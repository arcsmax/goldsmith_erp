"""Business logic for the V1.1 consultation module (Beratung & Annahme).

Transaction pattern: `async with transactional(db)` (measurement_service style) —
the context manager commits; methods flush+refresh inside it.
Side effects (calendar event, notification) run AFTER the consultation write and
are individually guarded: their failure is logged, never propagated.
"""

import json
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Import the module (not the function) so the unit-test conftest monkeypatch on
# goldsmith_erp.core.pubsub.publish_event actually intercepts our calls.
from goldsmith_erp.core import pubsub
from goldsmith_erp.db.models import (
    CalendarEvent,
    CalendarEventType,
    Consultation,
    ConsultationStatus,
    Customer,
    NotificationSeverityEnum,
    NotificationTypeEnum,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.consultation import ConsultationCreate, ConsultationUpdate

logger = logging.getLogger(__name__)

# Fields a CONVERTED consultation may still change (post-conversion bookkeeping).
_MUTABLE_AFTER_CONVERSION = {"status", "notes"}


class ConsultationService:
    @staticmethod
    async def create_consultation(
        db: AsyncSession,
        consultation_in: ConsultationCreate,
        conducted_by_user_id: int,
    ) -> Consultation:
        async with transactional(db):
            customer_exists = await db.execute(
                select(Customer.id).filter(Customer.id == consultation_in.customer_id)
            )
            if customer_exists.scalar_one_or_none() is None:
                raise ValueError(f"Customer {consultation_in.customer_id} not found")
            consultation = Consultation(
                conducted_by=conducted_by_user_id,
                **consultation_in.model_dump(),
            )
            db.add(consultation)
            await db.flush()
            await db.refresh(consultation)

        if consultation.follow_up_at is not None:
            await ConsultationService._ensure_follow_up_reminder(
                db, consultation, conducted_by_user_id
            )

        # Publish AFTER the consultation write succeeds. A Redis failure must
        # never roll back or otherwise fail the create — log and continue.
        try:
            await pubsub.publish_event(
                "consultation_updates",
                json.dumps(
                    {
                        "action": "create",
                        "consultation_id": consultation.id,
                        "customer_id": consultation.customer_id,
                    }
                ),
            )
        except Exception as exc:
            logger.error(
                "Failed to publish consultation create event",
                extra={"consultation_id": consultation.id, "error": str(exc)},
                exc_info=True,
            )

        logger.info(
            "Consultation created",
            extra={
                "consultation_id": consultation.id,
                "customer_id": consultation.customer_id,
            },
        )
        return await ConsultationService._reload(db, consultation.id)

    @staticmethod
    async def get_consultation(
        db: AsyncSession, consultation_id: int
    ) -> Optional[Consultation]:
        result = await db.execute(
            select(Consultation)
            .options(selectinload(Consultation.photos))
            .filter(Consultation.id == consultation_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_consultations(
        db: AsyncSession,
        customer_id: Optional[int] = None,
        status: Optional[ConsultationStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Consultation]:
        query = (
            select(Consultation)
            .options(selectinload(Consultation.photos))
            .order_by(Consultation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if customer_id is not None:
            query = query.filter(Consultation.customer_id == customer_id)
        if status is not None:
            query = query.filter(Consultation.status == status)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def update_consultation(
        db: AsyncSession, consultation_id: int, update_in: ConsultationUpdate
    ) -> Consultation:
        changed = update_in.model_dump(exclude_unset=True)
        async with transactional(db):
            consultation = await ConsultationService.get_consultation(
                db, consultation_id
            )
            if consultation is None:
                raise ValueError(f"Consultation {consultation_id} not found")
            if consultation.status is ConsultationStatus.CONVERTED and (
                set(changed) - _MUTABLE_AFTER_CONVERSION
            ):
                raise ValueError(
                    "Beratung ist bereits konvertiert und kann nicht mehr "
                    "geändert werden"
                )
            for field, value in changed.items():
                setattr(consultation, field, value)
            await db.flush()
            await db.refresh(consultation)

        if "follow_up_at" in changed and consultation.follow_up_at is not None:
            await ConsultationService._ensure_follow_up_reminder(
                db, consultation, consultation.conducted_by
            )

        logger.info(
            "Consultation updated",
            extra={"consultation_id": consultation_id, "fields": sorted(changed)},
        )
        return await ConsultationService._reload(db, consultation_id)

    @staticmethod
    async def _reload(db: AsyncSession, consultation_id: int) -> Consultation:
        consultation = await ConsultationService.get_consultation(db, consultation_id)
        assert consultation is not None
        return consultation

    @staticmethod
    async def _ensure_follow_up_reminder(
        db: AsyncSession, consultation: Consultation, user_id: int
    ) -> None:
        """Create/refresh the REMINDER calendar event + notification.

        Failures here must never break the consultation write — log and continue.
        """
        try:
            async with transactional(db):
                event = CalendarEvent(
                    title=f"Wiedervorlage Beratung #{consultation.id}",
                    description="Kunde wollte über den Schmuckwunsch nachdenken.",
                    event_type=CalendarEventType.REMINDER,
                    start_datetime=consultation.follow_up_at,
                    end_datetime=None,
                    all_day=True,
                    user_id=user_id,
                )
                db.add(event)
                await db.flush()
                consultation.calendar_event_id = event.id
        except Exception:
            logger.error(
                "Failed to create follow-up calendar event",
                extra={"consultation_id": consultation.id},
                exc_info=True,
            )
            return

        # Notification — lazy import to avoid circular deps (handoff_service pattern).
        from goldsmith_erp.services.notification_service import (  # noqa: PLC0415
            NotificationService,
        )

        try:
            await NotificationService.create_notification(
                db=db,
                user_id=user_id,
                title="Wiedervorlage geplant",
                message=(
                    f"Beratung #{consultation.id} ist zur Wiedervorlage am "
                    f"{consultation.follow_up_at:%d.%m.%Y} vorgemerkt."
                ),
                notification_type=NotificationTypeEnum.CONSULTATION_FOLLOWUP,
                severity=NotificationSeverityEnum.INFO,
                related_customer_id=consultation.customer_id,
            )
        except Exception:
            logger.error(
                "Failed to create follow-up notification",
                extra={"consultation_id": consultation.id},
                exc_info=True,
            )
