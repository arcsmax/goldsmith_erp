# tests/unit/test_cost_change_service.py
"""
Unit tests for CostChangeService (V1.2 Task 5).

Covers:
- create: original_amount derived from CostWatchService's quote reference
  (never client-supplied), 409 when no referenceable Quote exists, delta
  math, 404 on missing order; supersedes NOTHING (fix round 1 — drafts
  coexist freely).
- send: creates+sends the linked CustomerUpdate(kind=cost_change), only
  valid from DRAFT (409 otherwise), 404 on missing request; sibling-SENT
  invariant — any OTHER SENT request for the same order is superseded in
  the same transaction (fix round 1), scoped per-order.
- record_response: evidence logging, only valid from SENT (409
  otherwise), sets approved/declined + method/evidence/responded_at/
  recorded_by, 404 on missing request.
- list_for_order: newest first.
- uq_cost_change_one_sent_per_order (security re-review fix): the DB
  partial unique index enforces at most one SENT request per order —
  direct-insert enforcement proof, per-order/per-status scoping, and the
  service-level IntegrityError -> SentCostChangeConflictError (409)
  mapping on the cross-row race path.

aiosmtplib is mocked at the same boundary as test_customer_update_service.py.
"""
from datetime import datetime, timedelta

import pytest

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    CostChangeRequest,
    CostChangeResponseMethod,
    CostChangeStatus,
    Order,
    Quote,
    QuoteStatus,
)
from goldsmith_erp.models.customer_update import (
    CostChangeCreate,
    CostChangeLineItem,
    CostChangeRecordResponse,
)
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.cost_change_service import (
    CostChangeNotFoundError,
    CostChangeService,
    InvalidCostChangeStateError,
    NoQuoteAvailableError,
    SentCostChangeConflictError,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)


class _CapturingSend:
    def __init__(self) -> None:
        self.sent_messages: list = []

    async def __call__(self, msg, **kwargs):
        self.sent_messages.append(msg)
        return None


async def _add_quote(
    db_session, *, order, customer, user, status: QuoteStatus, subtotal: float
) -> Quote:
    tax_amount = round(subtotal * 0.19, 2)
    quote = Quote(
        quote_number=f"KV-TEST-{order.id}-{status.value}",
        order_id=order.id,
        customer_id=customer.id,
        created_by=user.id,
        status=status,
        valid_until=datetime.utcnow() + timedelta(days=14),
        subtotal=subtotal,
        tax_rate=19.0,
        tax_amount=tax_amount,
        total=subtotal + tax_amount,
    )
    db_session.add(quote)
    await db_session.commit()
    await db_session.refresh(quote)
    return quote


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    async def test_raises_when_order_not_found(self, db_session, sample_user):
        with pytest.raises(ValueError, match="nicht gefunden"):
            await CostChangeService.create(
                db_session,
                999_999,
                CostChangeCreate(new_amount=100.0, reason="Zusaetzliche Arbeit noetig"),
                sample_user.id,
            )

    async def test_raises_no_quote_available_when_order_has_no_quote(
        self, db_session, sample_order, sample_user
    ):
        with pytest.raises(NoQuoteAvailableError):
            await CostChangeService.create(
                db_session,
                sample_order.id,
                CostChangeCreate(new_amount=100.0, reason="Zusaetzliche Arbeit noetig"),
                sample_user.id,
            )

    async def test_derives_original_amount_from_quote_net_subtotal(
        self, db_session, sample_order, sample_customer, sample_user
    ):
        await _add_quote(
            db_session,
            order=sample_order,
            customer=sample_customer,
            user=sample_user,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )

        cost_change = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(
                new_amount=1200.0, reason="Zusaetzliche Fassung fuer Stein noetig"
            ),
            sample_user.id,
        )

        assert cost_change.original_amount == 1000.0
        assert cost_change.new_amount == 1200.0
        assert cost_change.delta_percent == pytest.approx(20.0)
        assert cost_change.status == CostChangeStatus.DRAFT

    async def test_stores_line_items(
        self, db_session, sample_order, sample_customer, sample_user
    ):
        await _add_quote(
            db_session,
            order=sample_order,
            customer=sample_customer,
            user=sample_user,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )

        cost_change = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(
                new_amount=1150.0,
                reason="Zusaetzliche Fassung noetig",
                line_items=[
                    CostChangeLineItem(label="Fassung", amount=150.0, kind="add")
                ],
            ),
            sample_user.id,
        )

        assert cost_change.line_items == [
            {"label": "Fassung", "amount": 150.0, "kind": "add"}
        ]

    async def test_create_supersedes_nothing(
        self, db_session, sample_order, sample_customer, sample_user
    ):
        """Fix round 1: creation supersedes NOTHING — the sibling-SENT
        invariant is enforced at send-time. A pre-existing SENT request
        and a pre-existing draft must both survive a new create()
        untouched."""
        await _add_quote(
            db_session,
            order=sample_order,
            customer=sample_customer,
            user=sample_user,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )
        sent_sibling = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1100.0,
            delta_percent=10.0,
            reason="Bereits verschickte Anfrage",
            status=CostChangeStatus.SENT,
            created_by=sample_user.id,
        )
        draft_sibling = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1050.0,
            delta_percent=5.0,
            reason="Bestehender Entwurf",
            status=CostChangeStatus.DRAFT,
            created_by=sample_user.id,
        )
        db_session.add_all([sent_sibling, draft_sibling])
        await db_session.commit()
        await db_session.refresh(sent_sibling)
        await db_session.refresh(draft_sibling)

        await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(new_amount=1300.0, reason="Weitere neue Anfrage"),
            sample_user.id,
        )

        from sqlalchemy import select

        refetched_sent = (
            await db_session.execute(
                select(CostChangeRequest).where(CostChangeRequest.id == sent_sibling.id)
            )
        ).scalar_one()
        refetched_draft = (
            await db_session.execute(
                select(CostChangeRequest).where(
                    CostChangeRequest.id == draft_sibling.id
                )
            )
        ).scalar_one()
        assert refetched_sent.status == CostChangeStatus.SENT
        assert refetched_draft.status == CostChangeStatus.DRAFT


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


class TestSend:
    async def test_raises_not_found(self, db_session):
        with pytest.raises(CostChangeNotFoundError):
            await CostChangeService.send(db_session, 999_999, user_id=1)

    async def test_raises_invalid_state_when_not_draft(
        self, db_session, sample_order, sample_user
    ):
        cost_change = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1200.0,
            delta_percent=20.0,
            reason="Bereits verschickt",
            status=CostChangeStatus.SENT,
            created_by=sample_user.id,
        )
        db_session.add(cost_change)
        await db_session.commit()
        await db_session.refresh(cost_change)

        with pytest.raises(InvalidCostChangeStateError):
            await CostChangeService.send(db_session, cost_change.id, sample_user.id)

    async def test_concurrent_sends_only_one_wins_the_cas_claim(
        self, db_session, sample_order, sample_customer, sample_user, monkeypatch
    ):
        """Security/correctness (review fix — send-path race): two
        concurrent send() calls for the SAME DRAFT cost-change request
        must not both create+dispatch a linked CustomerUpdate. Exercised
        with two independent AsyncSession objects bound to the same
        underlying (file-backed) SQLite engine, raced via asyncio.gather
        — same pattern as
        test_customer_update_service.py's equivalent CAS test."""
        import asyncio

        from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

        _enable_smtp(monkeypatch)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())

        await _add_quote(
            db_session,
            order=sample_order,
            customer=sample_customer,
            user=sample_user,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )
        cost_change = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(new_amount=1200.0, reason="Zusaetzliche Fassung noetig"),
            sample_user.id,
        )

        session_b = _AsyncSession(bind=db_session.bind, expire_on_commit=False)
        try:
            results = await asyncio.gather(
                CostChangeService.send(db_session, cost_change.id, sample_user.id),
                CostChangeService.send(session_b, cost_change.id, sample_user.id),
                return_exceptions=True,
            )
        finally:
            await session_b.close()

        successes = [r for r in results if not isinstance(r, BaseException)]
        errors = [r for r in results if isinstance(r, BaseException)]

        assert len(successes) == 1, results
        assert len(errors) == 1, results
        assert isinstance(errors[0], InvalidCostChangeStateError)
        assert successes[0].delivered is True

    async def test_creates_and_sends_linked_customer_update(
        self, db_session, sample_order, sample_customer, sample_user, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        capture = _CapturingSend()
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

        await _add_quote(
            db_session,
            order=sample_order,
            customer=sample_customer,
            user=sample_user,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )
        cost_change = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(
                new_amount=1200.0, reason="Zusaetzliche Fassung noetig fuer Stein"
            ),
            sample_user.id,
        )

        result = await CostChangeService.send(
            db_session, cost_change.id, sample_user.id
        )

        assert result.delivered is True
        assert len(capture.sent_messages) == 1

        from sqlalchemy import select

        refetched = (
            await db_session.execute(
                select(CostChangeRequest).where(CostChangeRequest.id == cost_change.id)
            )
        ).scalar_one()
        assert refetched.status == CostChangeStatus.SENT

    async def test_send_supersedes_sibling_sent_request(
        self, db_session, sample_order, sample_customer, sample_user, monkeypatch
    ):
        """Fix round 1 sibling-SENT invariant: two drafts, send A, then
        send B — A must become SUPERSEDED (inside B's send transaction),
        B is SENT; at most one live notice per order."""
        _enable_smtp(monkeypatch)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())

        await _add_quote(
            db_session,
            order=sample_order,
            customer=sample_customer,
            user=sample_user,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )
        draft_a = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(new_amount=1100.0, reason="Erste Anfrage (Entwurf A)"),
            sample_user.id,
        )
        draft_b = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(new_amount=1300.0, reason="Zweite Anfrage (Entwurf B)"),
            sample_user.id,
        )

        await CostChangeService.send(db_session, draft_a.id, sample_user.id)
        await CostChangeService.send(db_session, draft_b.id, sample_user.id)

        from sqlalchemy import select

        refetched_a = (
            await db_session.execute(
                select(CostChangeRequest).where(CostChangeRequest.id == draft_a.id)
            )
        ).scalar_one()
        refetched_b = (
            await db_session.execute(
                select(CostChangeRequest).where(CostChangeRequest.id == draft_b.id)
            )
        ).scalar_one()
        assert refetched_a.status == CostChangeStatus.SUPERSEDED
        assert refetched_b.status == CostChangeStatus.SENT

    async def test_record_response_on_superseded_request_returns_conflict(
        self, db_session, sample_order, sample_customer, sample_user, monkeypatch
    ):
        """After A is superseded by sending B, record_response on A must
        raise InvalidCostChangeStateError (409) — only SENT accepts a
        customer response."""
        _enable_smtp(monkeypatch)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())

        await _add_quote(
            db_session,
            order=sample_order,
            customer=sample_customer,
            user=sample_user,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )
        draft_a = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(new_amount=1100.0, reason="Erste Anfrage (Entwurf A)"),
            sample_user.id,
        )
        draft_b = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(new_amount=1300.0, reason="Zweite Anfrage (Entwurf B)"),
            sample_user.id,
        )
        await CostChangeService.send(db_session, draft_a.id, sample_user.id)
        await CostChangeService.send(db_session, draft_b.id, sample_user.id)

        with pytest.raises(InvalidCostChangeStateError):
            await CostChangeService.record_response(
                db_session,
                draft_a.id,
                CostChangeRecordResponse(
                    status="approved",
                    response_method=CostChangeResponseMethod.EMAIL_REPLY,
                    response_evidence="Antwort auf die alte, ersetzte Anfrage",
                ),
                sample_user.id,
            )

    async def test_send_does_not_supersede_sent_requests_of_other_orders(
        self, db_session, sample_order, sample_customer, sample_user, monkeypatch
    ):
        """The sibling supersede is scoped to the SAME order — a SENT
        request on a different order must not be touched."""
        _enable_smtp(monkeypatch)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())

        other_order = Order(title="Anderer Auftrag", customer_id=sample_customer.id)
        db_session.add(other_order)
        await db_session.commit()
        await db_session.refresh(other_order)
        other_sent = CostChangeRequest(
            order_id=other_order.id,
            original_amount=500.0,
            new_amount=600.0,
            delta_percent=20.0,
            reason="Anfrage am anderen Auftrag",
            status=CostChangeStatus.SENT,
            created_by=sample_user.id,
        )
        db_session.add(other_sent)
        await db_session.commit()
        await db_session.refresh(other_sent)

        await _add_quote(
            db_session,
            order=sample_order,
            customer=sample_customer,
            user=sample_user,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )
        draft = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(new_amount=1300.0, reason="Anfrage am Hauptauftrag"),
            sample_user.id,
        )
        await CostChangeService.send(db_session, draft.id, sample_user.id)

        from sqlalchemy import select

        refetched_other = (
            await db_session.execute(
                select(CostChangeRequest).where(CostChangeRequest.id == other_sent.id)
            )
        ).scalar_one()
        assert refetched_other.status == CostChangeStatus.SENT


# ---------------------------------------------------------------------------
# uq_cost_change_one_sent_per_order — DB-level single-live-notice invariant
# (security re-review fix: the FOR UPDATE sibling scan does NOT serialize
# the cross-row race under READ COMMITTED; the partial unique index is the
# real invariant)
# ---------------------------------------------------------------------------


class TestOneSentPerOrderIndex:
    async def test_db_index_rejects_second_sent_row_for_same_order(
        self, db_session, sample_order, sample_user
    ):
        """Direct-insert proof of enforcement: two SENT rows for one order
        must violate the partial unique index regardless of any
        service-level logic."""
        from sqlalchemy.exc import IntegrityError

        first = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1100.0,
            delta_percent=10.0,
            reason="Erste versendete Anfrage",
            status=CostChangeStatus.SENT,
            created_by=sample_user.id,
        )
        db_session.add(first)
        await db_session.commit()

        second = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1200.0,
            delta_percent=20.0,
            reason="Zweite versendete Anfrage",
            status=CostChangeStatus.SENT,
            created_by=sample_user.id,
        )
        db_session.add(second)
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_db_index_allows_sent_rows_on_different_orders(
        self, db_session, sample_order, sample_customer, sample_user
    ):
        """The invariant is per-order — SENT rows on two different orders
        must coexist."""
        other_order = Order(title="Anderer Auftrag", customer_id=sample_customer.id)
        db_session.add(other_order)
        await db_session.commit()
        await db_session.refresh(other_order)

        for order_id in (sample_order.id, other_order.id):
            db_session.add(
                CostChangeRequest(
                    order_id=order_id,
                    original_amount=1000.0,
                    new_amount=1100.0,
                    delta_percent=10.0,
                    reason="Versendete Anfrage pro Auftrag",
                    status=CostChangeStatus.SENT,
                    created_by=sample_user.id,
                )
            )
        await db_session.commit()  # must not raise

    async def test_db_index_allows_many_non_sent_rows_per_order(
        self, db_session, sample_order, sample_user
    ):
        """Partial index scoping: DRAFT/SUPERSEDED/APPROVED rows are
        outside the WHERE clause and may pile up freely."""
        for status in (
            CostChangeStatus.DRAFT,
            CostChangeStatus.DRAFT,
            CostChangeStatus.SUPERSEDED,
            CostChangeStatus.APPROVED,
        ):
            db_session.add(
                CostChangeRequest(
                    order_id=sample_order.id,
                    original_amount=1000.0,
                    new_amount=1100.0,
                    delta_percent=10.0,
                    reason="Nicht-versendete Anfrage",
                    status=status,
                    created_by=sample_user.id,
                )
            )
        await db_session.commit()  # must not raise

    async def test_send_maps_index_conflict_to_409_conflict_error(
        self, db_session, sample_order, sample_customer, sample_user, monkeypatch
    ):
        """Cross-row race loser path, reached deterministically: bypass the
        sibling supersede (simulating READ COMMITTED's invisible-sibling
        snapshot — the exact condition the security re-review proved) so
        send()'s CAS trips the partial unique index. The IntegrityError
        must surface as the typed SentCostChangeConflictError (409 via
        the router's InvalidCostChangeStateError mapping), and the
        transaction must roll back cleanly: sibling still SENT, target
        still DRAFT, no linked CustomerUpdate created. Mirrors
        no_go_service's _add_no_go_bypassing_app_check precedent."""
        from sqlalchemy import select

        from goldsmith_erp.db.models import CustomerUpdate

        _enable_smtp(monkeypatch)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())

        sent_sibling = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1100.0,
            delta_percent=10.0,
            reason="Bereits versendete Anfrage",
            status=CostChangeStatus.SENT,
            created_by=sample_user.id,
        )
        db_session.add(sent_sibling)
        await db_session.commit()
        await db_session.refresh(sent_sibling)

        await _add_quote(
            db_session,
            order=sample_order,
            customer=sample_customer,
            user=sample_user,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )
        draft = await CostChangeService.create(
            db_session,
            sample_order.id,
            CostChangeCreate(new_amount=1300.0, reason="Konkurrierende Anfrage"),
            sample_user.id,
        )
        # Captured up front: the CAS's rolled-back transaction expires
        # every ORM object in this session — attribute access afterwards
        # would raise MissingGreenlet (async lazy-load outside a greenlet
        # context; same trap documented in test_no_go_service).
        sibling_id = sent_sibling.id
        draft_id = draft.id

        async def _no_supersede(db, cost_change):
            return None

        monkeypatch.setattr(
            CostChangeService,
            "_supersede_sent_siblings",
            staticmethod(_no_supersede),
        )

        with pytest.raises(SentCostChangeConflictError) as exc_info:
            await CostChangeService.send(db_session, draft_id, sample_user.id)

        # Typed error, catchable by the router's existing 409 mapping,
        # with the fixed ID-free message.
        assert isinstance(exc_info.value, InvalidCostChangeStateError)
        assert "bereits eine Kostenänderung versendet" in str(exc_info.value)

        # Full rollback: nothing changed, nothing was created.
        refetched_sibling = (
            await db_session.execute(
                select(CostChangeRequest).where(CostChangeRequest.id == sibling_id)
            )
        ).scalar_one()
        refetched_draft = (
            await db_session.execute(
                select(CostChangeRequest).where(CostChangeRequest.id == draft_id)
            )
        ).scalar_one()
        linked_updates = (
            (
                await db_session.execute(
                    select(CustomerUpdate).where(
                        CustomerUpdate.cost_change_request_id == draft_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert refetched_sibling.status == CostChangeStatus.SENT
        assert refetched_draft.status == CostChangeStatus.DRAFT
        assert linked_updates == []


# ---------------------------------------------------------------------------
# record_response
# ---------------------------------------------------------------------------


class TestRecordResponse:
    async def test_raises_not_found(self, db_session, sample_user):
        with pytest.raises(CostChangeNotFoundError):
            await CostChangeService.record_response(
                db_session,
                999_999,
                CostChangeRecordResponse(
                    status="approved",
                    response_method=CostChangeResponseMethod.EMAIL_REPLY,
                    response_evidence="Kundin hat per Email zugestimmt",
                ),
                sample_user.id,
            )

    async def test_raises_invalid_state_when_not_sent(
        self, db_session, sample_order, sample_user
    ):
        cost_change = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1200.0,
            delta_percent=20.0,
            reason="Noch nicht verschickt",
            status=CostChangeStatus.DRAFT,
            created_by=sample_user.id,
        )
        db_session.add(cost_change)
        await db_session.commit()
        await db_session.refresh(cost_change)

        with pytest.raises(InvalidCostChangeStateError):
            await CostChangeService.record_response(
                db_session,
                cost_change.id,
                CostChangeRecordResponse(
                    status="approved",
                    response_method=CostChangeResponseMethod.IN_PERSON,
                    response_evidence="Muendlich zugestimmt",
                ),
                sample_user.id,
            )

    async def test_records_approval(self, db_session, sample_order, sample_user):
        cost_change = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1200.0,
            delta_percent=20.0,
            reason="Verschickt, wartet auf Antwort",
            status=CostChangeStatus.SENT,
            created_by=sample_user.id,
        )
        db_session.add(cost_change)
        await db_session.commit()
        await db_session.refresh(cost_change)

        updated = await CostChangeService.record_response(
            db_session,
            cost_change.id,
            CostChangeRecordResponse(
                status="approved",
                response_method=CostChangeResponseMethod.EMAIL_REPLY,
                response_evidence="Kundin hat per Email 'Ich stimme zu' geschrieben",
            ),
            sample_user.id,
        )

        assert updated.status == CostChangeStatus.APPROVED
        assert updated.response_method == CostChangeResponseMethod.EMAIL_REPLY
        assert updated.responded_at is not None
        assert updated.recorded_by == sample_user.id

    async def test_records_decline(self, db_session, sample_order, sample_user):
        cost_change = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1200.0,
            delta_percent=20.0,
            reason="Verschickt, wartet auf Antwort",
            status=CostChangeStatus.SENT,
            created_by=sample_user.id,
        )
        db_session.add(cost_change)
        await db_session.commit()
        await db_session.refresh(cost_change)

        updated = await CostChangeService.record_response(
            db_session,
            cost_change.id,
            CostChangeRecordResponse(
                status="declined",
                response_method=CostChangeResponseMethod.PHONE,
                response_evidence="Kundin hat telefonisch abgelehnt",
            ),
            sample_user.id,
        )

        assert updated.status == CostChangeStatus.DECLINED


# ---------------------------------------------------------------------------
# list_for_order
# ---------------------------------------------------------------------------


class TestListForOrder:
    async def test_returns_newest_first(self, db_session, sample_order, sample_user):
        first = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1100.0,
            delta_percent=10.0,
            reason="Erste Anfrage",
            status=CostChangeStatus.SUPERSEDED,
            created_by=sample_user.id,
        )
        db_session.add(first)
        await db_session.commit()
        second = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1300.0,
            delta_percent=30.0,
            reason="Zweite Anfrage",
            status=CostChangeStatus.DRAFT,
            created_by=sample_user.id,
        )
        db_session.add(second)
        await db_session.commit()
        await db_session.refresh(first)
        await db_session.refresh(second)

        results = await CostChangeService.list_for_order(
            db_session, sample_order.id, sample_user.id
        )

        assert [r.id for r in results] == [second.id, first.id]
