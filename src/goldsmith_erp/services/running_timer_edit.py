"""Edit a RUNNING time entry (activity, order, location, notes, start time).

The owner wants to correct a timer while it runs: wrong activity picked,
wrong job, started five minutes late. ``PATCH /time-tracking/{entry_id}``
lands here (ownership is checked by the router: owner or ADMIN).

Every applied change appends one line to the entry's change log. There is
no ``edit_log`` column (and db/models is not touched for this), so the log
lives in ``notes`` below :data:`EDIT_LOG_MARKER`. The client only ever
edits the text above the marker; the service keeps the log part, so a
PATCH cannot rewrite or drop earlier log lines.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, cast

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from goldsmith_erp.core.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from goldsmith_erp.core.timeutil import ensure_utc, format_local, utcnow
from goldsmith_erp.db.models import Activity as ActivityModel
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.models import TimeEntry as TimeEntryModel
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.models.time_entry import RunningTimeEntryEdit

logger = logging.getLogger(__name__)

EDIT_LOG_MARKER = "--- Änderungsprotokoll ---"
MAX_START_AGE = timedelta(hours=24)
# Client clocks drift; a start a few seconds "in the future" is a tap on now.
FUTURE_TOLERANCE = timedelta(minutes=1)
TIME_FORMAT = "%H:%M"


@dataclass(frozen=True)
class RunningEditResult:
    entry_id: str
    changes: Tuple[str, ...]
    changed_fields: Tuple[str, ...]


def split_notes(notes: Optional[str]) -> Tuple[str, str]:
    """``(user_text, edit_log)`` of a stored notes value."""
    if not notes:
        return "", ""
    head, sep, tail = notes.partition(EDIT_LOG_MARKER)
    if not sep:
        return notes, ""
    return head.rstrip("\n"), tail.strip("\n")


def join_notes(user_text: str, edit_log: str) -> Optional[str]:
    if not edit_log:
        return user_text or None
    prefix = f"{user_text}\n\n" if user_text else ""
    return f"{prefix}{EDIT_LOG_MARKER}\n{edit_log}"


async def _load_running(db: AsyncSession, entry_id: str) -> TimeEntryModel:
    result = await db.execute(
        select(TimeEntryModel).where(TimeEntryModel.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError(
            "Time entry not found",
            code="time_entry.not_found",
            extra={"entry_id": entry_id},
        )
    if entry.end_time is not None:
        raise ConflictError(
            "Diese Zeiterfassung ist bereits gestoppt und kann hier nicht "
            "mehr bearbeitet werden.",
            code="time_entry.not_running",
            extra={"entry_id": entry_id},
        )
    return entry


async def _require_activity(db: AsyncSession, activity_id: int) -> None:
    found = await db.execute(
        select(ActivityModel.id).where(ActivityModel.id == activity_id).limit(1)
    )
    if found.scalar_one_or_none() is None:
        raise NotFoundError(
            "Aktivität nicht gefunden.",
            code="activity.not_found",
            extra={"activity_id": activity_id},
        )


async def _require_order(db: AsyncSession, order_id: int) -> None:
    found = await db.execute(
        select(OrderModel.id)
        .where(OrderModel.id == order_id, OrderModel.is_deleted.isnot(True))
        .limit(1)
    )
    if found.scalar_one_or_none() is None:
        raise NotFoundError(
            f"Auftrag #{order_id} nicht gefunden.",
            code="order.not_found",
            extra={"order_id": order_id},
        )


async def _previous_end(db: AsyncSession, entry: TimeEntryModel) -> Optional[datetime]:
    """End of the user's latest other (stopped) entry."""
    result = await db.execute(
        select(func.max(TimeEntryModel.end_time)).where(
            TimeEntryModel.user_id == entry.user_id,
            TimeEntryModel.id != entry.id,
            TimeEntryModel.end_time.isnot(None),
        )
    )
    value = result.scalar_one_or_none()
    return ensure_utc(value) if value is not None else None


async def validate_start_time(
    db: AsyncSession, entry: TimeEntryModel, new_start: datetime
) -> datetime:
    """Bounds for a new start time; German 422 messages."""
    new_start = ensure_utc(new_start)
    now = utcnow()
    if new_start > now + FUTURE_TOLERANCE:
        raise DomainValidationError(
            "Die Startzeit darf nicht in der Zukunft liegen.",
            code="time_entry.start_in_future",
        )
    if now - new_start > MAX_START_AGE:
        raise DomainValidationError(
            "Die Startzeit darf höchstens 24 Stunden zurückliegen.",
            code="time_entry.start_too_old",
        )
    previous_end = await _previous_end(db, entry)
    if previous_end is not None and new_start < previous_end:
        raise DomainValidationError(
            "Die Startzeit darf nicht vor dem Ende der vorherigen "
            f"Zeiterfassung ({format_local(previous_end)} Uhr) liegen.",
            code="time_entry.start_before_previous",
            extra={"previous_end": previous_end.isoformat()},
        )
    return min(new_start, now)


def _describe(field: str, old: Any, new: Any) -> str:
    if field == "activity_id":
        return f"Aktivität #{old} → #{new}"
    if field == "order_id":
        return f"Auftrag #{old} → #{new}"
    if field == "location":
        return f"Ort „{old or '–'}“ → „{new or '–'}“"
    if field == "start_time":
        return (
            f"Startzeit {format_local(old, TIME_FORMAT)} → "
            f"{format_local(new, TIME_FORMAT)}"
        )
    return "Notiz geändert"


async def _collect_changes(
    db: AsyncSession, entry: TimeEntryModel, edit: RunningTimeEntryEdit
) -> Dict[str, Any]:
    """Validated ``{column: new_value}`` for the fields that really change."""
    sent = edit.model_dump(exclude_unset=True)
    changes: Dict[str, Any] = {}
    if "activity_id" in sent and sent["activity_id"] != entry.activity_id:
        await _require_activity(db, sent["activity_id"])
        changes["activity_id"] = sent["activity_id"]
    if "order_id" in sent and sent["order_id"] != entry.order_id:
        await _require_order(db, sent["order_id"])
        changes["order_id"] = sent["order_id"]
    if "location" in sent and sent["location"] != entry.location:
        changes["location"] = sent["location"]
    if "start_time" in sent:
        new_start = await validate_start_time(db, entry, sent["start_time"])
        if new_start != ensure_utc(cast(datetime, entry.start_time)):
            changes["start_time"] = new_start
    if "notes" in sent:
        user_text, _ = split_notes(cast(Optional[str], entry.notes))
        new_text = (sent["notes"] or "").strip()
        if new_text != user_text.strip():
            changes["notes"] = new_text
    return changes


def _log_line(user: UserModel, entry: TimeEntryModel, changes: Dict[str, Any]) -> str:
    parts: List[str] = [
        _describe(field, getattr(entry, field), value)
        for field, value in changes.items()
    ]
    stamp = format_local(utcnow())
    # A user id, never a name: the log must not carry PII (CLAUDE.md).
    return f"[{stamp}] Benutzer #{user.id}: " + "; ".join(parts)


async def edit_running_entry(
    db: AsyncSession, entry_id: str, edit: RunningTimeEntryEdit, user: UserModel
) -> RunningEditResult:
    """Apply ``edit`` to the running entry and append the change-log line.

    Returns the changed fields; the caller reloads, publishes and responds.
    No-op edits change nothing and write no log line.
    """
    entry = await _load_running(db, entry_id)
    changes = await _collect_changes(db, entry, edit)
    if not changes:
        return RunningEditResult(entry_id=entry_id, changes=(), changed_fields=())

    line = _log_line(user, entry, changes)
    user_text, edit_log = split_notes(cast(Optional[str], entry.notes))
    if "notes" in changes:
        user_text = changes["notes"]
    new_log = f"{edit_log}\n{line}" if edit_log else line
    values = {k: v for k, v in changes.items() if k != "notes"}
    values["notes"] = join_notes(user_text, new_log)

    await db.execute(
        update(TimeEntryModel).where(TimeEntryModel.id == entry_id).values(**values)
    )
    await db.commit()
    logger.info(
        "Running time entry edited",
        extra={
            "entry_id": entry_id,
            "user_id": user.id,
            "fields": sorted(changes),
        },
    )
    return RunningEditResult(
        entry_id=entry_id,
        changes=(line,),
        changed_fields=tuple(sorted(changes)),
    )
