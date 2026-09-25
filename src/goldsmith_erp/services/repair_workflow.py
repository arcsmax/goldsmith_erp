"""Repair lifecycle: transition table, events and job sync (ARCH phase 5).

The repair counterpart of ``services/order_workflow.py``. Every
``RepairJob.status`` write goes through :func:`transition`, which checks
:data:`ALLOWED_TRANSITIONS`, sets the status, writes an ``order_events`` row
with ``repair_job_id`` + ``job_id`` set (``order_id`` NULL) and keeps the
repair's ``jobs`` row in sync. It never commits: the caller's
``transactional(db)`` writes the status, its event and the job together.

Repair events carry no free text (``reason`` stays NULL): a repair's notes
are not a GDPR scrub target on ``order_events``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Union, cast

from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import OrderEvent, RepairJob, RepairJobStatus, User
from goldsmith_erp.services.job_service import JobService

logger = logging.getLogger(__name__)

R = RepairJobStatus

REPAIR_STATUS_LABELS: Mapping[RepairJobStatus, str] = {
    R.RECEIVED: "Eingang",
    R.DIAGNOSED: "Diagnose",
    R.QUOTED: "Angebot erstellt",
    R.APPROVED: "Genehmigt",
    R.IN_REPAIR: "In Reparatur",
    R.QUALITY_CHECK: "Qualitätskontrolle",
    R.READY: "Abholbereit",
    R.PICKED_UP: "Abgeholt",
    R.CANCELLED: "Storniert",
}

#: Forward transitions per status (moved from repair_service, unchanged).
#: Cancelling is separate: allowed from every status in CANCELLABLE.
ALLOWED_TRANSITIONS: Mapping[RepairJobStatus, list[RepairJobStatus]] = {
    R.RECEIVED: [R.DIAGNOSED, R.CANCELLED],
    R.DIAGNOSED: [R.QUOTED, R.CANCELLED],
    R.QUOTED: [R.APPROVED, R.CANCELLED],
    R.APPROVED: [R.IN_REPAIR, R.CANCELLED],
    R.IN_REPAIR: [R.QUALITY_CHECK, R.CANCELLED],
    R.QUALITY_CHECK: [R.READY, R.IN_REPAIR],
    R.READY: [R.PICKED_UP],
    R.PICKED_UP: [],
    R.CANCELLED: [],
}

FINAL_STATUSES: frozenset[RepairJobStatus] = frozenset({R.PICKED_UP, R.CANCELLED})
CANCELLABLE: frozenset[RepairJobStatus] = frozenset(set(R) - FINAL_STATUSES)

StatusLike = Union[RepairJobStatus, str]


class InvalidRepairTransitionError(ValueError):
    """The table does not allow ``from -> to`` (routers map it to 422)."""

    def __init__(self, current: RepairJobStatus, target: RepairJobStatus) -> None:
        allowed = [s.value for s in ALLOWED_TRANSITIONS.get(current, [])]
        super().__init__(
            f"Statuswechsel von '{current.value}' nach '{target.value}' "
            f"ist nicht erlaubt. Erlaubt: {allowed}"
        )
        self.current = current
        self.target = target


def _coerce(status: StatusLike) -> RepairJobStatus:
    return status if isinstance(status, RepairJobStatus) else RepairJobStatus(status)


def label_for(status: StatusLike) -> str:
    return REPAIR_STATUS_LABELS[_coerce(status)]


def is_transition_allowed(current: StatusLike, target: StatusLike) -> bool:
    current_status, target_status = _coerce(current), _coerce(target)
    if target_status is R.CANCELLED:
        return current_status in CANCELLABLE
    return target_status in ALLOWED_TRANSITIONS.get(current_status, [])


def check_transition(current: StatusLike, target: StatusLike) -> None:
    current_status, target_status = _coerce(current), _coerce(target)
    if not is_transition_allowed(current_status, target_status):
        raise InvalidRepairTransitionError(current_status, target_status)


def _user_id(user: Union[User, int, None]) -> Optional[int]:
    if user is None or isinstance(user, int):
        return user
    return cast(Optional[int], user.id)


async def _add_event(
    db: AsyncSession,
    repair: RepairJob,
    job_id: int,
    from_status: Optional[str],
    to_status: str,
    user: Union[User, int, None],
    meta: Optional[dict[str, Any]],
) -> OrderEvent:
    event = OrderEvent(
        order_id=None,
        repair_job_id=repair.id,
        job_id=job_id,
        from_status=from_status,
        to_status=to_status,
        user_id=_user_id(user),
        reason=None,
        created_at=datetime.now(timezone.utc),
        meta=meta or None,
    )
    db.add(event)
    await db.flush()
    return event


async def transition(
    db: AsyncSession,
    repair: RepairJob,
    new_status: StatusLike,
    user: Union[User, int, None] = None,
    *,
    meta: Optional[dict[str, Any]] = None,
    extra_updates: Optional[dict[str, Any]] = None,
) -> Optional[OrderEvent]:
    """Move ``repair`` to ``new_status``, add its event and sync the job.

    Raises :class:`InvalidRepairTransitionError` (a ``ValueError``). Same
    status is a no-op (returns ``None``). Does not commit.
    """
    row: Any = repair  # Column-style model
    current = _coerce(row.status)
    target = _coerce(new_status)
    if current is target:
        return None
    check_transition(current, target)
    row.status = target
    for field, value in (extra_updates or {}).items():
        setattr(row, field, value)
    job = await JobService.sync_repair(db, repair)
    event = await _add_event(
        db, repair, int(job.id), current.value, target.value, user, meta
    )
    logger.info(
        "Repair status transition",
        extra={
            "repair_id": row.id,
            "job_id": job.id,
            "from_status": current.value,
            "to_status": target.value,
            "user_id": event.user_id,
        },
    )
    return event


async def record_creation(
    db: AsyncSession,
    repair: RepairJob,
    user: Union[User, int, None] = None,
    *,
    meta: Optional[dict[str, Any]] = None,
) -> OrderEvent:
    """Create the job and the first event (``from_status`` NULL) of a repair."""
    job = await JobService.sync_repair(db, repair)
    row: Any = repair
    return await _add_event(
        db, repair, int(job.id), None, _coerce(row.status).value, user, meta
    )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "CANCELLABLE",
    "InvalidRepairTransitionError",
    "REPAIR_STATUS_LABELS",
    "check_transition",
    "is_transition_allowed",
    "label_for",
    "record_creation",
    "transition",
]
