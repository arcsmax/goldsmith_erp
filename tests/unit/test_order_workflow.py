"""W2-07: order lifecycle transition table (ARCH-01, BE-06, DOM-13, DOM-46).

Covers every (from, to) pair of ``OrderStatusEnum`` against the explicit
table in ``services/order_workflow.py``, the reason guards for ``on_hold``
and ``cancelled``, the 409 detail (German, lists the allowed next
statuses), the helper predicates, and the async ``transition()`` writing
an ``OrderEvent`` row.
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from goldsmith_erp.db.models import Order, OrderEvent, OrderStatusEnum
from goldsmith_erp.services import order_workflow as wf
from goldsmith_erp.services.order_workflow import (
    ALLOWED_TRANSITIONS,
    ORDER_STATUS_LABELS,
    InvalidStatusTransitionError,
    StatusTransitionInputError,
    TransitionReasonRequiredError,
    allowed_next_statuses,
    check_transition,
    counts_for_deadline,
    is_active_status,
    is_transition_allowed,
)

S = OrderStatusEnum

PRODUCTION = {
    S.IN_PROGRESS,
    S.WAITING_FOR_FITTING,
    S.FITTING_DONE,
    S.READY_FOR_SETTING,
    S.QUALITY_CHECK,
}

# The expected matrix, written out independently of the implementation.
EXPECTED: dict[OrderStatusEnum, set[OrderStatusEnum]] = {
    S.DRAFT: {S.CONFIRMED, S.CANCELLED},
    S.NEW: {S.DRAFT, S.CONFIRMED, S.ON_HOLD, S.CANCELLED} | PRODUCTION,
    S.CONFIRMED: {
        S.DRAFT,
        S.IN_PROGRESS,
        S.WAITING_FOR_FITTING,
        S.ON_HOLD,
        S.CANCELLED,
    },
    **{
        p: (PRODUCTION - {p}) | {S.COMPLETED, S.ON_HOLD, S.CANCELLED}
        for p in PRODUCTION
    },
    S.ON_HOLD: {S.CONFIRMED, S.CANCELLED} | PRODUCTION,
    S.COMPLETED: {S.DELIVERED, S.QUALITY_CHECK, S.IN_PROGRESS},
    S.DELIVERED: set(),
    S.CANCELLED: {S.DRAFT},
}

ALL_PAIRS = [(a, b) for a, b in itertools.product(S, S) if a is not b]
ALLOWED_PAIRS = [(a, b) for a, b in ALL_PAIRS if b in EXPECTED[a]]
FORBIDDEN_PAIRS = [(a, b) for a, b in ALL_PAIRS if b not in EXPECTED[a]]


def _reason_for(target: OrderStatusEnum) -> str | None:
    return "Wartet auf Stein" if target in (S.ON_HOLD, S.CANCELLED) else None


# --------------------------------------------------------------------------- #
# Table shape
# --------------------------------------------------------------------------- #


def test_new_enum_values_exist():
    assert S.ON_HOLD.value == "on_hold"
    assert S.CANCELLED.value == "cancelled"


def test_table_covers_every_status():
    assert set(ALLOWED_TRANSITIONS) == set(S)


def test_table_matches_expected_matrix():
    assert {k: set(v) for k, v in ALLOWED_TRANSITIONS.items()} == EXPECTED


def test_every_status_has_a_german_label():
    assert set(ORDER_STATUS_LABELS) == set(S)
    assert ORDER_STATUS_LABELS[S.ON_HOLD] == "Pausiert"
    assert ORDER_STATUS_LABELS[S.CANCELLED] == "Storniert"
    assert ORDER_STATUS_LABELS[S.READY_FOR_SETTING] == "Bereit zum Fassen"


@pytest.mark.parametrize("current,target", ALLOWED_PAIRS)
def test_allowed_transition_passes(current, target):
    assert is_transition_allowed(current, target)
    check_transition(current, target, reason=_reason_for(target))


@pytest.mark.parametrize("current,target", FORBIDDEN_PAIRS)
def test_forbidden_transition_raises_409(current, target):
    assert not is_transition_allowed(current, target)
    with pytest.raises(InvalidStatusTransitionError) as exc:
        check_transition(current, target, reason="irgendwas")
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert detail["code"] == "INVALID_STATUS_TRANSITION"
    assert detail["from_status"] == current.value
    assert detail["to_status"] == target.value
    assert detail["allowed"] == [s.value for s in allowed_next_statuses(current)]


def test_self_transition_is_a_noop_not_an_error():
    for status in S:
        check_transition(status, status)


# --------------------------------------------------------------------------- #
# Guards named in the fix plan
# --------------------------------------------------------------------------- #


def test_delivered_to_in_progress_is_409_with_german_message():
    with pytest.raises(InvalidStatusTransitionError) as exc:
        check_transition(S.DELIVERED, S.IN_PROGRESS)
    message = exc.value.detail["message"]
    assert "Ausgeliefert" in message
    assert "In Bearbeitung" in message
    assert "keine weiteren Statuswechsel" in message


def test_cannot_deliver_without_completed():
    for status in S:
        if status in (S.COMPLETED, S.DELIVERED):
            continue
        assert not is_transition_allowed(status, S.DELIVERED), status


def test_cannot_cancel_a_delivered_order():
    assert not is_transition_allowed(S.DELIVERED, S.CANCELLED)


def test_409_message_lists_allowed_next_statuses_in_german():
    with pytest.raises(InvalidStatusTransitionError) as exc:
        check_transition(S.DRAFT, S.COMPLETED)
    message = exc.value.detail["message"]
    assert "Bestätigt" in message and "Storniert" in message
    assert exc.value.detail["allowed_labels"] == ["Bestätigt", "Storniert"]


@pytest.mark.parametrize("target", [S.ON_HOLD, S.CANCELLED])
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_reason_required_for_hold_and_cancel(target, reason):
    with pytest.raises(TransitionReasonRequiredError) as exc:
        check_transition(S.IN_PROGRESS, target, reason=reason)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "STATUS_REASON_REQUIRED"
    assert "Grund" in exc.value.detail["message"]


def test_resume_date_in_the_past_is_rejected():
    with pytest.raises(StatusTransitionInputError) as exc:
        check_transition(
            S.IN_PROGRESS,
            S.ON_HOLD,
            reason="Wartet auf Guss",
            resume_date=date.today() - timedelta(days=1),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "STATUS_RESUME_DATE_INVALID"


# --------------------------------------------------------------------------- #
# Predicates for dashboard / notifications
# --------------------------------------------------------------------------- #


def test_is_active_status():
    assert not is_active_status(S.CANCELLED)
    assert not is_active_status(S.DELIVERED)
    assert is_active_status(S.ON_HOLD)
    assert is_active_status(S.IN_PROGRESS)
    assert is_active_status("in_progress")


def test_counts_for_deadline():
    for status in (S.ON_HOLD, S.CANCELLED, S.COMPLETED, S.DELIVERED):
        assert not counts_for_deadline(status), status
    for status in PRODUCTION | {S.CONFIRMED, S.DRAFT, S.NEW}:
        assert counts_for_deadline(status), status
    assert not counts_for_deadline("on_hold")


def test_sql_sets_match_predicates():
    assert set(wf.NO_DEADLINE_STATUSES) == {s for s in S if not counts_for_deadline(s)}
    assert set(wf.CLOSED_STATUSES) == {s for s in S if not is_active_status(s)}


# --------------------------------------------------------------------------- #
# transition() against the DB
# --------------------------------------------------------------------------- #


async def _order(db, customer, status=S.IN_PROGRESS, **kw) -> Order:
    order = Order(title="Ring", customer_id=customer.id, status=status, **kw)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _events(db, order_id):
    result = await db.execute(
        select(OrderEvent)
        .where(OrderEvent.order_id == order_id)
        .order_by(OrderEvent.id)
    )
    return result.scalars().all()


async def test_transition_sets_status_and_writes_event(
    db_session, sample_customer, sample_user
):
    order = await _order(db_session, sample_customer)
    event = await wf.transition(
        db_session, order, S.QUALITY_CHECK, sample_user, meta={"origin": "test"}
    )
    await db_session.commit()

    assert order.status is S.QUALITY_CHECK
    events = await _events(db_session, order.id)
    assert len(events) == 1 and events[0].id == event.id
    assert events[0].from_status == "in_progress"
    assert events[0].to_status == "quality_check"
    assert events[0].user_id == sample_user.id
    assert events[0].meta == {"origin": "test"}


async def test_transition_to_on_hold_stores_reason_and_resume_date(
    db_session, sample_customer, sample_user
):
    order = await _order(db_session, sample_customer)
    resume = date.today() + timedelta(days=7)
    await wf.transition(
        db_session,
        order,
        S.ON_HOLD,
        sample_user.id,
        reason="Wartet auf Stein",
        resume_date=resume,
    )
    await db_session.commit()
    assert order.hold_reason == "Wartet auf Stein"
    assert order.resume_date == resume
    events = await _events(db_session, order.id)
    assert events[-1].reason == "Wartet auf Stein"
    assert events[-1].meta["resume_date"] == resume.isoformat()

    # Resuming clears the hold fields but keeps the history.
    await wf.transition(db_session, order, S.IN_PROGRESS, sample_user)
    await db_session.commit()
    assert order.hold_reason is None and order.resume_date is None
    assert len(await _events(db_session, order.id)) == 2


async def test_transition_to_cancelled_stores_cancel_reason(
    db_session, sample_customer, sample_user
):
    order = await _order(db_session, sample_customer, status=S.CONFIRMED)
    await wf.transition(
        db_session, order, S.CANCELLED, sample_user, reason="Kunde storniert"
    )
    await db_session.commit()
    assert order.cancel_reason == "Kunde storniert"


async def test_forbidden_transition_writes_nothing(
    db_session, sample_customer, sample_user
):
    order = await _order(db_session, sample_customer, status=S.DELIVERED)
    with pytest.raises(InvalidStatusTransitionError):
        await wf.transition(db_session, order, S.IN_PROGRESS, sample_user)
    await db_session.commit()
    await db_session.refresh(order)
    assert order.status is S.DELIVERED
    assert await _events(db_session, order.id) == []


async def test_same_status_transition_writes_no_event(
    db_session, sample_customer, sample_user
):
    order = await _order(db_session, sample_customer)
    assert await wf.transition(db_session, order, S.IN_PROGRESS, sample_user) is None
    await db_session.commit()
    assert await _events(db_session, order.id) == []


async def test_transition_to_completed_enforces_punzierung(
    db_session, sample_customer, sample_user
):
    from goldsmith_erp.services.order_service import PunzierungRequiredError

    order = await _order(db_session, sample_customer, alloy="750")
    with pytest.raises(PunzierungRequiredError):
        await wf.transition(db_session, order, S.COMPLETED, sample_user)
    await wf.transition(
        db_session, order, S.COMPLETED, sample_user, pending_marks=["750"]
    )
    await db_session.commit()
    assert order.status is S.COMPLETED


async def test_record_creation_writes_initial_event(
    db_session, sample_customer, sample_user
):
    order = await _order(db_session, sample_customer, status=S.DRAFT)
    await wf.record_creation(db_session, order, sample_user)
    await db_session.commit()
    events = await _events(db_session, order.id)
    assert len(events) == 1
    assert events[0].from_status is None
    assert events[0].to_status == "draft"
