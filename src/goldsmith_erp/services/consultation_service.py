"""Business logic for the V1.1 consultation module (Beratung & Annahme).

Transaction pattern: `async with transactional(db)` (measurement_service style) —
the context manager commits; methods flush+refresh inside it.
Side effects (calendar event, notification) run AFTER the consultation write and
are individually guarded: their failure is logged, never propagated.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
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


class ConsultationNotFoundError(ValueError):
    """A referenced consultation — or, during creation, its customer —
    could not be found.

    Subclasses ``ValueError`` so pre-existing callers that catch
    ``ValueError`` keep working. Lets the router dispatch on type instead
    of string-matching "not found" in the message (pattern precedent:
    ``DuplicateNoGoError`` in no_go_service.py).
    """


class AlreadyConvertedError(ValueError):
    """Consultation was already converted — carries the existing target ids."""

    def __init__(self, order_id: Optional[int], quote_id: Optional[int]):
        self.order_id = order_id
        self.quote_id = quote_id
        super().__init__(
            "Beratung wurde bereits konvertiert "
            f"(order_id={order_id}, quote_id={quote_id})"
        )


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
                raise ConsultationNotFoundError(
                    f"Customer {consultation_in.customer_id} not found"
                )
            consultation = Consultation(
                conducted_by=conducted_by_user_id,
                **consultation_in.model_dump(),
            )
            db.add(consultation)
            await db.flush()
            await db.refresh(consultation)

        # Capture scalars NOW: a failed side-effect below rolls back the session,
        # which expires every ORM object — reading consultation.<attr> afterwards
        # would raise MissingGreenlet on an AsyncSession. Locals stay valid.
        consultation_id: int = consultation.id
        customer_id: int = consultation.customer_id
        follow_up_at: Optional[datetime] = consultation.follow_up_at

        if follow_up_at is not None:
            await ConsultationService._ensure_follow_up_reminder(
                db,
                consultation_id=consultation_id,
                customer_id=customer_id,
                follow_up_at=follow_up_at,
                user_id=conducted_by_user_id,
            )

        # Publish AFTER the consultation write succeeds. A Redis failure must
        # never roll back or otherwise fail the create — log and continue.
        try:
            await pubsub.publish_event(
                "consultation_updates",
                json.dumps(
                    {
                        "action": "create",
                        "consultation_id": consultation_id,
                        "customer_id": customer_id,
                    }
                ),
            )
        except Exception as exc:
            logger.error(
                "Failed to publish consultation create event",
                extra={"consultation_id": consultation_id, "error": str(exc)},
                exc_info=True,
            )

        logger.info(
            "Consultation created",
            extra={
                "consultation_id": consultation_id,
                "customer_id": customer_id,
            },
        )
        return await ConsultationService._reload(db, consultation_id)

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
                raise ConsultationNotFoundError(
                    f"Consultation {consultation_id} not found"
                )
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

        # Capture scalars before any side effect: a rollback inside
        # _ensure_follow_up_reminder expires all ORM objects (see create).
        customer_id: int = consultation.customer_id
        follow_up_at: Optional[datetime] = consultation.follow_up_at
        conducted_by: int = consultation.conducted_by
        existing_calendar_event_id: Optional[int] = consultation.calendar_event_id

        if "follow_up_at" in changed and follow_up_at is not None:
            await ConsultationService._ensure_follow_up_reminder(
                db,
                consultation_id=consultation_id,
                customer_id=customer_id,
                follow_up_at=follow_up_at,
                existing_calendar_event_id=existing_calendar_event_id,
                user_id=conducted_by,
            )

        logger.info(
            "Consultation updated",
            extra={"consultation_id": consultation_id, "fields": sorted(changed)},
        )
        return await ConsultationService._reload(db, consultation_id)

    @staticmethod
    async def convert_consultation(
        db: AsyncSession,
        consultation_id: int,
        target: str,  # "quote" | "order" — validated by the router schema
        current_user,  # User — typed loosely to avoid circular import
    ) -> Consultation:
        """Convert a consultation into a Quote or an Order.

        Two sequential transactions (transactional() commits and is not
        nestable): (1) create the target entity via its own service — this
        commits on its own; (2) a second transactional block links the
        consultation back to the new target and, for order conversions,
        stamps order_id on every attached photo. The idempotency check runs
        before (1) so a repeat call never creates a duplicate target.

        If (2) fails after (1) succeeded, the target entity exists but the
        consultation was never linked to it (orphaned conversion) — this is
        logged at ERROR with both ids and re-raised. Fail loudly; no silent
        inconsistency.
        """
        from goldsmith_erp.models.order import OrderCreate  # noqa: PLC0415
        from goldsmith_erp.models.quote import QuoteCreate  # noqa: PLC0415
        from goldsmith_erp.services.order_service import OrderService  # noqa: PLC0415
        from goldsmith_erp.services.quote_service import QuoteService  # noqa: PLC0415

        consultation = await ConsultationService.get_consultation(db, consultation_id)
        if consultation is None:
            raise ConsultationNotFoundError(f"Consultation {consultation_id} not found")
        if consultation.status is ConsultationStatus.CONVERTED:
            raise AlreadyConvertedError(
                consultation.converted_order_id, consultation.converted_quote_id
            )

        piece_label = (
            consultation.piece_type.value if consultation.piece_type else "Schmuckstück"
        )
        description = (
            consultation.wishes
            or consultation.notes
            or (f"Aus Beratung #{consultation.id} übernommen")
        )

        new_order_id: Optional[int] = None
        new_quote_id: Optional[int] = None
        if target == "order":
            order = await OrderService.create_order(
                db,
                OrderCreate(
                    customer_id=consultation.customer_id,
                    title=f"Beratung #{consultation.id}: {piece_label}"[:200],
                    description=description[:2000],
                ),
            )
            new_order_id = order.id
        else:
            quote = await QuoteService.create_quote(
                db,
                QuoteCreate(
                    customer_id=consultation.customer_id,
                    notes=description[:2000],
                ),
                current_user,
            )
            new_quote_id = quote.id

        try:
            async with transactional(db):
                consultation = await ConsultationService._reload(db, consultation_id)
                consultation.status = ConsultationStatus.CONVERTED
                consultation.converted_order_id = new_order_id
                consultation.converted_quote_id = new_quote_id
                if new_order_id is not None:
                    for photo in consultation.photos:
                        photo.order_id = new_order_id
        except Exception:
            logger.error(
                "Orphaned conversion — created target but failed to link back; "
                "link manually",
                extra={
                    "consultation_id": consultation_id,
                    "order_id": new_order_id,
                    "quote_id": new_quote_id,
                },
                exc_info=True,
            )
            raise

        # Publish AFTER the linking transaction succeeds. A Redis failure must
        # never fail the conversion — log and continue (same guarded pattern
        # as create_consultation).
        try:
            await pubsub.publish_event(
                "consultation_updates",
                json.dumps(
                    {
                        "action": "convert",
                        "consultation_id": consultation_id,
                        "order_id": new_order_id,
                        "quote_id": new_quote_id,
                    }
                ),
            )
        except Exception as exc:
            logger.error(
                "Failed to publish consultation convert event",
                extra={"consultation_id": consultation_id, "error": str(exc)},
                exc_info=True,
            )

        logger.info(
            "Consultation converted",
            extra={
                "consultation_id": consultation_id,
                "target": target,
                "order_id": new_order_id,
                "quote_id": new_quote_id,
            },
        )
        return await ConsultationService._reload(db, consultation_id)

    @staticmethod
    async def _reload(db: AsyncSession, consultation_id: int) -> Consultation:
        """Fresh, authoritative read after side effects.

        populate_existing forces the row's current DB state onto the identity-map
        instance — the side effects update calendar_event_id via a bulk UPDATE,
        which a plain SELECT would not push onto an already-loaded object.
        """
        result = await db.execute(
            select(Consultation)
            .options(selectinload(Consultation.photos))
            .execution_options(populate_existing=True)
            .filter(Consultation.id == consultation_id)
        )
        consultation = result.scalar_one_or_none()
        assert consultation is not None
        return consultation

    @staticmethod
    async def _ensure_follow_up_reminder(
        db: AsyncSession,
        consultation_id: int,
        customer_id: int,
        follow_up_at: datetime,
        user_id: int,
        existing_calendar_event_id: Optional[int] = None,
    ) -> None:
        """Create or reuse the REMINDER calendar event + notify.

        When ``existing_calendar_event_id`` refers to a still-existing
        CalendarEvent row (the consultation was already linked to a
        reminder from an earlier follow_up_at), that row's start_datetime
        is UPDATEd in place — and its end_datetime too, if it had one —
        instead of creating a second CalendarEvent. Without this, every
        autosave PATCH that touched follow_up_at left the previous
        reminder behind as an orphan. If the referenced row no longer
        exists (deleted out-of-band), a fresh event is created exactly
        like the create_consultation path.

        Takes plain scalars (not the ORM object): if the inner transaction
        fails, its rollback expires every object in the session's identity
        map, and reading ORM attributes afterwards raises MissingGreenlet
        on an AsyncSession. Scalars keep the guard actually side-effect-safe.

        Failures here must never break the consultation write — log and continue.
        """
        try:
            async with transactional(db):
                reused_event_id: Optional[int] = None
                if existing_calendar_event_id is not None:
                    existing_row = (
                        await db.execute(
                            select(CalendarEvent.id, CalendarEvent.end_datetime).filter(
                                CalendarEvent.id == existing_calendar_event_id,
                                CalendarEvent.event_type == CalendarEventType.REMINDER,
                            )
                        )
                    ).first()
                    if existing_row is not None:
                        update_values: dict[str, datetime] = {
                            "start_datetime": follow_up_at
                        }
                        if existing_row.end_datetime is not None:
                            update_values["end_datetime"] = follow_up_at
                        await db.execute(
                            update(CalendarEvent)
                            .where(CalendarEvent.id == existing_calendar_event_id)
                            .values(**update_values)
                        )
                        reused_event_id = existing_calendar_event_id

                if reused_event_id is None:
                    event = CalendarEvent(
                        title=f"Wiedervorlage Beratung #{consultation_id}",
                        description="Kunde wollte über den Schmuckwunsch nachdenken.",
                        event_type=CalendarEventType.REMINDER,
                        start_datetime=follow_up_at,
                        end_datetime=None,
                        all_day=True,
                        user_id=user_id,
                    )
                    db.add(event)
                    await db.flush()
                    # UPDATE by id instead of mutating a possibly-detached ORM
                    # object — no attribute access on expired instances.
                    await db.execute(
                        update(Consultation)
                        .where(Consultation.id == consultation_id)
                        .values(calendar_event_id=event.id)
                    )
        except Exception:
            logger.error(
                "Failed to create or update follow-up calendar event",
                extra={"consultation_id": consultation_id},
                exc_info=True,
            )
            return

        if reused_event_id is not None:
            # Reusing an existing REMINDER event (issue #13 item 7's
            # in-place update, above) — the user was already notified when
            # it was first created. Sending "Wiedervorlage geplant" again on
            # every subsequent follow_up_at edit would be noisy and
            # misleading (it implies a NEW reminder, not an edit of the
            # existing one). Only notify on actual creation.
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
                    f"Beratung #{consultation_id} ist zur Wiedervorlage am "
                    f"{follow_up_at:%d.%m.%Y} vorgemerkt."
                ),
                notification_type=NotificationTypeEnum.CONSULTATION_FOLLOWUP,
                severity=NotificationSeverityEnum.INFO,
                related_customer_id=customer_id,
            )
        except Exception:
            # create_notification self-commits; if that commit fails the session
            # is left in pending-rollback state and every later statement (e.g.
            # _reload) would raise PendingRollbackError. Roll back first to
            # recover — harmless no-op when the session is clean.
            await db.rollback()
            logger.error(
                "Failed to create follow-up notification",
                extra={"consultation_id": consultation_id},
                exc_info=True,
            )
