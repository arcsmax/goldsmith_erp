"""Customer-facing "Statusbericht" PDF for an order or a repair.

W6 / DOM section D, Option 2 ("Werkstattbericht"): a live snapshot, never a
stored document. Every request re-reads the current order/repair state, the
customer-visible timeline and the latest customer-visible photos, so the
report is always current and needs no new persistence or migration.

Privacy (CLAUDE.md — non-negotiable):
- NEVER prices, cost internals or material cost (financial data, ADMIN/
  GOLDSMITH only — enforced by the router's permission, not repeated here).
- NEVER staff names — timeline entries carry no ``user_id``/name.
- NEVER internal notes, diagnosis notes or design descriptions (design-IP /
  business-confidential free text) — only the order/repair title and
  structured piece facts (metal, gemstone type/carat) are shown.

Customer-visible timeline: status changes (German labels) and customer
updates that were actually SENT (drafts are internal). Time entries are
never included — they are staff/internal by nature.

Customer-visible photos:
- Orders: only OrderPhoto ids that were explicitly selected into a SENT
  CustomerUpdate for this order — the same "nothing is ever auto-shared"
  design-IP rule the Kundeninfo composer already enforces (see
  ``CustomerUpdate`` model docstring and
  ``customer_message_service.load_photo_attachments``). There is no
  per-photo visibility flag on ``OrderPhoto``, so this *is* "what exists":
  the set of photos actually shared with this customer so far.
- Repairs: ``RepairPhoto`` carries no per-photo visibility flag, and repair
  customer-updates never carry photo attachments today
  (``load_photo_attachments`` requires an ``order_id``) — so, per the
  "or all if no such flag exists" rule, the latest ``RepairPhoto`` rows are
  used instead, most recent first (before/after documentation is already
  customer-facing, e.g. the handover PDF).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    CustomerUpdate,
    CustomerUpdateStatus,
    MediaOwnerType,
    Order,
    OrderEvent,
    RepairJob,
    RepairPhoto,
)
from goldsmith_erp.models.consent import ConsentPurpose
from goldsmith_erp.services.consent_service import ConsentService
from goldsmith_erp.services.customer_message_service import (
    load_photo_attachments,
    resolve_recipient,
)
from goldsmith_erp.services.image_validation import (
    PhotoValidationError,
    create_email_variant,
    resolve_within_root,
)
from goldsmith_erp.services.media_service import MediaService
from goldsmith_erp.services.order_workflow import label_for
from goldsmith_erp.services.pdf_service import PDFService
from goldsmith_erp.services.workshop_settings_service import WorkshopSettingsService

logger = logging.getLogger(__name__)

# Longest side of a report photo — matches the Kundeninfo email variant.
PHOTO_MAX_PX = 1200
MAX_REPORT_PHOTOS = 6

_NEXT_STEPS_DEFAULT = "Wir melden uns, sobald es Neuigkeiten zu Ihrem Auftrag gibt."

_METAL_LABELS: Dict[str, str] = {
    "gold_24k": "999 Gold (24 Karat)",
    "gold_22k": "916 Gold (22 Karat)",
    "gold_18k": "750 Gold (18 Karat)",
    "gold_14k": "585 Gold (14 Karat)",
    "gold_9k": "375 Gold (9 Karat)",
    "silver_999": "Feinsilber (999)",
    "silver_925": "Sterling Silber (925)",
    "silver_800": "Altsilber (800)",
    "platinum_950": "Platin (950)",
    "platinum_900": "Platin (900)",
    "palladium": "Palladium",
    "white_gold_18k": "750 Weißgold (18 Karat)",
    "white_gold_14k": "585 Weißgold (14 Karat)",
}

_UPDATE_KIND_REPORT_LABELS: Dict[str, str] = {
    "progress": "Fortschritts-Update gesendet",
    "ready_for_pickup": "Abholbereit-Meldung gesendet",
    "custom": "Nachricht gesendet",
    # cost_change is never surfaced here — no prices in a customer report.
}

_REPAIR_STATUS_LABELS: Dict[str, str] = {
    "received": "Angenommen",
    "diagnosed": "Diagnose abgeschlossen",
    "quoted": "Kostenvoranschlag erstellt",
    "approved": "Reparatur genehmigt",
    "in_repair": "In Bearbeitung",
    "quality_check": "Qualitätskontrolle",
    "ready": "Abholbereit",
    "picked_up": "Abgeholt",
    "cancelled": "Storniert",
}


class StatusReportNotFoundError(ValueError):
    """No such order/repair (404)."""


@dataclass(frozen=True)
class StatusReportEvent:
    """One customer-visible line of the report's timeline."""

    at: Any
    summary: str


@dataclass(frozen=True)
class StatusReportData:
    """Everything ``pdf_service.render_status_report_pdf`` needs."""

    reference: str
    title: str
    metal_label: Optional[str]
    gemstones: List[str]
    events: List[StatusReportEvent]
    photos: List[bytes]
    next_steps: str
    customer_name: str
    workshop: Dict[str, Any]


def _metal_label(metal_type: Any) -> Optional[str]:
    if metal_type is None:
        return None
    raw = getattr(metal_type, "value", metal_type)
    return _METAL_LABELS.get(str(raw), str(raw).replace("_", " "))


def _gemstone_labels(gemstones: Sequence[Any]) -> List[str]:
    labels: List[str] = []
    for stone in gemstones:
        stone_type = str(getattr(stone, "type", "") or "").strip()
        if not stone_type:
            continue
        text = stone_type.capitalize()
        carat = getattr(stone, "carat", None)
        if carat:
            text += f" {carat:g} ct"
        quantity = getattr(stone, "quantity", None) or 1
        if quantity and quantity > 1:
            text += f" ({quantity}x)"
        labels.append(text)
    return labels


def _safe_status_label(status: Any) -> str:
    raw = getattr(status, "value", status)
    try:
        return label_for(raw)
    except ValueError:
        return str(raw)


async def _order_events(db: AsyncSession, order_id: int) -> List[StatusReportEvent]:
    event_rows = (
        (
            await db.execute(
                select(OrderEvent)
                .where(OrderEvent.order_id == order_id)
                .order_by(OrderEvent.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    events: List[StatusReportEvent] = []
    for row in event_rows:
        to_label = _safe_status_label(row.to_status)
        if row.from_status is None:
            summary = f"Auftrag angelegt: {to_label}"
        else:
            summary = (
                f"Status geändert: {_safe_status_label(row.from_status)} → {to_label}"
            )
        events.append(StatusReportEvent(at=row.created_at, summary=summary))
    events.extend(await _sent_update_events(db, order_id=order_id, repair_job_id=None))
    events.sort(key=lambda item: item.at)
    return events


def _repair_label(status: Any) -> str:
    return _REPAIR_STATUS_LABELS.get(str(status), "Status aktualisiert")


async def _repair_lifecycle_events(
    db: AsyncSession, repair_job_id: int
) -> List[StatusReportEvent]:
    """ARCH phase 5: repair status history from ``order_events``."""
    rows = (
        (
            await db.execute(
                select(OrderEvent)
                .where(OrderEvent.repair_job_id == repair_job_id)
                .order_by(OrderEvent.created_at.asc(), OrderEvent.id.asc())
            )
        )
        .scalars()
        .all()
    )
    events: List[StatusReportEvent] = []
    for row in rows:
        to_label = _repair_label(row.to_status)
        if row.from_status is None:
            summary = (
                f"Aktueller Status: {to_label}"
                if row.reason == "backfill"
                else "Reparatur angenommen"
            )
        else:
            summary = f"Status geändert: {_repair_label(row.from_status)} → {to_label}"
        events.append(StatusReportEvent(at=row.created_at, summary=summary))
    return events


async def _repair_events(db: AsyncSession, repair: Any) -> List[StatusReportEvent]:
    lifecycle = await _repair_lifecycle_events(db, int(repair.id))
    if lifecycle:
        lifecycle.extend(
            await _sent_update_events(db, order_id=None, repair_job_id=repair.id)
        )
        lifecycle.sort(key=lambda item: item.at)
        return lifecycle
    # Fallback for a repair without events (written by pre-ARCH-5 code).
    events: List[StatusReportEvent] = []
    if repair.created_at is not None:
        events.append(
            StatusReportEvent(at=repair.created_at, summary="Reparatur angenommen")
        )
    current_label = _REPAIR_STATUS_LABELS.get(
        str(getattr(repair.status, "value", repair.status)), None
    )
    if current_label and current_label != "Angenommen":
        # No repair event-history table exists (only the current status is
        # stored) — the best customer-visible marker for "where things stand
        # now" is the current status itself, timestamped at the most
        # relevant known milestone date.
        at = (
            repair.picked_up_at
            or repair.actual_completion_date
            or repair.customer_notified_at
            or repair.created_at
        )
        events.append(
            StatusReportEvent(at=at, summary=f"Aktueller Status: {current_label}")
        )
    events.extend(await _sent_update_events(db, order_id=None, repair_job_id=repair.id))
    events.sort(key=lambda item: item.at)
    return events


async def _sent_update_events(
    db: AsyncSession, *, order_id: Optional[int], repair_job_id: Optional[int]
) -> List[StatusReportEvent]:
    condition = (
        CustomerUpdate.order_id == order_id
        if order_id is not None
        else CustomerUpdate.repair_job_id == repair_job_id
    )
    rows = (
        (
            await db.execute(
                select(CustomerUpdate).where(
                    condition, CustomerUpdate.status == CustomerUpdateStatus.SENT
                )
            )
        )
        .scalars()
        .all()
    )
    events: List[StatusReportEvent] = []
    for row in rows:
        kind_value = str(getattr(row.kind, "value", row.kind))
        if kind_value == "cost_change":
            continue  # never a price-bearing entry in a customer report
        label = _UPDATE_KIND_REPORT_LABELS.get(kind_value, "Nachricht gesendet")
        if row.photo_ids:
            label += " (mit Fotos)"
        events.append(
            StatusReportEvent(at=row.sent_at or row.created_at, summary=label)
        )
    return events


async def _flagged_legacy_ids(
    db: AsyncSession, owner_type: MediaOwnerType, owner_id: int
) -> List[str]:
    """Newest-first legacy ids of the owner's ``customer_visible`` photos."""
    flagged = await MediaService.customer_visible_legacy_ids(db, owner_type, owner_id)
    return list(reversed(flagged))[:MAX_REPORT_PHOTOS]


async def _order_photos(db: AsyncSession, order_id: int) -> List[bytes]:
    # Photos flagged "für Kunden sichtbar" win; without any flag the report
    # keeps showing the photos already sent to the customer (pre-flag rule).
    flagged = await _flagged_legacy_ids(db, MediaOwnerType.ORDER, order_id)
    if flagged:
        return await load_photo_attachments(db, order_id, flagged)
    rows = (
        (
            await db.execute(
                select(CustomerUpdate)
                .where(
                    CustomerUpdate.order_id == order_id,
                    CustomerUpdate.status == CustomerUpdateStatus.SENT,
                )
                .order_by(CustomerUpdate.sent_at.desc())
            )
        )
        .scalars()
        .all()
    )
    seen: List[str] = []
    for row in rows:
        for photo_id in cast(Optional[List[str]], row.photo_ids) or []:
            if photo_id not in seen:
                seen.append(photo_id)
        if len(seen) >= MAX_REPORT_PHOTOS:
            break
    photo_ids = seen[:MAX_REPORT_PHOTOS]
    return await load_photo_attachments(db, order_id, photo_ids)


async def _has_photo_consent(db: AsyncSession, customer_id: Optional[int]) -> bool:
    if customer_id is None:
        return False
    return await ConsentService.has_consent(db, customer_id, ConsentPurpose.PHOTO_USE)


async def _repair_photos(db: AsyncSession, repair_job_id: int) -> List[bytes]:
    # Flagged photos win; without any flag, the latest photos (pre-flag rule).
    stmt = select(RepairPhoto).where(RepairPhoto.repair_job_id == repair_job_id)
    flagged = await _flagged_legacy_ids(db, MediaOwnerType.REPAIR, repair_job_id)
    if flagged:
        stmt = stmt.where(RepairPhoto.id.in_([int(pid) for pid in flagged]))
    rows = (
        (
            await db.execute(
                stmt.order_by(RepairPhoto.timestamp.desc()).limit(MAX_REPORT_PHOTOS)
            )
        )
        .scalars()
        .all()
    )
    storage_root = Path(settings.PHOTO_STORAGE_PATH).resolve()
    variants: List[bytes] = []
    for photo in rows:
        resolved = resolve_within_root(cast(str, photo.file_path), storage_root)
        if resolved is None or not resolved.is_file():
            logger.warning(
                "Status report repair photo path invalid or missing",
                extra={"photo_id": photo.id, "repair_job_id": repair_job_id},
            )
            continue
        try:
            variants.append(
                await asyncio.to_thread(create_email_variant, resolved, PHOTO_MAX_PX)
            )
        except (PhotoValidationError, OSError):
            logger.warning(
                "Status report repair photo failed validation",
                extra={"photo_id": photo.id, "repair_job_id": repair_job_id},
                exc_info=True,
            )
    return variants


async def build_order_status_report(
    db: AsyncSession, order_id: int, *, next_steps: Optional[str] = None
) -> StatusReportData:
    """Assemble the report data for an order. Raises ``StatusReportNotFoundError``."""
    order = (
        await db.execute(
            select(Order)
            .options(selectinload(Order.gemstones))
            .where(Order.id == order_id)
        )
    ).scalar_one_or_none()
    if order is None:
        raise StatusReportNotFoundError(f"Auftrag #{order_id} nicht gefunden")

    recipient = await resolve_recipient(db, order_id=order_id, repair_job_id=None)
    workshop = await WorkshopSettingsService.seller_block(db)
    events = await _order_events(db, order_id)
    photos = await _order_photos(db, order_id)
    if photos and not await _has_photo_consent(db, recipient.customer_id):
        # Consent may have been revoked after an earlier update was sent —
        # never show previously-shared photos again once withdrawn; the
        # rest of the report (piece, timeline, next steps) stays intact.
        photos = []
    return StatusReportData(
        reference=recipient.order_ref,
        title=str(order.title) if order.title else recipient.order_ref,
        metal_label=_metal_label(order.metal_type),
        gemstones=_gemstone_labels(order.gemstones),
        events=events,
        photos=photos,
        next_steps=next_steps or _NEXT_STEPS_DEFAULT,
        customer_name=recipient.display_name,
        workshop=workshop,
    )


async def build_repair_status_report(
    db: AsyncSession, repair_job_id: int, *, next_steps: Optional[str] = None
) -> StatusReportData:
    """Assemble the report data for a repair. Raises ``StatusReportNotFoundError``."""
    repair = (
        await db.execute(select(RepairJob).where(RepairJob.id == repair_job_id))
    ).scalar_one_or_none()
    if repair is None:
        raise StatusReportNotFoundError(
            f"Reparaturauftrag #{repair_job_id} nicht gefunden"
        )

    recipient = await resolve_recipient(db, order_id=None, repair_job_id=repair_job_id)
    workshop = await WorkshopSettingsService.seller_block(db)
    events = await _repair_events(db, repair)
    photos = await _repair_photos(db, repair_job_id)
    return StatusReportData(
        reference=recipient.order_ref,
        title=str(repair.item_description or recipient.order_ref),
        metal_label=_metal_label(repair.metal_type) if repair.metal_type else None,
        gemstones=[],
        events=events,
        photos=photos,
        next_steps=next_steps or _NEXT_STEPS_DEFAULT,
        customer_name=recipient.display_name,
        workshop=workshop,
    )


async def render_order_status_report_pdf(
    db: AsyncSession, order_id: int, *, next_steps: Optional[str] = None
) -> bytes:
    """Build and render the order Statusbericht as PDF bytes."""
    data = await build_order_status_report(db, order_id, next_steps=next_steps)
    return await asyncio.to_thread(PDFService.render_status_report_pdf, data=data)


async def render_repair_status_report_pdf(
    db: AsyncSession, repair_job_id: int, *, next_steps: Optional[str] = None
) -> bytes:
    """Build and render the repair Statusbericht as PDF bytes."""
    data = await build_repair_status_report(db, repair_job_id, next_steps=next_steps)
    return await asyncio.to_thread(PDFService.render_status_report_pdf, data=data)


__all__ = [
    "StatusReportData",
    "StatusReportEvent",
    "StatusReportNotFoundError",
    "build_order_status_report",
    "build_repair_status_report",
    "render_order_status_report_pdf",
    "render_repair_status_report_pdf",
]
