# src/goldsmith_erp/services/repair_service.py
"""
Business logic for the Repair Tracking module (Reparaturverwaltung).

Repair numbers follow the format REP-YYYY-NNNN (sequential per calendar year).
Bag numbers follow the format TÜ-YYYY-NNNN (same counter, physical label).

Stage transitions are validated — a job cannot skip stages forward (though
cancellation is always allowed from any active state).
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core import pubsub
from goldsmith_erp.db.models import (
    Customer,
    Notification,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    RepairJob,
    RepairJobStatus,
    User,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.repair import (
    RepairCompleteInput,
    RepairDiagnoseInput,
    RepairJobCreate,
    RepairStatusUpdate,
)

logger = logging.getLogger(__name__)

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

        repair = RepairJob(
            repair_number=repair_number,
            bag_number=bag_number,
            customer_id=data.customer_id,
            received_by=user_id,
            item_description=data.item_description,
            item_type=data.item_type,
            metal_type=data.metal_type,
            estimated_value=data.estimated_value,
            estimated_completion_date=data.estimated_completion_date,
            status=RepairJobStatus.RECEIVED,
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
        Quality check passed — mark as READY and notify customer.

        Records actual cost and completion timestamp.
        Sends REPAIR_READY notification to any admin/goldsmith users.
        """
        now = datetime.utcnow()
        repair = await RepairService._transition(
            db,
            repair_id,
            RepairJobStatus.READY,
            extra_updates={
                "actual_cost": data.actual_cost,
                "actual_completion_date": now,
                "customer_notified_at": now,
            },
        )

        # Create in-app notification for admins (customer contact role)
        # In a production system we'd also send an SMS/email here
        await RepairService._notify_admins_repair_ready(db, repair, user_id)

        return repair

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
