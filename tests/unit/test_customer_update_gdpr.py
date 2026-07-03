"""GDPR erasure cascade for customer updates & cost-change requests (V1.2 / Task 6).

Extends the existing Art. 17 machinery covered by
``tests/unit/test_gdpr_customer_erasure.py`` (``CustomerService.scrub_customer_pii``)
to the ``CustomerUpdate`` / ``CostChangeRequest`` tables added in V1.2:

- ``customer_updates.body`` / ``.subject`` — PII-token scrubbed via
  ``SCRUBBABLE_FIELDS``, reachable via EITHER the ``order_id`` OR the
  ``repair_job_id`` link (exactly one is set per row — Pydantic-enforced,
  see the model docstring). Both link paths are exercised explicitly below
  (the generic coverage matrix in ``test_gdpr_customer_erasure.py`` only
  exercises the order-linked factory).
- ``customer_updates.photo_ids`` — structured JSON (OrderPhoto UUIDs), NOT
  a free-text field, so it is NULLed wholesale rather than token-redacted
  (same rationale as ``repair_jobs.intake_checklist``).
- ``cost_change_requests.reason`` / ``.response_evidence`` — PII-token
  scrubbed via the ``order_id`` link (``order_id`` is required/RESTRICT on
  this table, so there is no repair_job_id alternative).
- ``cost_change_requests.line_items`` — structured JSON, NULLed wholesale.

Both ``CustomerUpdate`` and ``CostChangeRequest`` rows themselves are
retained (skeleton rows for Art. 30 accountability / financial-record
retention, per the model docstrings) — only their free-text/JSON content
is scrubbed, mirroring the ``RepairJob``/``Consultation`` precedent.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    CostChangeRequest,
    Customer,
    CustomerUpdate,
    CustomerUpdateKind,
    Order,
    OrderStatusEnum,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    User,
    UserRole,
)
from goldsmith_erp.services.customer_service import REDACTION_TOKEN, CustomerService

# ---------------------------------------------------------------------------
# Fixtures — mirrors tests/unit/test_gdpr_customer_erasure.py's mueller_maria
# / admin fixtures so the customer's name is a real PII token the scrubber
# can match inside the customer-update / cost-change free-text fields.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mueller_maria(db_session: AsyncSession) -> Customer:
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
async def schmidt_bernd(db_session: AsyncSession) -> Customer:
    """A completely separate customer sharing no PII tokens with Mueller/Maria."""
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


async def _mk_order(db: AsyncSession, customer: Customer) -> Order:
    order = Order(
        title="Test order",
        customer_id=customer.id,
        status=OrderStatusEnum.NEW,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _mk_repair_job(
    db: AsyncSession, customer: Customer, admin: User
) -> RepairJob:
    repair = RepairJob(
        repair_number=f"REP-2026-{uuid.uuid4().hex[:6]}",
        bag_number="A1",
        customer_id=customer.id,
        received_by=admin.id,
        item_description="Standard item",
        item_type=RepairItemType.RING,
        status=RepairJobStatus.RECEIVED,
    )
    db.add(repair)
    await db.commit()
    await db.refresh(repair)
    return repair


# ---------------------------------------------------------------------------
# CustomerUpdate.body / .subject — order_id link
# ---------------------------------------------------------------------------


class TestScrubCustomerUpdateViaOrder:
    @pytest.mark.asyncio
    async def test_scrub_redacts_body_and_subject_order_linked(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _mk_order(db_session, mueller_maria)
        update = CustomerUpdate(
            order_id=order.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Fortschritt fuer Maria Mueller",
            body="Ihr Ring, Maria Mueller, ist fast fertig.",
            sent_by=admin.id,
        )
        db_session.add(update)
        await db_session.commit()
        await db_session.refresh(update)

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(update)

        assert "Maria" not in update.subject
        assert "Mueller" not in update.subject
        assert "Maria" not in update.body
        assert "Mueller" not in update.body
        assert REDACTION_TOKEN in update.subject
        assert REDACTION_TOKEN in update.body
        assert counts["customer_updates.subject"] >= 2
        assert counts["customer_updates.body"] >= 2


# ---------------------------------------------------------------------------
# CustomerUpdate.body / .subject — repair_job_id link (the second ScrubTarget
# entry sharing the same counter_key — not exercised by the generic coverage
# matrix, which only builds order-linked rows).
# ---------------------------------------------------------------------------


class TestScrubCustomerUpdateViaRepairJob:
    @pytest.mark.asyncio
    async def test_scrub_redacts_body_and_subject_repair_linked(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        repair = await _mk_repair_job(db_session, mueller_maria, admin)
        update = CustomerUpdate(
            repair_job_id=repair.id,
            kind=CustomerUpdateKind.READY_FOR_PICKUP,
            subject="Abholbereit fuer Maria Mueller",
            body="Die Reparatur von Maria Mueller ist abholbereit.",
            sent_by=admin.id,
        )
        db_session.add(update)
        await db_session.commit()
        await db_session.refresh(update)

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(update)

        assert "Maria" not in update.subject
        assert "Mueller" not in update.subject
        assert "Maria" not in update.body
        assert "Mueller" not in update.body
        assert counts["customer_updates.subject"] >= 2
        assert counts["customer_updates.body"] >= 2

    @pytest.mark.asyncio
    async def test_repair_linked_update_untouched_by_unrelated_customer_scrub(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        schmidt_bernd: Customer,
        admin: User,
    ):
        """A repair-linked CustomerUpdate for customer B must survive a
        scrub of customer A untouched — proves the repair_job_id link
        resolver scopes correctly to the erased customer's own repairs."""
        repair_b = await _mk_repair_job(db_session, schmidt_bernd, admin)
        update_b = CustomerUpdate(
            repair_job_id=repair_b.id,
            kind=CustomerUpdateKind.READY_FOR_PICKUP,
            subject="Abholbereit",
            body="Reparatur von Bernd Schmidt ist abholbereit.",
            sent_by=admin.id,
        )
        db_session.add(update_b)
        await db_session.commit()
        await db_session.refresh(update_b)

        await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(update_b)

        assert "Bernd" in update_b.body
        assert "Schmidt" in update_b.body


# ---------------------------------------------------------------------------
# CustomerUpdate.photo_ids — structured JSON, NULLed wholesale
# ---------------------------------------------------------------------------


class TestScrubCustomerUpdatePhotoIds:
    @pytest.mark.asyncio
    async def test_scrub_nulls_photo_ids_order_linked(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _mk_order(db_session, mueller_maria)
        update = CustomerUpdate(
            order_id=order.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Fortschritt",
            body="Fortschrittsbericht",
            photo_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
            sent_by=admin.id,
        )
        db_session.add(update)
        await db_session.commit()
        await db_session.refresh(update)

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(update)

        assert update.photo_ids is None
        assert counts["customer_updates.photo_ids"] == 1

        # Idempotent: second scrub finds nothing left to NULL.
        counts_again = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        assert counts_again["customer_updates.photo_ids"] == 0

    @pytest.mark.asyncio
    async def test_scrub_nulls_photo_ids_repair_linked(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        repair = await _mk_repair_job(db_session, mueller_maria, admin)
        update = CustomerUpdate(
            repair_job_id=repair.id,
            kind=CustomerUpdateKind.READY_FOR_PICKUP,
            subject="Abholbereit",
            body="Bericht",
            photo_ids=[str(uuid.uuid4())],
            sent_by=admin.id,
        )
        db_session.add(update)
        await db_session.commit()
        await db_session.refresh(update)

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(update)

        assert update.photo_ids is None
        assert counts["customer_updates.photo_ids"] == 1

    @pytest.mark.asyncio
    async def test_scrub_skips_empty_photo_ids(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """No photo_ids set → zero redactions, no audit noise.

        Omits the ``photo_ids`` kwarg entirely (rather than passing
        ``photo_ids=None``) so the column gets a genuine SQL NULL at
        INSERT time. Passing ``None`` explicitly would hit the same
        JSON-literal-'null' trap the scrub's own ``sa.null()`` special
        case guards against (Column(JSON) has ``none_as_null=False``) —
        that path is exercised by
        ``CustomerUpdateService.create_draft``'s ``photo_ids=data.photo_ids
        or None`` and is a pre-existing, orthogonal service-layer nuance,
        not something this GDPR scrub test needs to reproduce.
        """
        order = await _mk_order(db_session, mueller_maria)
        update = CustomerUpdate(
            order_id=order.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Fortschritt",
            body="Fortschrittsbericht",
            sent_by=admin.id,
        )
        db_session.add(update)
        await db_session.commit()
        await db_session.refresh(update)

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(update)

        assert update.photo_ids is None
        assert counts["customer_updates.photo_ids"] == 0


# ---------------------------------------------------------------------------
# CostChangeRequest.reason / .response_evidence — order_id link
# ---------------------------------------------------------------------------


class TestScrubCostChangeRequest:
    @pytest.mark.asyncio
    async def test_scrub_redacts_reason_and_response_evidence(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _mk_order(db_session, mueller_maria)
        request = CostChangeRequest(
            order_id=order.id,
            original_amount=100.0,
            new_amount=130.0,
            delta_percent=30.0,
            reason="Mehraufwand bei Maria Mueller wegen Steinbruch",
            response_evidence="Maria Mueller hat telefonisch zugestimmt",
            created_by=admin.id,
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(request)

        assert "Maria" not in request.reason
        assert "Mueller" not in request.reason
        assert "Maria" not in request.response_evidence
        assert "Mueller" not in request.response_evidence
        assert counts["cost_change_requests.reason"] >= 2
        assert counts["cost_change_requests.response_evidence"] >= 2

    @pytest.mark.asyncio
    async def test_scrub_nulls_line_items(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _mk_order(db_session, mueller_maria)
        request = CostChangeRequest(
            order_id=order.id,
            original_amount=100.0,
            new_amount=150.0,
            delta_percent=50.0,
            reason="Zusaetzliche Steinfassung",
            line_items=[{"label": "Diamant nachfassen", "amount": 50.0, "kind": "add"}],
            created_by=admin.id,
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(request)

        assert request.line_items is None
        assert counts["cost_change_requests.line_items"] == 1

        # Idempotent: second scrub finds nothing left to NULL.
        counts_again = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        assert counts_again["cost_change_requests.line_items"] == 0

    @pytest.mark.asyncio
    async def test_scrub_skips_empty_line_items(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """No line_items set → zero redactions. Omits the kwarg entirely
        (see the analogous photo_ids test's docstring for why passing
        ``None`` explicitly would trip the JSON-literal-'null' trap
        instead of leaving a genuine SQL NULL)."""
        order = await _mk_order(db_session, mueller_maria)
        request = CostChangeRequest(
            order_id=order.id,
            original_amount=100.0,
            new_amount=150.0,
            delta_percent=50.0,
            reason="Kein Line-Item-Detail",
            created_by=admin.id,
        )
        db_session.add(request)
        await db_session.commit()
        await db_session.refresh(request)

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(request)

        assert request.line_items is None
        assert counts["cost_change_requests.line_items"] == 0


# ---------------------------------------------------------------------------
# Idempotent re-scrub across both tables in one pass
# ---------------------------------------------------------------------------


class TestScrubIdempotentReScrub:
    @pytest.mark.asyncio
    async def test_second_scrub_produces_zero_counts(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        order = await _mk_order(db_session, mueller_maria)
        update = CustomerUpdate(
            order_id=order.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Update fuer Maria Mueller",
            body="Maria Mueller Bericht",
            photo_ids=[str(uuid.uuid4())],
            sent_by=admin.id,
        )
        request = CostChangeRequest(
            order_id=order.id,
            original_amount=100.0,
            new_amount=140.0,
            delta_percent=40.0,
            reason="Maria Mueller wuenscht Aenderung",
            line_items=[{"label": "Extra", "amount": 40.0, "kind": "add"}],
            created_by=admin.id,
        )
        db_session.add_all([update, request])
        await db_session.commit()

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

        assert first["customer_updates.body"] > 0
        assert first["customer_updates.photo_ids"] == 1
        assert first["cost_change_requests.reason"] > 0
        assert first["cost_change_requests.line_items"] == 1
        for key in (
            "customer_updates.body",
            "customer_updates.subject",
            "customer_updates.photo_ids",
            "cost_change_requests.reason",
            "cost_change_requests.line_items",
        ):
            assert second[key] == 0, f"{key} double-processed: {second[key]}"


# ---------------------------------------------------------------------------
# Cross-customer isolation — scrubbing A must not touch B's rows
# ---------------------------------------------------------------------------


class TestNoBleedAcrossCustomers:
    @pytest.mark.asyncio
    async def test_scrubbing_a_leaves_b_untouched(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        schmidt_bernd: Customer,
        admin: User,
    ):
        order_a = await _mk_order(db_session, mueller_maria)
        order_b = await _mk_order(db_session, schmidt_bernd)
        update_a = CustomerUpdate(
            order_id=order_a.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Update",
            body="Ring fuer Maria Mueller",
            photo_ids=[str(uuid.uuid4())],
            sent_by=admin.id,
        )
        update_b = CustomerUpdate(
            order_id=order_b.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Update",
            body="Ring fuer Bernd Schmidt",
            photo_ids=[str(uuid.uuid4())],
            sent_by=admin.id,
        )
        request_a = CostChangeRequest(
            order_id=order_a.id,
            original_amount=100.0,
            new_amount=130.0,
            delta_percent=30.0,
            reason="Aenderung fuer Maria Mueller",
            created_by=admin.id,
        )
        request_b = CostChangeRequest(
            order_id=order_b.id,
            original_amount=100.0,
            new_amount=130.0,
            delta_percent=30.0,
            reason="Aenderung fuer Bernd Schmidt",
            created_by=admin.id,
        )
        db_session.add_all([update_a, update_b, request_a, request_b])
        await db_session.commit()
        await db_session.refresh(update_a)
        await db_session.refresh(update_b)
        await db_session.refresh(request_a)
        await db_session.refresh(request_b)

        await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()
        await db_session.refresh(update_a)
        await db_session.refresh(update_b)
        await db_session.refresh(request_a)
        await db_session.refresh(request_b)

        # A scrubbed: text redacted, photo_ids NULLed.
        assert "Maria" not in update_a.body
        assert "Mueller" not in update_a.body
        assert update_a.photo_ids is None
        assert "Maria" not in request_a.reason
        assert "Mueller" not in request_a.reason

        # B untouched.
        assert "Bernd" in update_b.body
        assert "Schmidt" in update_b.body
        assert update_b.photo_ids is not None
        assert "Bernd" in request_b.reason
        assert "Schmidt" in request_b.reason
