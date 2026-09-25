"""Order lifecycle: transition table, guards and event history (W2-07).

Findings ARCH-01, BE-06, DOM-13, DOM-46 (docs/review/2026-09-25/).

Single entry point for every ``Order.status`` write:
:func:`transition` checks the explicit :data:`ALLOWED_TRANSITIONS` table and
the guards, sets the status (plus hold/cancel fields), and adds an
:class:`~goldsmith_erp.db.models.OrderEvent` row to the caller's session.
It never commits: the caller's ``transactional(db)`` block commits the status
change and its event together, or rolls both back.

Callers: ``OrderService.update_order`` (PUT/PATCH ``/orders/{id}``, the new
``PATCH /orders/{id}/status`` and the scan flow's ``advance_status``) and
``QuoteService.convert_quote``. ``record_creation`` writes the first event
for a new order.

The table is permissive inside production (workshop stations vary per piece)
and strict at the edges: a draft must be confirmed first, only a completed
piece can be delivered, a delivered order is final, cancelling needs a
reason and a cancelled order can only be reopened as a draft. The later
lifecycle vs. production-stage split is W6-04.

Also the one backend source of German status labels (playbook 3.2) and the
predicates the dashboard and notification services use to leave paused and
cancelled orders out of deadline alarms and active counts.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional, Union, cast

from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.errors import ConflictError, DomainValidationError
from goldsmith_erp.db.models import Order, OrderEvent, OrderStatusEnum, User
from goldsmith_erp.services.hallmark_vocabulary import satisfies_hallmark_requirement

logger = logging.getLogger(__name__)

S = OrderStatusEnum

# --------------------------------------------------------------------------- #
# Labels (UI-UX-PLAYBOOK 3.2; on_hold / cancelled follow the repair wording)
# --------------------------------------------------------------------------- #

ORDER_STATUS_LABELS: dict[OrderStatusEnum, str] = {
    S.DRAFT: "Entwurf",
    S.NEW: "Neu",
    S.CONFIRMED: "Bestätigt",
    S.IN_PROGRESS: "In Bearbeitung",
    S.WAITING_FOR_FITTING: "Wartet auf Anprobe",
    S.FITTING_DONE: "Anprobe abgeschlossen",
    S.READY_FOR_SETTING: "Bereit zum Fassen",
    S.QUALITY_CHECK: "Qualitätskontrolle",
    S.COMPLETED: "Fertiggestellt",
    S.DELIVERED: "Ausgeliefert",
    S.ON_HOLD: "Pausiert",
    S.CANCELLED: "Storniert",
}

# --------------------------------------------------------------------------- #
# Transition table
# --------------------------------------------------------------------------- #

PRODUCTION_STATUSES: frozenset[OrderStatusEnum] = frozenset(
    {
        S.IN_PROGRESS,
        S.WAITING_FOR_FITTING,
        S.FITTING_DONE,
        S.READY_FOR_SETTING,
        S.QUALITY_CHECK,
    }
)

_LEAVE_PRODUCTION = frozenset({S.COMPLETED, S.ON_HOLD, S.CANCELLED})

ALLOWED_TRANSITIONS: Mapping[OrderStatusEnum, frozenset[OrderStatusEnum]] = {
    S.DRAFT: frozenset({S.CONFIRMED, S.CANCELLED}),
    # Legacy NEW (DOM-46): the data migration maps rows away; stay lenient
    # for any row written by old code during a rolling deploy.
    S.NEW: frozenset({S.DRAFT, S.CONFIRMED, S.ON_HOLD, S.CANCELLED})
    | PRODUCTION_STATUSES,
    S.CONFIRMED: frozenset(
        {S.DRAFT, S.IN_PROGRESS, S.WAITING_FOR_FITTING, S.ON_HOLD, S.CANCELLED}
    ),
    **{
        stage: (PRODUCTION_STATUSES - {stage}) | _LEAVE_PRODUCTION
        for stage in PRODUCTION_STATUSES
    },
    S.ON_HOLD: frozenset({S.CONFIRMED, S.CANCELLED}) | PRODUCTION_STATUSES,
    # Rework before pickup goes back to QC or the bench.
    S.COMPLETED: frozenset({S.DELIVERED, S.QUALITY_CHECK, S.IN_PROGRESS}),
    S.DELIVERED: frozenset(),
    # Reopen a mistaken cancellation; it has to be confirmed again.
    S.CANCELLED: frozenset({S.DRAFT}),
}

REASON_REQUIRED: frozenset[OrderStatusEnum] = frozenset({S.ON_HOLD, S.CANCELLED})

# --------------------------------------------------------------------------- #
# Predicates (dashboard_service / notification_service)
# --------------------------------------------------------------------------- #

#: Not counted as active work anywhere (lists, KPIs, workload).
CLOSED_STATUSES: frozenset[OrderStatusEnum] = frozenset({S.DELIVERED, S.CANCELLED})

#: No overdue / deadline alarms: finished, paused or cancelled.
NO_DEADLINE_STATUSES: frozenset[OrderStatusEnum] = frozenset(
    {S.COMPLETED, S.DELIVERED, S.CANCELLED, S.ON_HOLD}
)

StatusLike = Union[OrderStatusEnum, str]


def _coerce(status: StatusLike) -> OrderStatusEnum:
    return status if isinstance(status, OrderStatusEnum) else OrderStatusEnum(status)


def is_active_status(status: StatusLike) -> bool:
    """True unless the order is delivered or cancelled (on_hold is active)."""
    return _coerce(status) not in CLOSED_STATUSES


def counts_for_deadline(status: StatusLike) -> bool:
    """True when a deadline on an order in this status should raise alarms."""
    return _coerce(status) not in NO_DEADLINE_STATUSES


def label_for(status: StatusLike) -> str:
    return ORDER_STATUS_LABELS[_coerce(status)]


def allowed_next_statuses(current: StatusLike) -> list[OrderStatusEnum]:
    """Allowed targets from ``current`` in enum declaration order."""
    allowed = ALLOWED_TRANSITIONS[_coerce(current)]
    return [status for status in OrderStatusEnum if status in allowed]


def is_transition_allowed(current: StatusLike, target: StatusLike) -> bool:
    return _coerce(target) in ALLOWED_TRANSITIONS[_coerce(current)]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


def _join_labels(labels: Iterable[str]) -> str:
    return ", ".join(labels)


class InvalidStatusTransitionError(ConflictError):
    """409: the table does not allow ``from -> to``; lists the allowed ones."""

    def __init__(self, current: OrderStatusEnum, target: OrderStatusEnum) -> None:
        allowed = allowed_next_statuses(current)
        allowed_labels = [ORDER_STATUS_LABELS[s] for s in allowed]
        if allowed:
            hint = f"Erlaubt sind: {_join_labels(allowed_labels)}."
        else:
            hint = "Aus diesem Status sind keine weiteren Statuswechsel möglich."
        message = (
            f"Statuswechsel von „{ORDER_STATUS_LABELS[current]}“ nach "
            f"„{ORDER_STATUS_LABELS[target]}“ ist nicht erlaubt. {hint}"
        )
        extra = {
            "from_status": current.value,
            "to_status": target.value,
            "allowed": [s.value for s in allowed],
            "allowed_labels": allowed_labels,
        }
        super().__init__(
            message,
            code="order.invalid_transition",
            extra=extra,
            legacy_detail={
                "code": "INVALID_STATUS_TRANSITION",
                "message": message,
                **extra,
            },
        )


# Legacy UPPER_SNAKE code in ``detail.code`` -> new dotted slug.
_INPUT_ERROR_SLUGS: dict[str, str] = {
    "STATUS_REASON_REQUIRED": "order.reason_required",
    "STATUS_RESUME_DATE_INVALID": "order.resume_date_invalid",
}


class StatusTransitionInputError(DomainValidationError):
    """422: the transition is allowed but its inputs are missing or invalid."""

    def __init__(self, code: str, message: str, target: OrderStatusEnum) -> None:
        super().__init__(
            message,
            code=_INPUT_ERROR_SLUGS.get(code, "order.transition_input_invalid"),
            extra={"to_status": target.value},
            legacy_detail={
                "code": code,
                "message": message,
                "to_status": target.value,
            },
        )


class TransitionReasonRequiredError(StatusTransitionInputError):
    """422: on_hold / cancelled need a reason."""

    def __init__(self, target: OrderStatusEnum) -> None:
        super().__init__(
            "STATUS_REASON_REQUIRED",
            f"Für „{ORDER_STATUS_LABELS[target]}“ ist ein Grund erforderlich.",
            target,
        )


# --------------------------------------------------------------------------- #
# Hallmark ("Punzierung") guard (Slice 5 / M4 / R8 / A5.3, soft-gated by
# W2-09 / D-10), moved here from order_service so every status-write path
# runs it. order_service re-exports both names.
# --------------------------------------------------------------------------- #

_PUNZIERUNG_REQUIRED_TARGETS: frozenset[OrderStatusEnum] = frozenset({S.COMPLETED})


class PunzierungRequiredError(ConflictError):
    """409 when advancing to COMPLETED without a verified hallmark or a
    documented "nicht punziert" reason (M4, soft-gated by D-10).

    Structured detail so the frontend can open the PunzierungsCheckModal
    directly from the error response. ``code`` is the modern dotted slug
    (``order.hallmark_required``); ``legacy_detail.code`` keeps the
    original ``PUNZIERUNG_REQUIRED`` string so callers written against the
    hard-gate era keep working.
    """

    def __init__(self, *, order_id: int, alloy: str) -> None:
        message = (
            "Vor Status „Fertiggestellt“ muss entweder die Feingehalts-Punze "
            "bestätigt oder ein Grund für „nicht punziert“ dokumentiert werden."
        )
        super().__init__(
            message,
            code="order.hallmark_required",
            extra={"order_id": order_id, "alloy": alloy},
            legacy_detail={
                "code": "PUNZIERUNG_REQUIRED",
                "order_id": order_id,
                "alloy": alloy,
                "message": message,
            },
        )


def _check_punzierung_requirement(
    order: Any,
    new_status: Optional[OrderStatusEnum],
    pending_marks: Optional[list[Any]],
) -> None:
    """Refuse COMPLETED for an alloyed piece without a documented hallmark.

    Soft gate (D-10): satisfied by a real Feingehalt mark (for any alloy —
    see ``services/hallmark_vocabulary.satisfies_hallmark_requirement``) or
    by a ``"nicht punziert: <Grund>"`` entry recording why the piece was
    deliberately left unhallmarked. An additional mark alone (Meisterzeichen
    etc.) is not enough — "Meisterzeichen allein ist kein Reinheits-Audit".

    ``pending_marks`` are the marks the same request is about to write, so a
    caller can verify and complete in one round trip (scan flow). Orders
    without an alloy are exempt: the hallmark law only applies to pieces that
    carry a Feingehalts-Punze.
    """
    if new_status not in _PUNZIERUNG_REQUIRED_TARGETS:
        return
    if not order.alloy:
        return
    existing_marks = order.punzierung_verified_marks or []
    pending = pending_marks or []
    combined = [*existing_marks, *pending]
    if not satisfies_hallmark_requirement(combined):
        raise PunzierungRequiredError(order_id=order.id, alloy=order.alloy)


# --------------------------------------------------------------------------- #
# Validation + transition
# --------------------------------------------------------------------------- #


def _clean_reason(reason: Optional[str]) -> Optional[str]:
    if reason is None:
        return None
    stripped = reason.strip()
    return stripped or None


def check_transition(
    current: StatusLike,
    target: StatusLike,
    *,
    reason: Optional[str] = None,
    resume_date: Optional[date] = None,
) -> None:
    """Raise unless ``current -> target`` may happen with these inputs.

    Same status is a no-op and always passes (a form re-sending the
    unchanged status must not fail).
    """
    current_status, target_status = _coerce(current), _coerce(target)
    if current_status is target_status:
        return
    if not is_transition_allowed(current_status, target_status):
        raise InvalidStatusTransitionError(current_status, target_status)
    if target_status in REASON_REQUIRED and _clean_reason(reason) is None:
        raise TransitionReasonRequiredError(target_status)
    if resume_date is not None and target_status is S.ON_HOLD:
        if resume_date < date.today():
            raise StatusTransitionInputError(
                "STATUS_RESUME_DATE_INVALID",
                "Das Wiederaufnahme-Datum darf nicht in der Vergangenheit liegen.",
                target_status,
            )


def _user_id(user: Union[User, int, None]) -> Optional[int]:
    if user is None or isinstance(user, int):
        return user
    return cast(Optional[int], user.id)


def _apply_side_fields(
    order: Any,
    target: OrderStatusEnum,
    reason: Optional[str],
    resume_date: Optional[date],
) -> None:
    # ``order`` is typed Any: classic Column-style models type attributes as
    # Column[...] for mypy (same cast pattern as cost_change_service.py).
    if target is S.ON_HOLD:
        order.hold_reason = reason
        order.resume_date = resume_date
        return
    # Leaving (or never in) hold: the history keeps the old values.
    order.hold_reason = None
    order.resume_date = None
    if target is S.CANCELLED:
        order.cancel_reason = reason
    elif target is S.DRAFT:
        # Reopened after a cancellation.
        order.cancel_reason = None


async def transition(
    db: AsyncSession,
    order: Order,
    new_status: StatusLike,
    user: Union[User, int, None] = None,
    reason: Optional[str] = None,
    *,
    resume_date: Optional[date] = None,
    meta: Optional[dict[str, Any]] = None,
    pending_marks: Optional[list[Any]] = None,
) -> Optional[OrderEvent]:
    """Move ``order`` to ``new_status`` and add the matching event row.

    Does not commit; run it inside the caller's ``transactional(db)`` so the
    status and its event are written together or not at all. Returns
    ``None`` (and writes nothing) when the status does not change.

    Raises :class:`InvalidStatusTransitionError` (409),
    :class:`StatusTransitionInputError` (422) or
    :class:`PunzierungRequiredError` (409).
    """
    row: Any = order  # Column-style model, see _apply_side_fields
    target = _coerce(new_status)
    current = _coerce(row.status)
    clean_reason = _clean_reason(reason)
    check_transition(current, target, reason=clean_reason, resume_date=resume_date)
    if current is target:
        return None
    _check_punzierung_requirement(order, target, pending_marks)

    row.status = target
    _apply_side_fields(row, target, clean_reason, resume_date)

    event_meta: dict[str, Any] = dict(meta or {})
    if target is S.ON_HOLD and resume_date is not None:
        event_meta["resume_date"] = resume_date.isoformat()
    event = OrderEvent(
        order_id=order.id,
        from_status=current.value,
        to_status=target.value,
        user_id=_user_id(user),
        reason=clean_reason,
        created_at=datetime.utcnow(),
        meta=event_meta or None,
    )
    db.add(event)
    await db.flush()
    logger.info(
        "Order status transition",
        extra={
            "order_id": order.id,
            "from_status": current.value,
            "to_status": target.value,
            "user_id": event.user_id,
        },
    )
    return event


async def record_creation(
    db: AsyncSession,
    order: Order,
    user: Union[User, int, None] = None,
    *,
    meta: Optional[dict[str, Any]] = None,
) -> OrderEvent:
    """Add the first event (``from_status`` NULL) for a just-flushed order."""
    event = OrderEvent(
        order_id=order.id,
        from_status=None,
        to_status=_coerce(cast(Any, order).status).value,
        user_id=_user_id(user),
        created_at=datetime.utcnow(),
        meta=meta,
    )
    db.add(event)
    await db.flush()
    return event
