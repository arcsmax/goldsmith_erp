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
    CalendarEvent,
    CalendarEventType,
    Consultation,
    Customer,
    CustomerAuditLog,
    CustomerMeasurement,
    CostingMethod,
    GDPRRequest,
    Gemstone,
    HandoffStatusEnum,
    HandoffTypeEnum,
    Invoice,
    InvoiceLineItem,
    InvoiceLineType,
    InvoiceStatus,
    MaterialUsage,
    MeasurementType,
    MetalPurchase,
    MetalType,
    Notification,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    Order,
    OrderComment,
    OrderHallmark,
    OrderHandoff,
    OrderItem,
    OrderPhoto,
    OrderStatusEnum,
    OrderStatusHistory,
    HallmarkStatus,
    HallmarkType,
    Quote,
    QuoteLineItem,
    QuoteLineType,
    QuoteStatus,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    RepairPhoto,
    RepairPhotoPhase,
    ScrapGold,
    ScrapGoldItem,
    ScrapGoldStatus,
    AlloyType,
    TimeEntry,
    User,
    UserRole,
    ValuationCertificate,
)
from goldsmith_erp.services.customer_service import (
    CustomerService,
    REDACTION_TOKEN,
    SCRUBBABLE_FIELDS,
    SIGNATURE_REDACTION_TOKEN,
    ScrubTarget,
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
        # SCRUBBABLE_FIELDS keys + the two consultation special-case
        # counters (budget NULL-out / no-go hard-delete — Task 10, not
        # string-scrub targets) + "total".
        expected_keys = {target.counter_key for target in SCRUBBABLE_FIELDS} | {
            "consultations.budget",
            "customer_no_gos.deleted",
            "total",
        }
        assert set(log.details["counts"].keys()) == expected_keys
        assert log.details["counts"]["repair_jobs.item_description"] == 2


# ---------------------------------------------------------------------------
# Parametrised coverage matrix — one test per ScrubTarget
# ---------------------------------------------------------------------------
#
# The parametrised test below is driven by SCRUBBABLE_FIELDS. Adding a new
# ScrubTarget to that list automatically adds a new parametrised case here
# — no new test function to write. This replaces the "one test class per
# newly-discovered PII-leak field" churn seen in H1/H2/H5/H8.
#
# ``_TARGET_FACTORIES`` maps (table_name, column) → an async factory that
# builds the parent row(s) with PII in the named column and returns the
# row instance. Each factory accepts a ``pii_value`` and ``db_session`` +
# the customer/admin fixtures.


PII_STRING = "Ring fuer Maria Mueller"


async def _mk_order(
    db: AsyncSession, customer: Customer, admin: User, *, title=None,
    description=None, special_instructions=None,
) -> Order:
    order = Order(
        title=title or "Order",
        description=description,
        special_instructions=special_instructions,
        customer_id=customer.id,
        status=OrderStatusEnum.NEW,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _mk_activity(db: AsyncSession) -> Activity:
    activity = Activity(
        name="Polieren",
        category="fabrication",
        icon=":)",
        color="#FF0000",
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return activity


async def _mk_repair(
    db: AsyncSession, customer: Customer, admin: User, **overrides,
) -> RepairJob:
    defaults = dict(
        repair_number=f"REP-2026-{uuid.uuid4().hex[:6]}",
        bag_number="A1",
        customer_id=customer.id,
        received_by=admin.id,
        item_description="Standard item",
        item_type=RepairItemType.RING,
        status=RepairJobStatus.RECEIVED,
    )
    defaults.update(overrides)
    repair = RepairJob(**defaults)
    db.add(repair)
    await db.commit()
    await db.refresh(repair)
    return repair


async def _mk_quote(
    db: AsyncSession, customer: Customer, admin: User, **overrides,
) -> Quote:
    defaults = dict(
        quote_number=f"KV-2026-{uuid.uuid4().hex[:6]}",
        customer_id=customer.id,
        created_by=admin.id,
        status=QuoteStatus.DRAFT,
        valid_until=datetime.utcnow() + timedelta(days=14),
    )
    defaults.update(overrides)
    quote = Quote(**defaults)
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote


async def _mk_invoice(
    db: AsyncSession, customer: Customer, admin: User, **overrides,
) -> Invoice:
    order = await _mk_order(db, customer, admin)
    defaults = dict(
        invoice_number=f"RE-2026-{uuid.uuid4().hex[:6]}",
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin.id,
        status=InvoiceStatus.DRAFT,
        due_date=datetime.utcnow() + timedelta(days=14),
    )
    defaults.update(overrides)
    invoice = Invoice(**defaults)
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def _mk_scrap_gold(
    db: AsyncSession, customer: Customer, admin: User, **overrides,
) -> ScrapGold:
    order = await _mk_order(db, customer, admin)
    defaults = dict(
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin.id,
        status=ScrapGoldStatus.RECEIVED,
    )
    defaults.update(overrides)
    scrap = ScrapGold(**defaults)
    db.add(scrap)
    await db.commit()
    await db.refresh(scrap)
    return scrap


async def _mk_metal_purchase(db: AsyncSession) -> MetalPurchase:
    purchase = MetalPurchase(
        metal_type=MetalType.GOLD_18K,
        weight_g=100.0,
        remaining_weight_g=90.0,
        price_total=5000.0,
        price_per_gram=50.0,
        supplier="Supplier X",
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)
    return purchase


# For each ScrubTarget, provide an async function that creates the parent
# row(s) with PII in the target column. Returns the row instance so the
# test can re-fetch and assert the field is scrubbed.
#
# Signature: async def factory(db, customer, admin, pii_value) -> row

async def _f_orders_title(db, customer, admin, pii_value):
    return await _mk_order(db, customer, admin, title=pii_value)


async def _f_orders_description(db, customer, admin, pii_value):
    return await _mk_order(db, customer, admin, description=pii_value)


async def _f_orders_special_instructions(db, customer, admin, pii_value):
    return await _mk_order(db, customer, admin, special_instructions=pii_value)


async def _f_order_comments_text(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    comment = OrderComment(order_id=order.id, user_id=admin.id, text=pii_value)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def _f_time_entries_notes(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    activity = await _mk_activity(db)
    entry = TimeEntry(
        order_id=order.id,
        user_id=admin.id,
        activity_id=activity.id,
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow(),
        duration_minutes=60,
        notes=pii_value,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def _f_order_status_history_notes(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    history = OrderStatusHistory(
        order_id=order.id,
        to_status="completed",
        changed_by=admin.id,
        notes=pii_value,
    )
    db.add(history)
    await db.commit()
    await db.refresh(history)
    return history


async def _f_order_handoffs_notes(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    handoff = OrderHandoff(
        order_id=order.id,
        from_user_id=admin.id,
        to_user_id=admin.id,
        handoff_type=HandoffTypeEnum.PASS_TO_NEXT,
        status=HandoffStatusEnum.PENDING,
        notes=pii_value,
    )
    db.add(handoff)
    await db.commit()
    await db.refresh(handoff)
    return handoff


async def _f_order_handoffs_response_notes(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    handoff = OrderHandoff(
        order_id=order.id,
        from_user_id=admin.id,
        to_user_id=admin.id,
        handoff_type=HandoffTypeEnum.PASS_TO_NEXT,
        status=HandoffStatusEnum.ACCEPTED,
        response_notes=pii_value,
    )
    db.add(handoff)
    await db.commit()
    await db.refresh(handoff)
    return handoff


async def _f_gemstones_notes(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    gem = Gemstone(
        order_id=order.id,
        type="diamond",
        cost=500.0,
        quantity=1,
        notes=pii_value,
    )
    db.add(gem)
    await db.commit()
    await db.refresh(gem)
    return gem


async def _f_repair_jobs_item_description(db, customer, admin, pii_value):
    return await _mk_repair(db, customer, admin, item_description=pii_value)


async def _f_repair_jobs_diagnosis_notes(db, customer, admin, pii_value):
    return await _mk_repair(db, customer, admin, diagnosis_notes=pii_value)


async def _f_valuation_certificates_item_description(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    cert = ValuationCertificate(
        certificate_number=f"WG-2026-{uuid.uuid4().hex[:6]}",
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin.id,
        item_description=pii_value,
        appraised_value=1000.0,
        valuation_date=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(days=730),
        goldsmith_name="Test Goldsmith",
    )
    db.add(cert)
    await db.commit()
    await db.refresh(cert)
    return cert


async def _f_valuation_certificates_gemstones_description(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    cert = ValuationCertificate(
        certificate_number=f"WG-2026-{uuid.uuid4().hex[:6]}",
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin.id,
        item_description="Ring",
        gemstones_description=pii_value,
        appraised_value=1000.0,
        valuation_date=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(days=730),
        goldsmith_name="Test Goldsmith",
    )
    db.add(cert)
    await db.commit()
    await db.refresh(cert)
    return cert


async def _f_quotes_notes(db, customer, admin, pii_value):
    return await _mk_quote(db, customer, admin, notes=pii_value)


async def _f_quotes_signature(db, customer, admin, pii_value):
    # Binary field: store the "PII value" as-is; scrubber replaces the whole
    # blob with SIGNATURE_REDACTION_TOKEN. We re-use the same pii_value for
    # interface symmetry; the assertion checks against the sentinel.
    return await _mk_quote(
        db, customer, admin,
        status=QuoteStatus.APPROVED,
        customer_signature_data=pii_value,
    )


async def _f_customer_measurements_notes(db, customer, admin, pii_value):
    measurement = CustomerMeasurement(
        customer_id=customer.id,
        measured_by=admin.id,
        measurement_type=MeasurementType.RING_SIZE,
        value=52.0,
        unit="mm",
        notes=pii_value,
    )
    db.add(measurement)
    await db.commit()
    await db.refresh(measurement)
    return measurement


async def _f_order_photos_notes(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    photo = OrderPhoto(
        order_id=order.id,
        file_path="/tmp/photo.jpg",
        taken_by=admin.id,
        notes=pii_value,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


async def _f_repair_photos_notes(db, customer, admin, pii_value):
    repair = await _mk_repair(db, customer, admin)
    photo = RepairPhoto(
        repair_job_id=repair.id,
        phase=RepairPhotoPhase.INTAKE,
        file_path="/tmp/repair.jpg",
        taken_by=admin.id,
        notes=pii_value,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


async def _f_order_hallmarks_notes(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    hallmark = OrderHallmark(
        order_id=order.id,
        hallmark_type=HallmarkType.FINENESS_MARK,
        status=HallmarkStatus.PENDING,
        notes=pii_value,
        created_by=admin.id,
    )
    db.add(hallmark)
    await db.commit()
    await db.refresh(hallmark)
    return hallmark


async def _f_order_items_description(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    item = OrderItem(
        order_id=order.id,
        description=pii_value,
        quantity=1,
        unit_price=100.0,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def _f_invoices_notes(db, customer, admin, pii_value):
    return await _mk_invoice(db, customer, admin, notes=pii_value)


async def _f_invoice_line_items_description(db, customer, admin, pii_value):
    invoice = await _mk_invoice(db, customer, admin)
    line = InvoiceLineItem(
        invoice_id=invoice.id,
        line_type=InvoiceLineType.MATERIAL,
        description=pii_value,
        quantity=1.0,
        unit_price=100.0,
        total=100.0,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return line


async def _f_quote_line_items_description(db, customer, admin, pii_value):
    quote = await _mk_quote(db, customer, admin)
    line = QuoteLineItem(
        quote_id=quote.id,
        line_type=QuoteLineType.MATERIAL,
        description=pii_value,
        quantity=1.0,
        unit_price=100.0,
        total=100.0,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return line


async def _f_scrap_gold_notes(db, customer, admin, pii_value):
    return await _mk_scrap_gold(db, customer, admin, notes=pii_value)


async def _f_scrap_gold_signature(db, customer, admin, pii_value):
    # Binary field — same as quotes.customer_signature_data.
    return await _mk_scrap_gold(db, customer, admin, signature_data=pii_value)


async def _f_scrap_gold_items_description(db, customer, admin, pii_value):
    scrap = await _mk_scrap_gold(db, customer, admin)
    item = ScrapGoldItem(
        scrap_gold_id=scrap.id,
        description=pii_value,
        alloy=AlloyType.GOLD_585,
        weight_g=5.0,
        fine_content_g=2.925,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def _f_material_usage_notes(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    purchase = await _mk_metal_purchase(db)
    usage = MaterialUsage(
        order_id=order.id,
        metal_purchase_id=purchase.id,
        weight_used_g=1.0,
        cost_at_time=50.0,
        price_per_gram_at_time=50.0,
        costing_method=CostingMethod.FIFO,
        notes=pii_value,
    )
    db.add(usage)
    await db.commit()
    await db.refresh(usage)
    return usage


async def _f_calendar_events_title(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    event = CalendarEvent(
        title=pii_value,
        event_type=CalendarEventType.WORKSHOP_TASK,
        start_datetime=datetime.utcnow(),
        order_id=order.id,
        user_id=admin.id,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def _f_calendar_events_description(db, customer, admin, pii_value):
    order = await _mk_order(db, customer, admin)
    event = CalendarEvent(
        title="Task",
        description=pii_value,
        event_type=CalendarEventType.WORKSHOP_TASK,
        start_datetime=datetime.utcnow(),
        order_id=order.id,
        user_id=admin.id,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def _f_notifications_title(db, customer, admin, pii_value):
    notif = Notification(
        user_id=admin.id,
        title=pii_value,
        message="stub",
        notification_type=NotificationTypeEnum.ORDER_STATUS,
        severity=NotificationSeverityEnum.INFO,
        related_customer_id=customer.id,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    return notif


async def _f_notifications_message(db, customer, admin, pii_value):
    notif = Notification(
        user_id=admin.id,
        title="stub",
        message=pii_value,
        notification_type=NotificationTypeEnum.ORDER_STATUS,
        severity=NotificationSeverityEnum.INFO,
        related_customer_id=customer.id,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    return notif


async def _f_customers_notes(db, customer, admin, pii_value):
    """F1: set the customer's own ``notes`` column.

    Unlike the other factories, this one does NOT create a new parent
    row — the existing `customer` fixture IS the target row, linked
    via ``link="direct"``.
    """
    customer.notes = pii_value
    await db.commit()
    await db.refresh(customer)
    return customer


async def _f_consultations_wishes(db, customer, admin, pii_value):
    consultation = Consultation(
        customer_id=customer.id,
        conducted_by=admin.id,
        wishes=pii_value,
    )
    db.add(consultation)
    await db.commit()
    await db.refresh(consultation)
    return consultation


async def _f_consultations_notes(db, customer, admin, pii_value):
    consultation = Consultation(
        customer_id=customer.id,
        conducted_by=admin.id,
        notes=pii_value,
    )
    db.add(consultation)
    await db.commit()
    await db.refresh(consultation)
    return consultation


async def _f_consultations_source_material(db, customer, admin, pii_value):
    consultation = Consultation(
        customer_id=customer.id,
        conducted_by=admin.id,
        source_material=pii_value,
    )
    db.add(consultation)
    await db.commit()
    await db.refresh(consultation)
    return consultation


# Per-target factory map. Keyed by counter_key for traceability against
# SCRUBBABLE_FIELDS. The parametrised test asserts this map covers every
# SCRUBBABLE_FIELDS entry — so adding a new target without adding a factory
# fails fast rather than silently skipping.
_FACTORY_MAP = {
    "orders.title": _f_orders_title,
    "orders.description": _f_orders_description,
    "orders.special_instructions": _f_orders_special_instructions,
    "order_comments.text": _f_order_comments_text,
    "time_entries.notes": _f_time_entries_notes,
    "order_status_history.notes": _f_order_status_history_notes,
    "order_handoffs.notes": _f_order_handoffs_notes,
    "order_handoffs.response_notes": _f_order_handoffs_response_notes,
    "gemstones.notes": _f_gemstones_notes,
    "repair_jobs.item_description": _f_repair_jobs_item_description,
    "repair_jobs.diagnosis_notes": _f_repair_jobs_diagnosis_notes,
    "valuation_certificates.item_description": _f_valuation_certificates_item_description,
    "valuation_certificates.gemstones_description": _f_valuation_certificates_gemstones_description,
    "quotes.notes": _f_quotes_notes,
    "quotes.customer_signature_data": _f_quotes_signature,
    "customer_measurements.notes": _f_customer_measurements_notes,
    "order_photos.notes": _f_order_photos_notes,
    "repair_photos.notes": _f_repair_photos_notes,
    "order_hallmarks.notes": _f_order_hallmarks_notes,
    "order_items.description": _f_order_items_description,
    "invoices.notes": _f_invoices_notes,
    "invoice_line_items.description": _f_invoice_line_items_description,
    "quote_line_items.description": _f_quote_line_items_description,
    "scrap_gold.notes": _f_scrap_gold_notes,
    "scrap_gold.signature_data": _f_scrap_gold_signature,
    "scrap_gold_items.description": _f_scrap_gold_items_description,
    "material_usage.notes": _f_material_usage_notes,
    "calendar_events.title": _f_calendar_events_title,
    "calendar_events.description": _f_calendar_events_description,
    "notifications.title": _f_notifications_title,
    "notifications.message": _f_notifications_message,
    # F1 (2026-04-16) — customers.notes — link="direct"
    "customers.notes": _f_customers_notes,
    # Consultation module (V1.1 / Task 10)
    "consultations.wishes": _f_consultations_wishes,
    "consultations.notes": _f_consultations_notes,
    "consultations.source_material": _f_consultations_source_material,
}


def test_factory_map_covers_every_scrub_target():
    """Meta-test: every ScrubTarget must have a factory. Adding a new
    ScrubTarget without a factory here fails this test, so the parametrised
    matrix below has 100% coverage of the declared scope.
    """
    target_keys = {t.counter_key for t in SCRUBBABLE_FIELDS}
    factory_keys = set(_FACTORY_MAP.keys())
    missing = target_keys - factory_keys
    extra = factory_keys - target_keys
    assert not missing, f"No factory for SCRUBBABLE_FIELDS entries: {missing}"
    assert not extra, f"Stale factories (no matching ScrubTarget): {extra}"


class TestScrubCoverageMatrix:
    """Parametrised matrix: exactly one case per ScrubTarget.

    Each case: create a fresh customer, create the parent row with
    ``PII_STRING`` in the target column, run the scrubber, assert the
    column no longer contains the PII tokens + the counter is non-zero.

    This replaces hand-written "class per newly-discovered field" tests.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "target",
        SCRUBBABLE_FIELDS,
        ids=[t.counter_key for t in SCRUBBABLE_FIELDS],
    )
    async def test_target_is_scrubbed(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
        target: ScrubTarget,
    ):
        factory = _FACTORY_MAP[target.counter_key]
        row = await factory(db_session, mueller_maria, admin, PII_STRING)

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(row)

        scrubbed = getattr(row, target.column)

        if target.binary:
            assert scrubbed == SIGNATURE_REDACTION_TOKEN, (
                f"Binary target {target.counter_key} not replaced with sentinel"
            )
            assert counts[target.counter_key] == 1
        else:
            # PII tokens must be gone; REDACTION_TOKEN must be present.
            assert "Maria" not in scrubbed, (
                f"{target.counter_key} still contains 'Maria' after scrub: {scrubbed!r}"
            )
            assert "Mueller" not in scrubbed, (
                f"{target.counter_key} still contains 'Mueller' after scrub: {scrubbed!r}"
            )
            assert REDACTION_TOKEN in scrubbed, (
                f"{target.counter_key} has no REDACTION_TOKEN after scrub: {scrubbed!r}"
            )
            # PII_STRING "Ring fuer Maria Mueller" → 2 redactions.
            assert counts[target.counter_key] >= 2, (
                f"{target.counter_key} counter={counts[target.counter_key]} "
                f"< expected 2 for input {PII_STRING!r}"
            )


# ---------------------------------------------------------------------------
# Cross-customer "no bleed" test — Customer B untouched when A is scrubbed
# ---------------------------------------------------------------------------


class TestNoBleedAcrossCustomers:
    """Scrubbing customer A must not touch customer B's rows."""

    @pytest_asyncio.fixture
    async def schmidt_bernd(self, db_session: AsyncSession) -> Customer:
        """A completely separate customer with a different name set —
        Schmidt / Bernd shares no tokens with Mueller / Maria."""
        customer = Customer(
            first_name="Bernd",
            last_name="Schmidt",
            email=f"bernd.schmidt_{uuid.uuid4().hex[:8]}@example.de",
            phone="+49 30 7654321",
            customer_type="private",
            is_active=True,
        )
        db_session.add(customer)
        await db_session.commit()
        await db_session.refresh(customer)
        return customer

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "target",
        # Sample across link-kinds — 6 representative targets (full-matrix
        # no-bleed would be 31 targets × 2 = 62 setup rows per test run,
        # not worth the runtime).
        [
            t
            for t in SCRUBBABLE_FIELDS
            if t.counter_key
            in {
                "orders.description",
                "order_comments.text",
                "repair_jobs.item_description",
                "quotes.notes",
                "invoice_line_items.description",
                "notifications.message",
            }
        ],
        ids=lambda t: t.counter_key,
    )
    async def test_scrubbing_A_leaves_B_untouched(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        schmidt_bernd: Customer,
        admin: User,
        target: ScrubTarget,
    ):
        factory = _FACTORY_MAP[target.counter_key]
        # Customer A row — contains Maria Mueller PII
        row_a = await factory(
            db_session, mueller_maria, admin, "Ring fuer Maria Mueller",
        )
        # Customer B row — contains Bernd Schmidt PII
        row_b = await factory(
            db_session, schmidt_bernd, admin, "Ring fuer Bernd Schmidt",
        )

        # Scrub ONLY customer A.
        await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(row_a)
        await db_session.refresh(row_b)

        a_val = getattr(row_a, target.column)
        b_val = getattr(row_b, target.column)

        if target.binary:
            assert a_val == SIGNATURE_REDACTION_TOKEN
            # B's signature blob is untouched.
            assert b_val != SIGNATURE_REDACTION_TOKEN
        else:
            # A scrubbed, B untouched.
            assert "Maria" not in a_val
            assert "Mueller" not in a_val
            assert "Bernd" in b_val, (
                f"Customer B's {target.counter_key} was incorrectly scrubbed: {b_val!r}"
            )
            assert "Schmidt" in b_val, (
                f"Customer B's {target.counter_key} was incorrectly scrubbed: {b_val!r}"
            )


# ---------------------------------------------------------------------------
# System-field protection — scrubber MUST NOT touch DO-NOT-SCRUB columns
# ---------------------------------------------------------------------------


class TestSystemFieldProtection:
    """Audit tables, enum-only system columns, and the users table must
    never be modified by the scrubber — even if the customer's tokens
    accidentally match a system value.

    Picks 4 representative DO-NOT-SCRUB columns from PII-SCRUB-AUDIT.md:
    ``activities.name``, ``users.email``, ``audit_log entries``, and
    ``materials.name``.
    """

    @pytest.mark.asyncio
    async def test_activity_name_untouched(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Activity.name = 'Mueller-spezifische Politur' — the scrubber
        would match 'Mueller' IF it looked at activities, which it must not.
        """
        # Use the customer's real last name in an activity — simulating a
        # false positive surface.
        activity = Activity(
            name="Mueller-spezifische Politur",
            category="fabrication",
            icon=":)",
            color="#FF0000",
        )
        db_session.add(activity)
        await db_session.commit()
        await db_session.refresh(activity)

        original = activity.name
        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(activity)

        assert activity.name == original, (
            "Scrubber wrongly touched activities.name (system vocabulary)"
        )

    @pytest.mark.asyncio
    async def test_user_email_untouched(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Scrubbing a customer MUST NOT modify the users table.
        Slice 0 ``anonymize_user`` owns user erasure.
        """
        original_email = admin.email
        original_first_name = admin.first_name
        original_hash = admin.hashed_password

        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(admin)

        assert admin.email == original_email
        assert admin.first_name == original_first_name
        assert admin.hashed_password == original_hash

    @pytest.mark.asyncio
    async def test_customer_audit_log_rows_preserved(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """CustomerAuditLog rows contain PII tokens (e.g. old_value =
        'Maria Mueller') as audit evidence. Art. 17 preserves them.
        Scrubbing MUST NOT modify existing audit rows.
        """
        pre_existing = CustomerAuditLog(
            customer_id=mueller_maria.id,
            user_id=admin.id,
            action="customer_update",
            entity="customer",
            field_name="last_name",
            old_value="Mueller",  # PII token — must survive scrub
            new_value="Mueller-Meier",
            timestamp=datetime.utcnow(),
        )
        db_session.add(pre_existing)
        await db_session.commit()
        await db_session.refresh(pre_existing)

        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(pre_existing)

        assert pre_existing.old_value == "Mueller", (
            "Scrubber wrongly mutated customer_audit_logs.old_value — "
            "Art. 17 preservation breached"
        )
        assert pre_existing.new_value == "Mueller-Meier"

    @pytest.mark.asyncio
    async def test_interruption_reason_untouched(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """``interruptions.reason`` is a system-level enum value
        (``customer_call``, ``material_fetch``, …). The literal string
        ``customer_call`` must not be mis-scrubbed just because the
        substring "customer" appears."""
        from goldsmith_erp.db.models import Interruption

        order = await _mk_order(db_session, mueller_maria, admin)
        activity = await _mk_activity(db_session)
        entry = TimeEntry(
            order_id=order.id,
            user_id=admin.id,
            activity_id=activity.id,
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow(),
            duration_minutes=60,
        )
        db_session.add(entry)
        await db_session.commit()
        await db_session.refresh(entry)

        interruption = Interruption(
            time_entry_id=entry.id,
            reason="customer_call",
            duration_minutes=5,
        )
        db_session.add(interruption)
        await db_session.commit()
        await db_session.refresh(interruption)

        await CustomerService.scrub_customer_pii(
            db_session, customer_id=mueller_maria.id, performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(interruption)

        assert interruption.reason == "customer_call"


# ---------------------------------------------------------------------------
# Full-sweep integration test — one API-level scrub touches every field
# ---------------------------------------------------------------------------


class TestFullSweepIntegration:
    """Create a customer with PII in EVERY scrubbable field, issue a single
    ``scrub_customer_pii`` call, assert every target counter is non-zero
    and every row's scrubbed column is clean.
    """

    @pytest.mark.asyncio
    async def test_full_sweep_scrubs_every_field(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        # Build one parent row per target with PII_STRING injected.
        rows: Dict[str, Any] = {}
        for target in SCRUBBABLE_FIELDS:
            factory = _FACTORY_MAP[target.counter_key]
            rows[target.counter_key] = await factory(
                db_session, mueller_maria, admin, PII_STRING,
            )

        # Single scrub call.
        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        # Every counter non-zero.
        for target in SCRUBBABLE_FIELDS:
            assert counts[target.counter_key] >= 1, (
                f"Target {target.counter_key} was not scrubbed "
                f"(counts={counts[target.counter_key]})"
            )

        # Every row's column is clean (PII gone OR binary sentinel set).
        for target in SCRUBBABLE_FIELDS:
            row = rows[target.counter_key]
            await db_session.refresh(row)
            value = getattr(row, target.column)
            if target.binary:
                assert value == SIGNATURE_REDACTION_TOKEN, (
                    f"{target.counter_key} binary not replaced"
                )
            else:
                assert "Maria" not in value, (
                    f"{target.counter_key} still has 'Maria'"
                )
                assert "Mueller" not in value, (
                    f"{target.counter_key} still has 'Mueller'"
                )

        # Sanity: audit + GDPRRequest rows written.
        audit_row = (
            await db_session.execute(
                select(CustomerAuditLog).filter(
                    CustomerAuditLog.customer_id == mueller_maria.id,
                    CustomerAuditLog.action == "gdpr_pii_scrub",
                )
            )
        ).scalar_one()
        assert audit_row.details["scrubbed_field_count"] == len(
            SCRUBBABLE_FIELDS
        )

        gdpr_row = (
            await db_session.execute(
                select(GDPRRequest).filter(
                    GDPRRequest.customer_id == mueller_maria.id
                )
            )
        ).scalar_one()
        assert gdpr_row.request_type == "erasure"
        assert gdpr_row.status == "completed"

    @pytest.mark.asyncio
    async def test_full_sweep_is_idempotent(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Second scrub on fully-scrubbed data → zero additional redactions
        across every target.
        """
        for target in SCRUBBABLE_FIELDS:
            factory = _FACTORY_MAP[target.counter_key]
            await factory(db_session, mueller_maria, admin, PII_STRING)

        first = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        second = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        assert first["total"] > 0
        for target in SCRUBBABLE_FIELDS:
            assert second[target.counter_key] == 0, (
                f"Second pass on {target.counter_key} "
                f"double-redacted: {second[target.counter_key]}"
            )
