# src/goldsmith_erp/services/repair_service.py
"""
Business logic for the Repair Tracking module (Reparaturverwaltung).

Repair numbers follow the format REP-YYYY-NNNN (sequential per calendar year).
Bag numbers follow the format TÜ-YYYY-NNNN (same counter, physical label).

Stage transitions are validated — a job cannot skip stages forward (though
cancellation is always allowed from any active state).
"""

import asyncio
import io
import json
import logging
import re
import unicodedata
from datetime import datetime
from typing import Any, List, Optional, cast

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core import pubsub
from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    CustomerUpdateKind,
    Notification,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    RepairJob,
    RepairJobStatus,
    RepairPhoto,
    RepairPhotoPhase,
    User,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.customer_update import (
    CustomerUpdateCreate,
    CustomerUpdateSendResult,
)
from goldsmith_erp.models.repair import (
    IntakeChecklistItem,
    RepairCompleteInput,
    RepairDiagnoseInput,
    RepairJobCreate,
    RepairStatusUpdate,
)
from goldsmith_erp.services.repair_photo_service import RepairPhotoService

logger = logging.getLogger(__name__)


class InvalidChecklistPhotoError(ValueError):
    """
    One or more intake-checklist items reference a ``photo_id`` that is not
    an INTAKE-phase ``RepairPhoto`` belonging to THIS repair.

    SECURITY / PRIVACY: the message is intentionally ID-ONLY. Checklist item
    labels and ``na_reason`` values are user free-text and must never be
    embedded here — mirrors ``DuplicateNoGoError``'s rationale in
    no_go_service.py: exception text can reach ``transactional()``'s
    ERROR-level exception logger (``str(exc)``), and this error is in fact
    raised BEFORE entering that block for the same reason (see
    ``RepairService.update_intake_checklist``).
    """

    def __init__(self, repair_id: int, invalid_photo_ids: List[int]) -> None:
        self.repair_id = repair_id
        self.invalid_photo_ids = invalid_photo_ids
        super().__init__(
            f"Ungueltige photo_id(s) fuer Reparaturauftrag #{repair_id}: "
            f"{invalid_photo_ids} — muss ein INTAKE-Phase-Foto dieses "
            f"Auftrags sein"
        )


class NoCustomerUpdateDraftError(ValueError):
    """
    No CustomerUpdate exists yet for this repair — maps to 404.

    Expected when the repair has not reached READY yet (no draft has been
    created — see ``RepairService.complete_repair``). ID-only message,
    same rationale as ``InvalidChecklistPhotoError``.
    """

    def __init__(self, repair_id: int) -> None:
        super().__init__(
            f"Kein Kundeninfo-Entwurf fuer Reparaturauftrag #{repair_id} vorhanden"
        )


# German umlaut/ß transliteration applied before generic diacritic
# stripping, so e.g. "Schäden" -> "Schaeden" (not "Schden").
_UMLAUT_TRANSLATION = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}
)


def _slugify_label(label: str) -> str:
    """
    Deterministic, stable slug for a checklist label — used as its dict
    ``key``.

    Steps: transliterate German umlauts/ß, strip remaining diacritics
    (NFKD + drop combining marks, e.g. "Pavé" -> "Pave"), lowercase, then
    collapse every run of non-alphanumeric characters to a single '-'.
    Re-seeding with the same ``REPAIR_INTAKE_CHECKLIST`` setting always
    produces the same keys (stability requirement for the seeded
    checklist).
    """
    text = label.translate(_UMLAUT_TRANSLATION)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


# Valid forward transitions per status — cancellation is handled separately.
_VALID_TRANSITIONS: dict[RepairJobStatus, list[RepairJobStatus]] = {
    RepairJobStatus.RECEIVED: [RepairJobStatus.DIAGNOSED, RepairJobStatus.CANCELLED],
    RepairJobStatus.DIAGNOSED: [RepairJobStatus.QUOTED, RepairJobStatus.CANCELLED],
    RepairJobStatus.QUOTED: [RepairJobStatus.APPROVED, RepairJobStatus.CANCELLED],
    RepairJobStatus.APPROVED: [RepairJobStatus.IN_REPAIR, RepairJobStatus.CANCELLED],
    RepairJobStatus.IN_REPAIR: [
        RepairJobStatus.QUALITY_CHECK,
        RepairJobStatus.CANCELLED,
    ],
    RepairJobStatus.QUALITY_CHECK: [RepairJobStatus.READY, RepairJobStatus.IN_REPAIR],
    RepairJobStatus.READY: [RepairJobStatus.PICKED_UP],
    RepairJobStatus.PICKED_UP: [],
    RepairJobStatus.CANCELLED: [],
}


async def _generate_repair_number(db: AsyncSession) -> tuple[str, str]:
    """
    Generate unique repair number and bag number for the current year.

    Queries the highest existing sequence within the year and increments by one.
    Both numbers share the same counter so bag label matches the system record.

    Returns:
        (repair_number, bag_number) — e.g. ("REP-2026-0001", "TÜ-2026-0001")
    """
    year = datetime.utcnow().year
    prefix = f"REP-{year}-"

    result = await db.execute(
        select(func.max(RepairJob.repair_number)).where(
            RepairJob.repair_number.like(f"{prefix}%")
        )
    )
    last_number = result.scalar_one_or_none()

    if last_number:
        try:
            seq = int(last_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    repair_number = f"REP-{year}-{seq:04d}"
    bag_number = f"TU-{year}-{seq:04d}"  # ASCII-safe label for printer compatibility
    return repair_number, bag_number


ANNAHMESCHEIN_MAX_PHOTOS = 8
ANNAHMESCHEIN_THUMB_PX = 400


def _read_thumbnail(photo: RepairPhoto) -> Optional[bytes]:
    """JPEG thumbnail bytes of one photo, or None (logged) if unreadable.

    Uses the stored 200 px thumbnail; when it is missing (thumbnail creation
    is non-fatal at upload) the original is downscaled in memory, so the
    Annahmeschein never embeds a full-size photo.
    """
    try:
        original = RepairPhotoService._anchored_path_or_raise(photo)
        thumb = original.parent / "thumbs" / f"{original.stem}.jpg"
        if thumb.exists():
            return thumb.read_bytes()
        with Image.open(original) as img:
            img.thumbnail((ANNAHMESCHEIN_THUMB_PX, ANNAHMESCHEIN_THUMB_PX))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG")
            return buf.getvalue()
    except (OSError, ValueError):
        logger.warning(
            "Annahmeschein: repair photo unreadable, skipped",
            extra={"photo_id": photo.id, "repair_id": photo.repair_job_id},
            exc_info=True,
        )
        return None


INTAKE_PROBLEM_PREFIX = "Kundenangabe: "
INTAKE_CONDITION_PREFIX = "Zustand bei Annahme: "


def compose_intake_description(data: RepairJobCreate) -> str:
    """Item description plus the counter-intake notes (W2-12, FE-17).

    RepairJob has no columns for the customer's own words or the condition
    at intake yet (migrations are serialized elsewhere), so both are kept
    as labelled lines of ``item_description``. Everything that shows the
    description (detail page, Annahmeschein, label) then shows them too.
    """
    lines = [data.item_description]
    if data.customer_problem:
        lines.append(f"{INTAKE_PROBLEM_PREFIX}{data.customer_problem}")
    if data.condition_notes:
        lines.append(f"{INTAKE_CONDITION_PREFIX}{', '.join(data.condition_notes)}")
    return "\n".join(lines)


async def _load_repair(db: AsyncSession, repair_id: int) -> Optional[RepairJob]:
    """Load a single repair job with all relationships eager-loaded."""
    result = await db.execute(
        select(RepairJob)
        .options(
            selectinload(RepairJob.customer),
            selectinload(RepairJob.photos),
        )
        .where(RepairJob.id == repair_id, RepairJob.is_deleted == False)  # noqa: E712
    )
    return result.scalar_one_or_none()


class RepairService:
    """Service layer for repair job management."""

    # -------------------------------------------------------------------------
    # READ
    # -------------------------------------------------------------------------

    @staticmethod
    async def get_repair(db: AsyncSession, repair_id: int) -> Optional[RepairJob]:
        """Fetch a single repair job by primary key."""
        return await _load_repair(db, repair_id)

    @staticmethod
    async def intake_thumbnails(db: AsyncSession, repair: RepairJob) -> List[bytes]:
        """JPEG thumbnails of the repair's INTAKE photos for the Annahmeschein.

        ``repair.photos`` is already eager-loaded by ``get_repair``; ``db`` is
        accepted for the service-method convention. File reads run in a
        worker thread so they never block the event loop.
        """
        intake = [
            photo for photo in repair.photos if photo.phase == RepairPhotoPhase.INTAKE
        ][:ANNAHMESCHEIN_MAX_PHOTOS]
        loaded = [await asyncio.to_thread(_read_thumbnail, photo) for photo in intake]
        return [data for data in loaded if data is not None]

    @staticmethod
    async def list_repairs(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        status: Optional[RepairJobStatus] = None,
        customer_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> List[RepairJob]:
        """
        List repair jobs with optional filters.

        Filters:
          - status: exact match on RepairJobStatus
          - customer_id: repairs for a specific customer
          - search: case-insensitive substring match on repair_number or bag_number
        """
        query = (
            select(RepairJob)
            .options(
                selectinload(RepairJob.customer),
            )
            .where(RepairJob.is_deleted == False)  # noqa: E712
            .order_by(RepairJob.created_at.desc())
        )

        if status is not None:
            query = query.where(RepairJob.status == status)
        if customer_id is not None:
            query = query.where(RepairJob.customer_id == customer_id)
        if search:
            like = f"%{search}%"
            query = query.where(
                RepairJob.repair_number.ilike(like)
                | RepairJob.bag_number.ilike(like)
                | RepairJob.item_description.ilike(like)
            )

        result = await db.execute(query.offset(skip).limit(limit))
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # CREATE
    # -------------------------------------------------------------------------

    @staticmethod
    async def create_repair(
        db: AsyncSession,
        data: RepairJobCreate,
        user_id: int,
    ) -> RepairJob:
        """
        Create a new repair intake record.

        Auto-generates repair_number (REP-YYYY-NNNN) and bag_number (TU-YYYY-NNNN).
        Initial status is always RECEIVED.
        """
        repair_number, bag_number = await _generate_repair_number(db)

        # Seed the intake checklist from settings — one open item per
        # configured label, keyed by a stable slug (see _slugify_label).
        # Written as part of the RepairJob constructor call, so it lands
        # inside the SAME transaction as the row's initial insert below
        # (no separate follow-up write).
        seeded_checklist = [
            {
                "key": _slugify_label(label),
                "label": label,
                "status": "open",
                "photo_id": None,
                "na_reason": None,
            }
            for label in settings.REPAIR_INTAKE_CHECKLIST
        ]

        repair = RepairJob(
            repair_number=repair_number,
            bag_number=bag_number,
            customer_id=data.customer_id,
            received_by=user_id,
            item_description=compose_intake_description(data),
            item_type=data.item_type,
            metal_type=data.metal_type,
            estimated_value=data.estimated_value,
            estimated_cost=data.estimated_cost,
            estimated_completion_date=data.estimated_completion_date,
            status=RepairJobStatus.RECEIVED,
            intake_checklist=seeded_checklist,
        )

        async with transactional(db):
            db.add(repair)
            await db.flush()  # Populate repair.id before notification

            # Fire REPAIR_RECEIVED notification for all goldsmiths/admins
            # (real-time via Redis pub/sub)
            await pubsub.publish_event(
                "repair_updates",
                json.dumps(
                    {
                        "action": "created",
                        "repair_id": repair.id,
                        "repair_number": repair_number,
                        "status": RepairJobStatus.RECEIVED.value,
                    }
                ),
            )

        logger.info(
            "Repair intake created",
            extra={
                "repair_id": repair.id,
                "repair_number": repair_number,
                "received_by": user_id,
            },
        )
        return repair

    # -------------------------------------------------------------------------
    # INTAKE CHECKLIST
    # -------------------------------------------------------------------------

    @staticmethod
    async def update_intake_checklist(
        db: AsyncSession,
        repair_id: int,
        items: List[IntakeChecklistItem],
    ) -> RepairJob:
        """
        Replace the repair's intake checklist with the given items.

        Every item with status="photo" must reference a photo_id that is an
        INTAKE-phase RepairPhoto belonging to THIS repair — cross-repair
        references and wrong-phase photos are rejected wholesale (via
        InvalidChecklistPhotoError) before any write happens.

        Raises:
            ValueError: If the repair does not exist.
            InvalidChecklistPhotoError: If any item's photo_id does not
                resolve to an INTAKE-phase photo of this repair.
        """
        # Pre-flight checks (read-only) run BEFORE entering transactional(db)
        # — see InvalidChecklistPhotoError's docstring: transactional()'s
        # generic error handler logs str(exc) at ERROR for any exception
        # escaping the block, and while this particular error message is
        # ID-only (safe either way), raising here follows this branch's
        # established pattern (no_go_service.add_no_go) of keeping
        # business-rule rejections out of the transaction logger entirely.
        repair = await _load_repair(db, repair_id)
        if repair is None:
            raise ValueError(f"Reparaturauftrag #{repair_id} nicht gefunden")

        photo_ids = {item.photo_id for item in items if item.photo_id is not None}
        if photo_ids:
            result = await db.execute(
                select(RepairPhoto.id).where(
                    RepairPhoto.id.in_(photo_ids),
                    RepairPhoto.repair_job_id == repair_id,
                    RepairPhoto.phase == RepairPhotoPhase.INTAKE,
                )
            )
            valid_ids = set(result.scalars().all())
            invalid_ids = sorted(photo_ids - valid_ids)
            if invalid_ids:
                raise InvalidChecklistPhotoError(repair_id, invalid_ids)

        async with transactional(db):
            # Replace the WHOLE list value — never mutate the existing list
            # in place. SQLAlchemy's JSON column change-tracking compares by
            # reference; an in-place `.append()`/`.remove()` on the current
            # list would not be detected as a change and silently fail to
            # persist.
            # cast(): mypy sees RepairJob.intake_checklist as Column[Any] at
            # the class level (declarative JSON column), but on a mapped
            # *instance* it holds the runtime Python value — a Column[T]
            # false positive on assignment, same class of nit flagged in
            # Task 1's review.
            repair.intake_checklist = cast(Any, [item.model_dump() for item in items])

        logger.info(
            "Repair intake checklist updated",
            extra={"repair_id": repair_id, "item_count": len(items)},
        )
        return repair

    # -------------------------------------------------------------------------
    # STATUS TRANSITIONS
    # -------------------------------------------------------------------------

    @staticmethod
    async def _transition(
        db: AsyncSession,
        repair_id: int,
        new_status: RepairJobStatus,
        extra_updates: Optional[dict] = None,
    ) -> RepairJob:
        """
        Internal helper — validate and apply a status transition.

        Raises:
            ValueError: If the repair is not found or the transition is invalid.
        """
        repair = await _load_repair(db, repair_id)
        if repair is None:
            raise ValueError(f"Reparaturauftrag #{repair_id} nicht gefunden")

        allowed = _VALID_TRANSITIONS.get(repair.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Statuswechsel von '{repair.status.value}' nach '{new_status.value}' "
                f"ist nicht erlaubt. Erlaubt: {[s.value for s in allowed]}"
            )

        async with transactional(db):
            repair.status = new_status
            if extra_updates:
                for field, value in extra_updates.items():
                    setattr(repair, field, value)

            await pubsub.publish_event(
                "repair_updates",
                json.dumps(
                    {
                        "action": "status_changed",
                        "repair_id": repair.id,
                        "repair_number": repair.repair_number,
                        "new_status": new_status.value,
                    }
                ),
            )

        logger.info(
            "Repair status changed",
            extra={
                "repair_id": repair.id,
                "new_status": new_status.value,
            },
        )
        return repair

    @staticmethod
    async def diagnose(
        db: AsyncSession,
        repair_id: int,
        data: RepairDiagnoseInput,
        user_id: int,
    ) -> RepairJob:
        """
        Record diagnosis notes and cost estimate, advance to DIAGNOSED → QUOTED.

        The status moves through two stages in one HTTP call: the goldsmith
        writes up the findings (DIAGNOSED) and the system immediately produces
        the written quote (QUOTED). The whole sequence is **atomic** — if the
        second transition or any DB write fails, the first is rolled back so
        the repair is not stranded in 'diagnosed' state with no quote behind it.
        """
        # Pre-flight checks (validation only — no writes yet) so that any
        # failure here returns 422 BEFORE we touch the row.
        repair = await _load_repair(db, repair_id)
        if repair is None:
            raise ValueError(f"Reparaturauftrag #{repair_id} nicht gefunden")

        for current, target in (
            (repair.status, RepairJobStatus.DIAGNOSED),
            (RepairJobStatus.DIAGNOSED, RepairJobStatus.QUOTED),
        ):
            if target not in _VALID_TRANSITIONS.get(current, []):
                raise ValueError(
                    f"Statuswechsel von '{current.value}' nach '{target.value}' "
                    f"ist nicht erlaubt. "
                    f"Erlaubt: {[s.value for s in _VALID_TRANSITIONS.get(current, [])]}"
                )

        # All-or-nothing: single transaction wrapping both transitions + the
        # field updates so the row is never left half-written.
        async with transactional(db):
            repair.status = RepairJobStatus.QUOTED
            repair.diagnosis_notes = data.diagnosis_notes
            repair.estimated_cost = data.estimated_cost
            if data.estimated_completion_date is not None:
                # Validator on RepairDiagnoseInput already strips tzinfo,
                # but assert here for clarity in case a caller bypasses it.
                ecd = data.estimated_completion_date
                if ecd.tzinfo is not None:
                    from datetime import timezone as _tz

                    ecd = ecd.astimezone(_tz.utc).replace(tzinfo=None)
                repair.estimated_completion_date = ecd

            await pubsub.publish_event(
                "repair_updates",
                json.dumps(
                    {
                        "action": "status_changed",
                        "repair_id": repair.id,
                        "repair_number": repair.repair_number,
                        "new_status": RepairJobStatus.QUOTED.value,
                    }
                ),
            )

        logger.info(
            "Repair diagnosed and quoted",
            extra={
                "repair_id": repair_id,
                "estimated_cost": data.estimated_cost,
                "diagnosed_by": user_id,
            },
        )
        return repair

    @staticmethod
    async def approve(
        db: AsyncSession,
        repair_id: int,
        data: RepairStatusUpdate,
        user_id: int,
    ) -> RepairJob:
        """Customer approved the quote — advance to APPROVED."""
        return await RepairService._transition(db, repair_id, RepairJobStatus.APPROVED)

    @staticmethod
    async def start_repair(
        db: AsyncSession,
        repair_id: int,
        user_id: int,
    ) -> RepairJob:
        """Begin physical repair work — advance to IN_REPAIR."""
        return await RepairService._transition(db, repair_id, RepairJobStatus.IN_REPAIR)

    @staticmethod
    async def submit_for_quality_check(
        db: AsyncSession,
        repair_id: int,
        user_id: int,
    ) -> RepairJob:
        """Repair work done — advance to QUALITY_CHECK."""
        return await RepairService._transition(
            db, repair_id, RepairJobStatus.QUALITY_CHECK
        )

    @staticmethod
    async def complete_repair(
        db: AsyncSession,
        repair_id: int,
        data: RepairCompleteInput,
        user_id: int,
    ) -> RepairJob:
        """
        Quality check passed — mark as READY and prepare the customer's
        pickup-ready Kundeninfo draft.

        Records actual cost and completion timestamp. Creates an in-app
        REPAIR_READY notification for staff, AND a DRAFT CustomerUpdate
        (kind=READY_FOR_PICKUP) the customer will actually receive once
        staff sends it (one tap — see ``send_customer_update``).

        DOM-12 / W2-02: unlike the pre-fix behaviour, ``customer_notified_at``
        is deliberately NOT stamped here — a draft existing is not the same
        as the customer having been informed. It is stamped by
        ``send_customer_update`` only once a send actually delivers.
        """
        now = datetime.utcnow()
        repair = await RepairService._transition(
            db,
            repair_id,
            RepairJobStatus.READY,
            extra_updates={
                "actual_cost": data.actual_cost,
                "actual_completion_date": now,
            },
        )

        # Create in-app notification for admins (customer contact role)
        await RepairService._notify_admins_repair_ready(db, repair, user_id)

        # Create the customer-facing pickup-ready draft — staff sends it
        # with one tap from the repair detail page
        # (RepairCustomerUpdatePanel), via send_customer_update below.
        await RepairService._create_pickup_ready_draft(db, repair, user_id)

        return repair

    @staticmethod
    async def _create_pickup_ready_draft(
        db: AsyncSession, repair: RepairJob, user_id: int
    ) -> None:
        """
        Create the DRAFT CustomerUpdate for a repair that just reached READY.

        Reuses ``CustomerUpdateService.create_draft`` — the SAME
        draft/send/dedupe mechanism used for orders (see
        ``automated_customer_email.py``), not a second notification path.

        Never raises: a failure to create the draft must not fail the
        status transition itself (the repair IS ready regardless of
        whether the Kundeninfo draft could be prepared) — logged loudly
        instead (CLAUDE.md: fail loudly, never swallow silently) so staff
        can notice and create the update by hand via
        ``POST /repairs/{id}/customer-updates`` if this ever happens.
        """
        # Late import — mirrors automated_customer_email._create_and_send's
        # deferred import of the same service (avoids a def-time coupling
        # between the two service modules).
        from goldsmith_erp.services.customer_update_service import (  # noqa: PLC0415
            CustomerUpdateService,
        )

        try:
            await CustomerUpdateService.create_draft(
                db,
                order_id=None,
                repair_job_id=cast(int, repair.id),
                data=CustomerUpdateCreate(
                    kind=CustomerUpdateKind.READY_FOR_PICKUP,
                    subject=None,
                    body=None,
                    photo_ids=None,
                ),
                user_id=user_id,
            )
        except Exception:
            logger.error(
                "Failed to create pickup-ready Kundeninfo draft for repair",
                extra={"repair_id": repair.id},
                exc_info=True,
            )

    @staticmethod
    async def send_customer_update(
        db: AsyncSession, repair_id: int, user_id: int
    ) -> CustomerUpdateSendResult:
        """
        One-tap send of the repair's pickup-ready Kundeninfo draft
        (DOM-12 / W2-02).

        Sends the MOST RECENT CustomerUpdate row for this repair (the draft
        created by ``complete_repair`` when the repair reached READY) via
        ``CustomerUpdateService.send`` — the same draft/send/dedupe path
        used everywhere else, not a second notification mechanism.

        ``RepairJob.customer_notified_at`` is stamped with the update's
        actual ``sent_at`` ONLY when the send is delivered (email accepted
        by SMTP) — never on a merely-attempted or SMTP-unconfigured send,
        so the timestamp can never lie about whether the customer was
        actually informed. A subsequent PDF-manual delivery confirmation
        (``POST /updates/{id}/mark-delivered``) also informs the customer
        but does not (yet) stamp this field — tracked as a follow-up, not
        part of this fix's Definition of Done.

        Raises:
            ValueError: repair not found (404).
            NoCustomerUpdateDraftError: no CustomerUpdate exists yet for
                this repair (404) — most likely it hasn't reached READY.
            CustomerUpdateNotFoundError / InvalidUpdateStateError: bubbled
                from CustomerUpdateService.send (already SENT -> 409).
        """
        # Late import — see _create_pickup_ready_draft's docstring.
        from goldsmith_erp.services.customer_update_service import (  # noqa: PLC0415
            CustomerUpdateService,
        )

        repair = await _load_repair(db, repair_id)
        if repair is None:
            raise ValueError(f"Reparaturauftrag #{repair_id} nicht gefunden")

        latest = (
            await db.execute(
                select(CustomerUpdate)
                .where(CustomerUpdate.repair_job_id == repair_id)
                .order_by(CustomerUpdate.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            raise NoCustomerUpdateDraftError(repair_id)

        result = await CustomerUpdateService.send(db, cast(int, latest.id), user_id)

        if result.delivered and result.update.sent_at is not None:
            async with transactional(db):
                repair.customer_notified_at = result.update.sent_at
            await db.refresh(repair)

        return result

    @staticmethod
    async def _notify_admins_repair_ready(
        db: AsyncSession,
        repair: RepairJob,
        triggered_by: int,
    ) -> None:
        """Create REPAIR_READY notifications for all admin users."""
        result = await db.execute(
            select(User).where(User.is_active == True)  # noqa: E712
        )
        users = result.scalars().all()

        customer_name = "Laufkunde"
        if repair.customer:
            customer_name = f"{repair.customer.first_name} {repair.customer.last_name}"

        async with transactional(db):
            for user in users:
                notification = Notification(
                    user_id=user.id,
                    title="Reparatur abholbereit",
                    message=(
                        f"Reparatur {repair.repair_number} "
                        f"({customer_name}) ist fertig. "
                        f"Tüte: {repair.bag_number}"
                    ),
                    notification_type=NotificationTypeEnum.REPAIR_READY,
                    severity=NotificationSeverityEnum.INFO,
                )
                db.add(notification)

        logger.info(
            "REPAIR_READY notifications sent",
            extra={"repair_id": repair.id, "repair_number": repair.repair_number},
        )

    @staticmethod
    async def pickup(
        db: AsyncSession,
        repair_id: int,
        user_id: int,
    ) -> RepairJob:
        """Customer picked up the repaired piece — advance to PICKED_UP."""
        return await RepairService._transition(
            db,
            repair_id,
            RepairJobStatus.PICKED_UP,
            extra_updates={"picked_up_at": datetime.utcnow()},
        )

    @staticmethod
    async def cancel(
        db: AsyncSession,
        repair_id: int,
        data: RepairStatusUpdate,
        user_id: int,
    ) -> RepairJob:
        """Cancel a repair job from any active state."""
        repair = await _load_repair(db, repair_id)
        if repair is None:
            raise ValueError(f"Reparaturauftrag #{repair_id} nicht gefunden")

        if repair.status in (RepairJobStatus.PICKED_UP, RepairJobStatus.CANCELLED):
            raise ValueError(
                f"Reparatur im Status '{repair.status.value}' kann nicht storniert werden"
            )

        async with transactional(db):
            repair.status = RepairJobStatus.CANCELLED

        logger.info(
            "Repair cancelled",
            extra={"repair_id": repair_id, "cancelled_by": user_id},
        )
        return repair

    # -------------------------------------------------------------------------
    # SOFT DELETE
    # -------------------------------------------------------------------------

    @staticmethod
    async def soft_delete(db: AsyncSession, repair_id: int, user_id: int) -> bool:
        """
        Soft-delete a repair job (GDPR Art. 17 — 30-day grace period).

        Only PICKED_UP or CANCELLED jobs can be deleted.
        """
        repair = await _load_repair(db, repair_id)
        if repair is None:
            return False

        if repair.status not in (RepairJobStatus.PICKED_UP, RepairJobStatus.CANCELLED):
            raise ValueError(
                "Nur abgeholte oder stornierte Reparaturen koennen geloescht werden"
            )

        async with transactional(db):
            repair.is_deleted = True
            repair.deleted_at = datetime.utcnow()

        logger.info(
            "Repair soft-deleted",
            extra={"repair_id": repair_id, "deleted_by": user_id},
        )
        return True
