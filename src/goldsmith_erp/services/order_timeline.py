"""Merged order / repair history (W2-07, ARCH-01; repairs: ARCH phase 5).

``GET /orders/{id}/timeline`` and ``GET /jobs/{id}/timeline`` use
:func:`build_order_timeline`; a repair job uses :func:`build_repair_timeline`
(repair events, its Kundeninfo and, with DESIGN_VIEW, its photos).

Sources, merged ascending by time:
- ``order_events`` (status changes, creation, migration backfill);
- ``customer_updates`` for the order (Kundeninfo);
- ``order_photos`` (only for callers with DESIGN_VIEW: design IP);
- ``time_entries`` (activity, duration).

Role projection is done here, field by field, so nothing leaks by default:
no prices or costs at all, no customer free text (``body``), no time-entry
notes, no photo file paths. The subject of a cost-change update names an
amount, so it is served only to FINANCIAL_VIEW holders.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    CustomerUpdate,
    CustomerUpdateKind,
    OrderEvent,
    OrderPhoto,
    RepairPhoto,
    TimeEntry,
)
from goldsmith_erp.models.order import OrderTimelineItem, OrderTimelineRead
from goldsmith_erp.services import repair_workflow
from goldsmith_erp.services.order_workflow import label_for

_UPDATE_KIND_LABELS: dict[CustomerUpdateKind, str] = {
    CustomerUpdateKind.PROGRESS: "Fortschritt",
    CustomerUpdateKind.COST_CHANGE: "Kostenänderung",
    CustomerUpdateKind.READY_FOR_PICKUP: "Abholbereit",
    CustomerUpdateKind.CUSTOM: "Freitext",
}

# Only these event-meta keys are served; everything else stays internal.
_EVENT_META_KEYS = ("origin", "resume_date", "quote_id", "backfill", "legacy_status")

# Tie-break for identical timestamps: a status change reads before its effects.
_KIND_ORDER = {"status": 0, "time_entry": 1, "photo": 2, "customer_update": 3}


def _safe_label(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    try:
        return label_for(status)
    except ValueError:
        return status


def _safe_repair_label(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    try:
        return repair_workflow.label_for(status)
    except ValueError:
        return status


def _labeler(event: Any) -> Any:
    return _safe_repair_label if event.repair_job_id is not None else _safe_label


def _status_summary(event_row: OrderEvent) -> str:
    event: Any = event_row  # Column-style model attributes
    label = _labeler(event)
    to_label = label(event.to_status) or event.to_status
    if event.from_status is None:
        prefix = "Status übernommen" if event.reason == "backfill" else "Angelegt"
        return f"{prefix}: {to_label}"
    return f"{label(event.from_status)} → {to_label}"


def _event_item(event_row: OrderEvent) -> OrderTimelineItem:
    event: Any = event_row  # Column-style model attributes
    meta: dict[str, Any] = event.meta or {}
    label = _labeler(event)
    data: dict[str, Any] = {
        "from_status": event.from_status,
        "to_status": event.to_status,
        "from_label": label(event.from_status),
        "to_label": label(event.to_status),
        "reason": event.reason,
    }
    data.update({key: meta[key] for key in _EVENT_META_KEYS if key in meta})
    return OrderTimelineItem(
        kind="status",
        id=f"event-{event.id}",
        at=event.created_at,
        user_id=event.user_id,
        summary=_status_summary(event),
        data=data,
    )


def _update_item(update_row: CustomerUpdate, *, financial: bool) -> OrderTimelineItem:
    update: Any = update_row  # Column-style model attributes
    kind = CustomerUpdateKind(update.kind)
    data: dict[str, Any] = {
        "kind": kind.value,
        "status": getattr(update.status, "value", update.status),
        "sent_at": update.sent_at,
    }
    if kind is not CustomerUpdateKind.COST_CHANGE or financial:
        data["subject"] = update.subject
    return OrderTimelineItem(
        kind="customer_update",
        id=f"update-{update.id}",
        at=update.sent_at or update.created_at,
        user_id=update.sent_by,
        summary=f"Kundeninfo: {_UPDATE_KIND_LABELS[kind]}",
        data=data,
    )


def _photo_item(photo_row: OrderPhoto) -> OrderTimelineItem:
    photo: Any = photo_row  # Column-style model attributes
    return OrderTimelineItem(
        kind="photo",
        id=f"photo-{photo.id}",
        at=photo.timestamp,
        user_id=photo.taken_by,
        summary="Foto aufgenommen",
        data={"photo_id": photo.id},
    )


def _time_entry_item(entry_row: TimeEntry) -> OrderTimelineItem:
    entry: Any = entry_row  # Column-style model attributes
    activity_name = entry.activity.name if entry.activity is not None else None
    return OrderTimelineItem(
        kind="time_entry",
        id=f"time-{entry.id}",
        at=entry.start_time,
        user_id=entry.user_id,
        summary=f"Zeiterfassung: {activity_name or 'Tätigkeit'}",
        data={
            "activity_id": entry.activity_id,
            "activity_name": activity_name,
            "duration_minutes": entry.duration_minutes,
            "end_time": entry.end_time,
            "is_running": entry.end_time is None,
        },
    )


async def _fetch_all(db: AsyncSession, stmt: Any) -> list[Any]:
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def build_order_timeline(
    db: AsyncSession,
    order_id: int,
    *,
    financial: bool,
    design: bool,
) -> OrderTimelineRead:
    """Return the merged history of one order, projected for the caller.

    ``financial`` / ``design``: the caller holds FINANCIAL_VIEW / DESIGN_VIEW
    (the router decides via ``api.role_projection``).
    """
    events = await _fetch_all(
        db, select(OrderEvent).where(OrderEvent.order_id == order_id)
    )
    updates = await _fetch_all(
        db, select(CustomerUpdate).where(CustomerUpdate.order_id == order_id)
    )
    entries = await _fetch_all(
        db,
        select(TimeEntry)
        .options(selectinload(TimeEntry.activity))
        .where(TimeEntry.order_id == order_id),
    )
    items: list[OrderTimelineItem] = [_event_item(e) for e in events]
    items.extend(_update_item(u, financial=financial) for u in updates)
    items.extend(_time_entry_item(t) for t in entries)
    if design:
        photos = await _fetch_all(
            db, select(OrderPhoto).where(OrderPhoto.order_id == order_id)
        )
        items.extend(_photo_item(p) for p in photos)
    items.sort(key=lambda item: (item.at, _KIND_ORDER[item.kind], item.id))
    return OrderTimelineRead(order_id=order_id, items=items)


def _repair_photo_item(photo_row: RepairPhoto) -> OrderTimelineItem:
    photo: Any = photo_row  # Column-style model attributes
    return OrderTimelineItem(
        kind="photo",
        id=f"repair-photo-{photo.id}",
        at=photo.timestamp,
        user_id=photo.taken_by,
        summary="Foto aufgenommen",
        data={
            "photo_id": photo.id,
            "phase": getattr(photo.phase, "value", photo.phase),
        },
    )


async def build_repair_timeline(
    db: AsyncSession,
    repair_job_id: int,
    *,
    financial: bool,
    design: bool,
) -> list[OrderTimelineItem]:
    """Merged history of one repair, projected like the order timeline.

    Sources: repair lifecycle events (``order_events.repair_job_id``), the
    repair's Kundeninfo and, with ``design``, its photos. Time entries
    attach to orders only, so a repair has none.
    """
    events = await _fetch_all(
        db, select(OrderEvent).where(OrderEvent.repair_job_id == repair_job_id)
    )
    updates = await _fetch_all(
        db,
        select(CustomerUpdate).where(CustomerUpdate.repair_job_id == repair_job_id),
    )
    items: list[OrderTimelineItem] = [_event_item(e) for e in events]
    items.extend(_update_item(u, financial=financial) for u in updates)
    if design:
        photos = await _fetch_all(
            db, select(RepairPhoto).where(RepairPhoto.repair_job_id == repair_job_id)
        )
        items.extend(_repair_photo_item(p) for p in photos)
    items.sort(key=lambda item: (item.at, _KIND_ORDER[item.kind], item.id))
    return items


__all__ = ["build_order_timeline", "build_repair_timeline"]
