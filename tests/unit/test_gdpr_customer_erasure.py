"""
Unit tests for GDPR Art. 17 customer PII erasure scrubbing.

Covers `CustomerService.scrub_customer_pii` and the private helpers that
drive it. The scrubber scrubs PII from related free-text fields when a
customer is erased — see H2 and H5 in
docs/superpowers/plans/qr-barcode-workflow/V1.1-AMENDMENTS.md.

Scope per H2:
  - orders.description
  - orders.special_instructions
  - order_comments.text
  - time_entries.notes

Additional scope per H5 (extension):
  - order_status_history.notes
  - order_handoffs.notes
  - order_handoffs.response_notes
  - gemstones.notes
  - repair_jobs.item_description
  - repair_jobs.diagnosis_notes
  - valuation_certificates.item_description
  - valuation_certificates.gemstones_description
  - quotes.notes
  - quotes.customer_signature_data (blob → [REDACTED_SIGNATURE])
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    Customer,
    CustomerAuditLog,
    GDPRRequest,
    Gemstone,
    HandoffStatusEnum,
    HandoffTypeEnum,
    Order,
    OrderComment,
    OrderHandoff,
    OrderStatusEnum,
    OrderStatusHistory,
    Quote,
    QuoteStatus,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    TimeEntry,
    User,
    UserRole,
    ValuationCertificate,
)
from goldsmith_erp.services.customer_service import (
    CustomerService,
    REDACTION_TOKEN,
    SIGNATURE_REDACTION_TOKEN,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal data needed to exercise the scrubber
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mueller_maria(db_session: AsyncSession) -> Customer:
    """Create a customer whose name is likely to appear in free-text fields."""
    customer = Customer(
        first_name="Maria",
        last_name="Mueller",
        email=f"maria.mueller_{uuid.uuid4().hex[:8]}@example.de",
        phone="+49 89 1234567",
        mobile=None,
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    from goldsmith_erp.core.security import get_password_hash

    user = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("AdminPass123!"),
        first_name="Test",
        last_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_order(
    db: AsyncSession,
    customer: Customer,
    *,
    description: str | None = None,
    special_instructions: str | None = None,
) -> Order:
    order = Order(
        title="Test order",
        description=description,
        special_instructions=special_instructions,
        customer_id=customer.id,
        status=OrderStatusEnum.NEW,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


# ---------------------------------------------------------------------------
# Helper-level tests — _redact_text + _collect_pii_tokens
# ---------------------------------------------------------------------------

class TestRedactText:

    def test_name_tokens_are_redacted(self):
        tokens = ["Mueller", "Maria"]
        result, count = CustomerService._redact_text(
            "Trauring fuer Maria Mueller", tokens,
        )
        assert result == f"Trauring fuer {REDACTION_TOKEN} {REDACTION_TOKEN}"
        assert count == 2

    def test_case_insensitive_matching(self):
        tokens = ["Mueller"]
        result, count = CustomerService._redact_text(
            "kunde MUELLER war hier — mueller bestellt", tokens,
        )
        # two matches: MUELLER and mueller
        assert count == 2
        assert "MUELLER" not in result
        assert "mueller" not in result
        assert result.count(REDACTION_TOKEN) == 2

    def test_word_boundary_prevents_substring_match(self):
        """The name 'Max' should not match inside 'Maximilian'."""
        tokens = ["Max"]
        result, count = CustomerService._redact_text(
            "Maximilian ist ein Tag, Max war heute da.", tokens,
        )
        assert count == 1
        # Maximilian untouched
        assert "Maximilian" in result
        assert REDACTION_TOKEN in result

    def test_phone_number_exact_match(self):
        tokens = ["+49 89 1234567"]
        result, count = CustomerService._redact_text(
            "Anruf +49 89 1234567 um 14 Uhr", tokens,
        )
        assert count == 1
        assert "+49 89 1234567" not in result
        assert REDACTION_TOKEN in result

    def test_phone_number_digits_only_variant(self):
        """Digits-only variant matches even when original contained spaces/+."""
        tokens = ["49891234567"]
        result, count = CustomerService._redact_text(
            "Mobil 49891234567 nach 18 Uhr", tokens,
        )
        assert count == 1

    def test_email_address_match(self):
        tokens = ["maria.mueller@example.de"]
        result, count = CustomerService._redact_text(
            "Kontakt: maria.mueller@example.de bitte bestaetigen.", tokens,
        )
        assert count == 1
        assert "maria.mueller@example.de" not in result

    def test_text_without_pii_is_unchanged(self):
        tokens = ["Mueller", "Maria"]
        original = "Standard-Trauring 585er Gelbgold, 4 mm breit"
        result, count = CustomerService._redact_text(original, tokens)
        assert result == original
        assert count == 0

    def test_none_text_returns_none(self):
        tokens = ["Mueller"]
        result, count = CustomerService._redact_text(None, tokens)
        assert result is None
        assert count == 0

    def test_empty_token_list_is_safe(self):
        result, count = CustomerService._redact_text("some text", [])
        assert result == "some text"
        assert count == 0

    def test_idempotent_on_repeat(self):
        """Running the scrub twice produces the same output as once."""
        tokens = ["Mueller", "Maria"]
        once, count1 = CustomerService._redact_text(
            "Trauring fuer Maria Mueller", tokens,
        )
        twice, count2 = CustomerService._redact_text(once, tokens)
        assert once == twice
        assert count1 == 2
        assert count2 == 0


class TestCollectPiiTokens:

    def test_short_names_are_discarded(self):
        """Tokens < 3 chars are too generic to safely redact."""
        customer = Customer(
            first_name="Al",
            last_name="Bo",
            email="al@bo.de",
            phone=None,
            mobile=None,
            company_name=None,
        )
        tokens = CustomerService._collect_pii_tokens(customer)
        assert "Al" not in tokens
        assert "Bo" not in tokens

    def test_phone_produces_digit_only_variant(self):
        customer = Customer(
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            phone="+49 89 1234567",
            mobile=None,
            company_name=None,
        )
        tokens = CustomerService._collect_pii_tokens(customer)
        assert "+49 89 1234567" in tokens
        assert "49891234567" in tokens

    def test_tokens_are_sorted_by_length_desc(self):
        customer = Customer(
            first_name="Maria",
            last_name="Mueller",
            company_name="Mueller GmbH",
            email="maria@example.de",
            phone=None,
            mobile=None,
        )
        tokens = CustomerService._collect_pii_tokens(customer)
        # Longest first
        lengths = [len(t) for t in tokens]
        assert lengths == sorted(lengths, reverse=True)


# ---------------------------------------------------------------------------
# Service-level tests — scrub_customer_pii end-to-end against the DB
# ---------------------------------------------------------------------------

class TestScrubCustomerPii:

    @pytest.mark.asyncio
    async def test_scrub_redacts_order_description(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Order description 'Trauring fuer Maria Mueller' becomes '[REDACTED] [REDACTED]'."""
        order = await _make_order(
            db_session,
            mueller_maria,
            description="Trauring fuer Maria Mueller",
        )

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(order)

        assert order.description == f"Trauring fuer {REDACTION_TOKEN} {REDACTION_TOKEN}"
        assert counts["orders.description"] == 2
        assert counts["total"] == 2

    @pytest.mark.asyncio
    async def test_scrub_is_case_insensitive_in_db(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _make_order(
            db_session,
            mueller_maria,
            description="Kunde MUELLER hat angerufen",
        )

        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(order)

        assert "MUELLER" not in order.description
        assert REDACTION_TOKEN in order.description

    @pytest.mark.asyncio
    async def test_scrub_matches_phone_number(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _make_order(
            db_session,
            mueller_maria,
            special_instructions="Anruf vor Abholung: +49 89 1234567",
        )

        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(order)

        assert "+49 89 1234567" not in order.special_instructions
        assert REDACTION_TOKEN in order.special_instructions

    @pytest.mark.asyncio
    async def test_scrub_matches_email(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _make_order(
            db_session,
            mueller_maria,
            special_instructions=f"Nachricht an {mueller_maria.email} schicken",
        )

        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(order)

        assert mueller_maria.email not in order.special_instructions
        assert REDACTION_TOKEN in order.special_instructions

    @pytest.mark.asyncio
    async def test_order_description_without_pii_unchanged(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        original = "Standard-Trauring 585er Gelbgold, 4 mm breit, poliert"
        order = await _make_order(
            db_session,
            mueller_maria,
            description=original,
        )

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(order)

        assert order.description == original
        assert counts["orders.description"] == 0

    @pytest.mark.asyncio
    async def test_scrub_is_idempotent(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Running the scrub twice on the same record must not double-redact."""
        order = await _make_order(
            db_session,
            mueller_maria,
            description="Trauring fuer Maria Mueller",
        )

        first = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(order)
        description_after_first = order.description

        second = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(order)

        assert order.description == description_after_first
        assert first["total"] == 2
        assert second["total"] == 0

    @pytest.mark.asyncio
    async def test_scrub_redacts_order_comments(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _make_order(
            db_session,
            mueller_maria,
            description="Trauring",
        )
        comment = OrderComment(
            order_id=order.id,
            user_id=admin.id,
            text="Maria Mueller hat heute angerufen wegen Anprobe.",
        )
        db_session.add(comment)
        await db_session.commit()

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(comment)

        assert "Maria" not in comment.text
        assert "Mueller" not in comment.text
        assert counts["order_comments.text"] >= 2

    @pytest.mark.asyncio
    async def test_scrub_redacts_time_entry_notes(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _make_order(
            db_session,
            mueller_maria,
            description="Trauring",
        )
        activity = Activity(
            name="Polieren",
            category="fabrication",
            icon=":)",
            color="#FF0000",
        )
        db_session.add(activity)
        await db_session.commit()
        await db_session.refresh(activity)

        entry = TimeEntry(
            order_id=order.id,
            user_id=admin.id,
            activity_id=activity.id,
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow(),
            duration_minutes=60,
            notes="Rueckfrage Maria Mueller zu Ringgroesse",
        )
        db_session.add(entry)
        await db_session.commit()

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(entry)

        assert "Maria" not in entry.notes
        assert "Mueller" not in entry.notes
        assert counts["time_entries.notes"] >= 2

    @pytest.mark.asyncio
    async def test_scrub_writes_audit_log(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        await _make_order(
            db_session,
            mueller_maria,
            description="Trauring fuer Maria Mueller",
        )

        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()

        audit_result = await db_session.execute(
            select(CustomerAuditLog).filter(
                CustomerAuditLog.customer_id == mueller_maria.id,
                CustomerAuditLog.action == "gdpr_pii_scrub",
            )
        )
        log = audit_result.scalar_one()
        assert log.user_id == admin.id
        assert log.details["counts"]["total"] == 2

    @pytest.mark.asyncio
    async def test_scrub_writes_gdpr_request_row(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """H3 progress: scrub persists a GDPRRequest row for Art. 30 tracking."""
        await _make_order(
            db_session,
            mueller_maria,
            description="Trauring fuer Maria Mueller",
        )

        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()

        gdpr_result = await db_session.execute(
            select(GDPRRequest).filter(GDPRRequest.customer_id == mueller_maria.id)
        )
        request = gdpr_result.scalar_one()
        assert request.request_type == "erasure"
        assert request.status == "completed"
        assert request.requested_by == admin.id
        assert request.completed_at is not None

    @pytest.mark.asyncio
    async def test_scrub_for_nonexistent_customer_returns_zero_counts(
        self,
        db_session: AsyncSession,
        admin: User,
    ):
        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=999_999, performed_by=admin.id,
        )
        assert counts["total"] == 0
        # Must not write audit rows for a customer that never existed.
        audit_result = await db_session.execute(
            select(CustomerAuditLog).filter(CustomerAuditLog.customer_id == 999_999)
        )
        assert audit_result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# H5 extension tests — 8 additional free-text fields per V1.1-AMENDMENTS.md
# ---------------------------------------------------------------------------


class TestScrubH5OrderScopedFields:
    """Fields discovered by the H2 hotfix agent that live on tables
    reached via ``order_id`` (gemstones, order_status_history,
    order_handoffs)."""

    @pytest.mark.asyncio
    async def test_scrub_redacts_order_status_history_notes(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _make_order(db_session, mueller_maria, description="Ring")
        history = OrderStatusHistory(
            order_id=order.id,
            from_status="in_progress",
            to_status="completed",
            changed_by=admin.id,
            notes="Bei Abholung durch Maria Mueller bemerkt — Ring zu klein.",
        )
        db_session.add(history)
        await db_session.commit()
        await db_session.refresh(history)

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(history)

        assert "Maria" not in history.notes
        assert "Mueller" not in history.notes
        assert REDACTION_TOKEN in history.notes
        assert counts["order_status_history.notes"] == 2

    @pytest.mark.asyncio
    async def test_scrub_redacts_order_handoff_notes_and_response(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _make_order(db_session, mueller_maria, description="Ring")
        handoff = OrderHandoff(
            order_id=order.id,
            from_user_id=admin.id,
            to_user_id=admin.id,
            handoff_type=HandoffTypeEnum.PASS_TO_NEXT,
            status=HandoffStatusEnum.ACCEPTED,
            notes="Maria Mueller holt Freitag ab",
            response_notes="Uebernahme OK — Mueller informiert",
        )
        db_session.add(handoff)
        await db_session.commit()
        await db_session.refresh(handoff)

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(handoff)

        assert "Maria" not in handoff.notes
        assert "Mueller" not in handoff.notes
        assert REDACTION_TOKEN in handoff.notes
        assert "Mueller" not in handoff.response_notes
        assert REDACTION_TOKEN in handoff.response_notes
        assert counts["order_handoffs.notes"] == 2
        assert counts["order_handoffs.response_notes"] == 1

    @pytest.mark.asyncio
    async def test_scrub_redacts_gemstone_notes(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _make_order(db_session, mueller_maria, description="Ring")
        gem = Gemstone(
            order_id=order.id,
            type="diamond",
            cost=500.0,
            quantity=1,
            notes="Stein vom Kunden Maria Mueller mitgebracht",
        )
        db_session.add(gem)
        await db_session.commit()
        await db_session.refresh(gem)

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(gem)

        assert "Maria" not in gem.notes
        assert "Mueller" not in gem.notes
        assert REDACTION_TOKEN in gem.notes
        assert counts["gemstones.notes"] == 2


class TestScrubH5CustomerScopedFields:
    """Fields on tables that carry a direct ``customer_id`` FK
    (repair_jobs, valuation_certificates, quotes). These are scrubbed
    even when the customer has no orders."""

    @pytest.mark.asyncio
    async def test_scrub_redacts_repair_job_fields(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        repair = RepairJob(
            repair_number=f"REP-2026-{uuid.uuid4().hex[:6]}",
            bag_number="A1",
            customer_id=mueller_maria.id,
            received_by=admin.id,
            item_description="Goldring Frau Maria Mueller - Stein nachfassen",
            item_type=RepairItemType.RING,
            status=RepairJobStatus.RECEIVED,
            diagnosis_notes="Kunde (Maria Mueller) wuenscht neuen Stein",
        )
        db_session.add(repair)
        await db_session.commit()
        await db_session.refresh(repair)

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(repair)

        assert "Maria" not in repair.item_description
        assert "Mueller" not in repair.item_description
        assert "Maria" not in repair.diagnosis_notes
        assert "Mueller" not in repair.diagnosis_notes
        # "Maria Mueller" → 2 redactions in each of the two fields
        assert counts["repair_jobs.item_description"] == 2
        assert counts["repair_jobs.diagnosis_notes"] == 2

    @pytest.mark.asyncio
    async def test_scrub_redacts_valuation_certificate_fields(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """``valuation_certificates`` has no ``notes`` column on the model.
        The PII-leak surface claimed by H5 lives on ``item_description`` and
        ``gemstones_description`` instead — those are what we scrub.
        """
        order = await _make_order(db_session, mueller_maria, description="Ring")
        valuation = ValuationCertificate(
            certificate_number=f"WG-2026-{uuid.uuid4().hex[:6]}",
            order_id=order.id,
            customer_id=mueller_maria.id,
            created_by=admin.id,
            item_description=(
                "Trauring Wertgutachten fuer Maria Mueller, 750 Gelbgold"
            ),
            gemstones_description=(
                "Ein Brillant, vom Kunden Mueller mitgebracht"
            ),
            appraised_value=2500.0,
            valuation_date=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(days=730),
            goldsmith_name="Test Goldsmith",
        )
        db_session.add(valuation)
        await db_session.commit()
        await db_session.refresh(valuation)

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(valuation)

        assert "Maria" not in valuation.item_description
        assert "Mueller" not in valuation.item_description
        assert "Mueller" not in valuation.gemstones_description
        assert counts["valuation_certificates.item_description"] == 2
        assert counts["valuation_certificates.gemstones_description"] == 1

    @pytest.mark.asyncio
    async def test_scrub_redacts_quote_notes(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        quote = Quote(
            quote_number=f"KV-2026-{uuid.uuid4().hex[:6]}",
            customer_id=mueller_maria.id,
            created_by=admin.id,
            status=QuoteStatus.DRAFT,
            valid_until=datetime.utcnow() + timedelta(days=14),
            notes="Sonderkonditionen fuer Stammkundin Maria Mueller vereinbart",
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(quote)

        assert "Maria" not in quote.notes
        assert "Mueller" not in quote.notes
        assert counts["quotes.notes"] == 2

    @pytest.mark.asyncio
    async def test_scrub_replaces_customer_signature_blob(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """The base64 signature blob is replaced wholesale — regex cannot
        reach into image bytes, so we swap the entire field for a sentinel.
        """
        fake_signature_base64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE"
            "QVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII="
        )
        quote = Quote(
            quote_number=f"KV-2026-{uuid.uuid4().hex[:6]}",
            customer_id=mueller_maria.id,
            created_by=admin.id,
            status=QuoteStatus.APPROVED,
            valid_until=datetime.utcnow() + timedelta(days=14),
            customer_signature_data=fake_signature_base64,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(quote)

        assert quote.customer_signature_data == SIGNATURE_REDACTION_TOKEN
        assert counts["quotes.customer_signature_data"] == 1

    @pytest.mark.asyncio
    async def test_scrub_skips_empty_customer_signature(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Empty signature field → zero redactions, no audit noise."""
        quote = Quote(
            quote_number=f"KV-2026-{uuid.uuid4().hex[:6]}",
            customer_id=mueller_maria.id,
            created_by=admin.id,
            status=QuoteStatus.DRAFT,
            valid_until=datetime.utcnow() + timedelta(days=14),
            customer_signature_data=None,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(quote)

        assert quote.customer_signature_data is None
        assert counts["quotes.customer_signature_data"] == 0


class TestScrubH5CrossField:
    """Whole-surface tests: combine many fields in one call, verify
    idempotency, verify non-PII content is untouched."""

    @pytest.mark.asyncio
    async def test_scrub_covers_all_h5_fields_in_single_call(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """One scrub call → PII redacted in all H5 fields that have data."""
        order = await _make_order(
            db_session,
            mueller_maria,
            description="Ring fuer Maria Mueller",
        )

        # Populate every H5 field with "Maria Mueller" PII.
        db_session.add_all([
            OrderStatusHistory(
                order_id=order.id,
                to_status="completed",
                notes="Maria Mueller abgeholt",
            ),
            OrderHandoff(
                order_id=order.id,
                from_user_id=admin.id,
                to_user_id=admin.id,
                handoff_type=HandoffTypeEnum.MARK_COMPLETE,
                status=HandoffStatusEnum.ACCEPTED,
                notes="Maria Mueller bereit zur Abholung",
                response_notes="Mueller informiert",
            ),
            Gemstone(
                order_id=order.id,
                type="diamond",
                cost=100.0,
                quantity=1,
                notes="Stein von Maria Mueller",
            ),
            RepairJob(
                repair_number=f"REP-2026-{uuid.uuid4().hex[:6]}",
                bag_number="A1",
                customer_id=mueller_maria.id,
                item_description="Ring Maria Mueller",
                item_type=RepairItemType.RING,
                status=RepairJobStatus.RECEIVED,
                diagnosis_notes="Mueller wuenscht Polieren",
            ),
            ValuationCertificate(
                certificate_number=f"WG-2026-{uuid.uuid4().hex[:6]}",
                order_id=order.id,
                customer_id=mueller_maria.id,
                item_description="Wertgutachten Maria Mueller",
                gemstones_description="Brillant, Mueller-Sammlung",
                appraised_value=500.0,
                valuation_date=datetime.utcnow(),
                valid_until=datetime.utcnow() + timedelta(days=730),
                goldsmith_name="Test",
            ),
            Quote(
                quote_number=f"KV-2026-{uuid.uuid4().hex[:6]}",
                customer_id=mueller_maria.id,
                created_by=admin.id,
                status=QuoteStatus.APPROVED,
                valid_until=datetime.utcnow() + timedelta(days=14),
                notes="Quote fuer Maria Mueller",
                customer_signature_data="SGVsbG8gTXVlbGxlcg==",  # "Hello Mueller" b64
            ),
        ])
        await db_session.commit()

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()

        # Every H5 field counter must be non-zero.
        assert counts["order_status_history.notes"] >= 2
        assert counts["order_handoffs.notes"] >= 2
        assert counts["order_handoffs.response_notes"] >= 1
        assert counts["gemstones.notes"] >= 2
        assert counts["repair_jobs.item_description"] >= 2
        assert counts["repair_jobs.diagnosis_notes"] >= 1
        assert counts["valuation_certificates.item_description"] >= 2
        assert counts["valuation_certificates.gemstones_description"] >= 1
        assert counts["quotes.notes"] >= 2
        assert counts["quotes.customer_signature_data"] == 1

    @pytest.mark.asyncio
    async def test_scrub_is_idempotent_across_h5_fields(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Second scrub on the same records → zero redactions, no errors."""
        order = await _make_order(
            db_session, mueller_maria, description="Ring Mueller",
        )
        db_session.add_all([
            OrderStatusHistory(
                order_id=order.id,
                to_status="completed",
                notes="Maria Mueller abgeholt",
            ),
            RepairJob(
                repair_number=f"REP-2026-{uuid.uuid4().hex[:6]}",
                bag_number="A1",
                customer_id=mueller_maria.id,
                item_description="Ring Mueller",
                item_type=RepairItemType.RING,
                status=RepairJobStatus.RECEIVED,
            ),
            Quote(
                quote_number=f"KV-2026-{uuid.uuid4().hex[:6]}",
                customer_id=mueller_maria.id,
                created_by=admin.id,
                status=QuoteStatus.APPROVED,
                valid_until=datetime.utcnow() + timedelta(days=14),
                notes="Notes Mueller",
                customer_signature_data="c2lnbmF0dXJl",  # "signature"
            ),
        ])
        await db_session.commit()

        first = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()

        second = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()

        assert first["total"] > 0
        # Every H5 field must show zero on the second pass.
        for field in (
            "order_status_history.notes",
            "order_handoffs.notes",
            "order_handoffs.response_notes",
            "gemstones.notes",
            "repair_jobs.item_description",
            "repair_jobs.diagnosis_notes",
            "valuation_certificates.item_description",
            "valuation_certificates.gemstones_description",
            "quotes.notes",
            "quotes.customer_signature_data",
        ):
            assert second[field] == 0, f"{field} double-redacted: {second[field]}"

    @pytest.mark.asyncio
    async def test_scrub_leaves_non_pii_h5_content_untouched(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Fields containing only material codes / dates must not change."""
        order = await _make_order(db_session, mueller_maria, description="Ring")
        safe_notes = "Status 2026-04-16: 585 Gelbgold, 4 mm, poliert"
        history = OrderStatusHistory(
            order_id=order.id,
            to_status="completed",
            notes=safe_notes,
        )
        safe_repair_desc = "Goldring 750 — Politur und neue Rhodinierung"
        repair = RepairJob(
            repair_number=f"REP-2026-{uuid.uuid4().hex[:6]}",
            bag_number="A1",
            customer_id=mueller_maria.id,
            item_description=safe_repair_desc,
            item_type=RepairItemType.RING,
            status=RepairJobStatus.RECEIVED,
        )
        db_session.add_all([history, repair])
        await db_session.commit()
        await db_session.refresh(history)
        await db_session.refresh(repair)

        counts = await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(history)
        await db_session.refresh(repair)

        assert history.notes == safe_notes
        assert repair.item_description == safe_repair_desc
        assert counts["order_status_history.notes"] == 0
        assert counts["repair_jobs.item_description"] == 0

    @pytest.mark.asyncio
    async def test_audit_log_includes_h5_per_field_counts(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """CustomerAuditLog.details.counts must include every declared
        SCRUBBABLE_FIELDS key + ``total`` so the DPO can attest per-field
        coverage. Expected keys are derived from ``SCRUBBABLE_FIELDS`` —
        the test is automatically extended when new targets are added.
        """
        from goldsmith_erp.services.customer_service import SCRUBBABLE_FIELDS

        await _make_order(db_session, mueller_maria, description="Ring")
        db_session.add(RepairJob(
            repair_number=f"REP-2026-{uuid.uuid4().hex[:6]}",
            bag_number="A1",
            customer_id=mueller_maria.id,
            item_description="Ring Maria Mueller",
            item_type=RepairItemType.RING,
            status=RepairJobStatus.RECEIVED,
        ))
        await db_session.commit()

        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()

        result = await db_session.execute(
            select(CustomerAuditLog).filter(
                CustomerAuditLog.customer_id == mueller_maria.id,
                CustomerAuditLog.action == "gdpr_pii_scrub",
            )
        )
        log = result.scalar_one()
        expected_keys = {
            target.counter_key for target in SCRUBBABLE_FIELDS
        } | {"total"}
        assert set(log.details["counts"].keys()) == expected_keys
        assert log.details["counts"]["repair_jobs.item_description"] == 2
