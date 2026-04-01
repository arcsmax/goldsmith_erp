# src/goldsmith_erp/services/handoff_service.py
"""
Handoff service — business logic for the Stabuebergabe (order handoff) protocol.

When a goldsmith finishes their part of an order they create a handoff record
targeting the next craftsperson.  The recipient must explicitly accept or
decline before the system registers the change of responsibility.

Notification strategy:
  - On create  → notify to_user    ("Auftrag #123 wurde Ihnen uebergeben von Klaus")
  - On accept  → notify from_user  ("Uebergabe wurde bestaetigt von Maria")
  - On decline → notify from_user  ("Uebergabe abgelehnt: <Begruendung>")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.pubsub import publish_event
from goldsmith_erp.db.models import (
    HandoffStatusEnum,
    HandoffTypeEnum,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    Order,
    OrderHandoff,
    User,
)
from goldsmith_erp.db.transaction import transactional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_HANDOFF_TYPE_LABELS: dict[HandoffTypeEnum, str] = {
    HandoffTypeEnum.PASS_TO_NEXT: "Weitergabe",
    HandoffTypeEnum.REQUEST_REVIEW: "Pruefen angefordert",
    HandoffTypeEnum.RETURN_FOR_REWORK: "Rueckgabe zur Nacharbeit",
    HandoffTypeEnum.MARK_COMPLETE: "Als fertig markiert",
}


async def _load_handoff_with_relations(
    db: AsyncSession, handoff_id: int
) -> Optional[OrderHandoff]:
    """Fetch a single handoff with from_user and to_user eagerly loaded."""
    result = await db.execute(
        select(OrderHandoff)
        .options(
            selectinload(OrderHandoff.from_user),
            selectinload(OrderHandoff.to_user),
            selectinload(OrderHandoff.order),
        )
        .where(OrderHandoff.id == handoff_id)
    )
    return result.scalar_one_or_none()


async def _load_user(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _load_order(db: AsyncSession, order_id: int) -> Optional[Order]:
    result = await db.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one_or_none()


async def _send_notification(
    db: AsyncSession,
    user_id: int,
    title: str,
    message: str,
    severity: NotificationSeverityEnum,
    order_id: int,
) -> None:
    """
    Persist a HANDOFF notification and publish it to Redis.

    Imported lazily to avoid a circular dependency between handoff_service
    and notification_service.
    """
    from goldsmith_erp.services.notification_service import NotificationService  # noqa: PLC0415

    try:
        await NotificationService.create_notification(
            db=db,
            user_id=user_id,
            title=title,
            message=message,
            notification_type=NotificationTypeEnum.HANDOFF,
            severity=severity,
            related_order_id=order_id,
        )
    except Exception as exc:
        # Notification failure must not roll back the handoff transaction.
        logger.error(
            "Failed to create handoff notification",
            extra={"user_id": user_id, "order_id": order_id, "error": str(exc)},
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Public service methods
# ---------------------------------------------------------------------------


class HandoffService:
    """Static-method service — all methods accept AsyncSession as first arg."""

    @staticmethod
    async def create_handoff(
        db: AsyncSession,
        order_id: int,
        from_user_id: int,
        to_user_id: int,
        handoff_type: HandoffTypeEnum,
        notes: Optional[str] = None,
    ) -> OrderHandoff:
        """
        Create a new PENDING handoff for an order.

        Validates that:
        - The order exists.
        - The recipient user exists and is active.
        - The sender is not handing off to themselves.

        After persisting, sends a notification to the recipient and publishes
        an event to the ``order_updates`` Redis channel.

        Raises:
            ValueError: If any validation fails.
        """
        # --- Validate order ---
        order = await _load_order(db, order_id)
        if not order:
            raise ValueError(f"Auftrag #{order_id} nicht gefunden.")

        # --- Validate recipient ---
        if from_user_id == to_user_id:
            raise ValueError("Ein Goldschmied kann nicht an sich selbst uebergeben.")

        recipient = await _load_user(db, to_user_id)
        if not recipient or not recipient.is_active:
            raise ValueError(
                f"Empfaenger-Benutzer #{to_user_id} nicht gefunden oder inaktiv."
            )

        sender = await _load_user(db, from_user_id)

        # --- Persist handoff record ---
        handoff = OrderHandoff(
            order_id=order_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            handoff_type=handoff_type,
            status=HandoffStatusEnum.PENDING,
            notes=notes,
        )

        async with transactional(db):
            db.add(handoff)
            await db.flush()

        # Re-fetch with relationships for response serialisation
        handoff = await _load_handoff_with_relations(db, handoff.id)

        # --- Notify recipient ---
        sender_name = (
            f"{sender.first_name} {sender.last_name}" if sender else f"Benutzer #{from_user_id}"
        )
        type_label = _HANDOFF_TYPE_LABELS.get(handoff_type, handoff_type.value)
        await _send_notification(
            db=db,
            user_id=to_user_id,
            title=f"Auftrag #{order_id} uebergeben: {type_label}",
            message=(
                f"Auftrag #{order_id} \"{order.title or ''}\" wurde Ihnen "
                f"uebergeben von {sender_name}."
                + (f"\nHinweis: {notes}" if notes else "")
            ),
            severity=NotificationSeverityEnum.INFO,
            order_id=order_id,
        )

        # --- Publish order update event ---
        try:
            await publish_event(
                "order_updates",
                json.dumps(
                    {
                        "action": "handoff_created",
                        "order_id": order_id,
                        "handoff_id": handoff.id,
                        "from_user_id": from_user_id,
                        "to_user_id": to_user_id,
                        "handoff_type": handoff_type.value,
                    }
                ),
            )
        except Exception as exc:
            logger.error(
                "Failed to publish handoff_created event",
                extra={"handoff_id": handoff.id, "error": str(exc)},
                exc_info=True,
            )

        logger.info(
            "Handoff created",
            extra={
                "handoff_id": handoff.id,
                "order_id": order_id,
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
                "type": handoff_type.value,
            },
        )
        return handoff

    @staticmethod
    async def accept_handoff(
        db: AsyncSession,
        handoff_id: int,
        user_id: int,
        response_notes: Optional[str] = None,
    ) -> OrderHandoff:
        """
        Accept a PENDING handoff as the designated recipient.

        Only the intended recipient (to_user_id) may accept.

        Raises:
            ValueError: If handoff not found, already responded, or wrong user.
        """
        handoff = await _load_handoff_with_relations(db, handoff_id)
        if not handoff:
            raise ValueError(f"Uebergabe #{handoff_id} nicht gefunden.")

        if handoff.to_user_id != user_id:
            raise ValueError("Nur der vorgesehene Empfaenger kann diese Uebergabe bestaetigen.")

        if handoff.status != HandoffStatusEnum.PENDING:
            raise ValueError(
                f"Uebergabe #{handoff_id} ist bereits {handoff.status.value} und kann nicht mehr bearbeitet werden."
            )

        async with transactional(db):
            handoff.status = HandoffStatusEnum.ACCEPTED
            handoff.responded_at = datetime.utcnow()
            if response_notes:
                handoff.response_notes = response_notes
            await db.flush()

        # Re-fetch for clean response with all relationships
        handoff = await _load_handoff_with_relations(db, handoff_id)

        # --- Notify sender ---
        recipient_name = (
            f"{handoff.to_user.first_name} {handoff.to_user.last_name}"
            if handoff.to_user
            else f"Benutzer #{user_id}"
        )
        if handoff.from_user_id:
            await _send_notification(
                db=db,
                user_id=handoff.from_user_id,
                title=f"Uebergabe bestaetigt: Auftrag #{handoff.order_id}",
                message=(
                    f"{recipient_name} hat die Uebergabe fuer Auftrag #{handoff.order_id} bestaetigt."
                    + (f"\nKommentar: {response_notes}" if response_notes else "")
                ),
                severity=NotificationSeverityEnum.INFO,
                order_id=handoff.order_id,
            )

        # --- Publish event ---
        try:
            await publish_event(
                "order_updates",
                json.dumps(
                    {
                        "action": "handoff_accepted",
                        "order_id": handoff.order_id,
                        "handoff_id": handoff_id,
                        "accepted_by": user_id,
                    }
                ),
            )
        except Exception as exc:
            logger.error(
                "Failed to publish handoff_accepted event",
                extra={"handoff_id": handoff_id, "error": str(exc)},
                exc_info=True,
            )

        logger.info(
            "Handoff accepted",
            extra={
                "handoff_id": handoff_id,
                "order_id": handoff.order_id,
                "accepted_by": user_id,
            },
        )
        return handoff

    @staticmethod
    async def decline_handoff(
        db: AsyncSession,
        handoff_id: int,
        user_id: int,
        response_notes: str,
    ) -> OrderHandoff:
        """
        Decline a PENDING handoff with a mandatory reason.

        Only the intended recipient (to_user_id) may decline.

        Raises:
            ValueError: If handoff not found, already responded, wrong user,
                        or response_notes is blank.
        """
        if not response_notes or not response_notes.strip():
            raise ValueError("Eine Begruendung fuer die Ablehnung ist Pflicht.")

        handoff = await _load_handoff_with_relations(db, handoff_id)
        if not handoff:
            raise ValueError(f"Uebergabe #{handoff_id} nicht gefunden.")

        if handoff.to_user_id != user_id:
            raise ValueError("Nur der vorgesehene Empfaenger kann diese Uebergabe ablehnen.")

        if handoff.status != HandoffStatusEnum.PENDING:
            raise ValueError(
                f"Uebergabe #{handoff_id} ist bereits {handoff.status.value} und kann nicht mehr bearbeitet werden."
            )

        async with transactional(db):
            handoff.status = HandoffStatusEnum.DECLINED
            handoff.responded_at = datetime.utcnow()
            handoff.response_notes = response_notes.strip()
            await db.flush()

        # Re-fetch for clean response
        handoff = await _load_handoff_with_relations(db, handoff_id)

        # --- Notify sender ---
        recipient_name = (
            f"{handoff.to_user.first_name} {handoff.to_user.last_name}"
            if handoff.to_user
            else f"Benutzer #{user_id}"
        )
        if handoff.from_user_id:
            await _send_notification(
                db=db,
                user_id=handoff.from_user_id,
                title=f"Uebergabe abgelehnt: Auftrag #{handoff.order_id}",
                message=(
                    f"{recipient_name} hat die Uebergabe fuer Auftrag #{handoff.order_id} abgelehnt.\n"
                    f"Begruendung: {response_notes.strip()}"
                ),
                severity=NotificationSeverityEnum.WARNING,
                order_id=handoff.order_id,
            )

        # --- Publish event ---
        try:
            await publish_event(
                "order_updates",
                json.dumps(
                    {
                        "action": "handoff_declined",
                        "order_id": handoff.order_id,
                        "handoff_id": handoff_id,
                        "declined_by": user_id,
                        "reason": response_notes.strip(),
                    }
                ),
            )
        except Exception as exc:
            logger.error(
                "Failed to publish handoff_declined event",
                extra={"handoff_id": handoff_id, "error": str(exc)},
                exc_info=True,
            )

        logger.info(
            "Handoff declined",
            extra={
                "handoff_id": handoff_id,
                "order_id": handoff.order_id,
                "declined_by": user_id,
            },
        )
        return handoff

    @staticmethod
    async def get_pending_handoffs(
        db: AsyncSession, user_id: int
    ) -> List[OrderHandoff]:
        """
        Return all PENDING handoffs where the given user is the recipient.

        Used to populate the "Meine offenen Uebergaben" view — the goldsmith
        sees at a glance which orders are waiting for their acknowledgement.
        """
        result = await db.execute(
            select(OrderHandoff)
            .options(
                selectinload(OrderHandoff.from_user),
                selectinload(OrderHandoff.to_user),
                selectinload(OrderHandoff.order),
            )
            .where(
                OrderHandoff.to_user_id == user_id,
                OrderHandoff.status == HandoffStatusEnum.PENDING,
            )
            .order_by(OrderHandoff.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_order_handoff_history(
        db: AsyncSession, order_id: int
    ) -> List[OrderHandoff]:
        """
        Return the complete handoff history for a given order, newest first.

        Provides the full Uebergabe-Protokoll — who passed the order to whom
        at which point in the production chain.
        """
        result = await db.execute(
            select(OrderHandoff)
            .options(
                selectinload(OrderHandoff.from_user),
                selectinload(OrderHandoff.to_user),
            )
            .where(OrderHandoff.order_id == order_id)
            .order_by(OrderHandoff.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_handoff(
        db: AsyncSession, handoff_id: int
    ) -> Optional[OrderHandoff]:
        """Fetch a single handoff by ID (with relationships)."""
        return await _load_handoff_with_relations(db, handoff_id)
