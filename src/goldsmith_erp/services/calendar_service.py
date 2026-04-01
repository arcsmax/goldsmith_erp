# src/goldsmith_erp/services/calendar_service.py
"""
Calendar service — business logic for event management and order-deadline synthesis.

All public methods are async and accept AsyncSession as their first parameter,
in line with the project service-layer convention.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    CalendarEvent as CalendarEventModel,
    CalendarEventType,
    Order as OrderModel,
)
from goldsmith_erp.models.calendar import (
    CalendarDeadlineEvent,
    CalendarEventCreate,
    CalendarEventUpdate,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRAFFIC_GREEN = "green"
_TRAFFIC_YELLOW = "yellow"
_TRAFFIC_RED = "red"
_TRAFFIC_GREY = "grey"


def _traffic_light(order: OrderModel) -> tuple[str, int]:
    """
    Return (traffic_light_colour, days_until_deadline) for an order.

    Mirrors the frontend getTrafficClass() logic so the backend and UI agree.
    """
    now = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    deadline = order.deadline.replace(hour=0, minute=0, second=0, microsecond=0)
    days = (deadline - now).days

    status_val: str = (
        order.status.value if hasattr(order.status, "value") else order.status
    )
    if status_val in ("completed", "delivered"):
        return _TRAFFIC_GREY, days

    if days < 2:
        return _TRAFFIC_RED, days
    if days <= 5:
        return _TRAFFIC_YELLOW, days
    return _TRAFFIC_GREEN, days


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO date string into a datetime, returning None if not provided."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid date format '{value}'. Expected ISO format, e.g. 2026-03-31."
        ) from exc


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class CalendarService:
    """Calendar event CRUD and order-deadline synthesis."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_events(
        db: AsyncSession,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        event_type: Optional[CalendarEventType] = None,
        user_id: Optional[int] = None,
    ) -> List[CalendarEventModel]:
        """
        Return stored calendar events filtered by date range, type, and/or owner.

        Uses selectinload() on order and user relationships to avoid N+1 queries.
        """
        from_dt = _parse_date(date_from)
        to_dt = _parse_date(date_to)

        query = select(CalendarEventModel).options(
            selectinload(CalendarEventModel.order),
            selectinload(CalendarEventModel.user),
        )

        if from_dt:
            query = query.where(CalendarEventModel.start_datetime >= from_dt)
        if to_dt:
            # Include events that start on or before the end of the last day
            to_end_of_day = to_dt.replace(hour=23, minute=59, second=59)
            query = query.where(CalendarEventModel.start_datetime <= to_end_of_day)
        if event_type:
            query = query.where(CalendarEventModel.event_type == event_type)
        if user_id is not None:
            query = query.where(CalendarEventModel.user_id == user_id)

        query = query.order_by(CalendarEventModel.start_datetime)

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_event(
        db: AsyncSession, event_id: int
    ) -> Optional[CalendarEventModel]:
        """Fetch a single event by ID with relationships eagerly loaded."""
        result = await db.execute(
            select(CalendarEventModel)
            .options(
                selectinload(CalendarEventModel.order),
                selectinload(CalendarEventModel.user),
            )
            .where(CalendarEventModel.id == event_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_order_deadlines(
        db: AsyncSession,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[CalendarDeadlineEvent]:
        """
        Synthesise virtual calendar events from Order.deadline values.

        These are NOT stored in calendar_events — they are generated at
        query-time so the calendar always reflects the current order state.
        Mirrors the shape expected by the frontend calendarApi.getDeadlines().
        """
        from_dt = _parse_date(date_from)
        to_dt = _parse_date(date_to)

        query = (
            select(OrderModel)
            .where(OrderModel.deadline.isnot(None))
            .where(OrderModel.is_deleted.is_(False))
            .options(selectinload(OrderModel.customer))
            .order_by(OrderModel.deadline)
        )
        if from_dt:
            query = query.where(OrderModel.deadline >= from_dt)
        if to_dt:
            query = query.where(
                OrderModel.deadline <= to_dt.replace(hour=23, minute=59, second=59)
            )

        result = await db.execute(query)
        orders: List[OrderModel] = list(result.scalars().all())

        events: List[CalendarDeadlineEvent] = []
        for order in orders:
            colour, days = _traffic_light(order)
            status_val: str = (
                order.status.value if hasattr(order.status, "value") else order.status
            )
            customer_name: Optional[str] = None
            if order.customer:
                customer_name = (
                    f"{order.customer.first_name} {order.customer.last_name}".strip()
                )

            events.append(
                CalendarDeadlineEvent(
                    id=order.id,
                    title=order.title or f"Auftrag #{order.id}",
                    event_type=CalendarEventType.ORDER_DEADLINE,
                    start_datetime=order.deadline,  # type: ignore[arg-type]
                    all_day=True,
                    order_id=order.id,
                    status=status_val,
                    customer_name=customer_name,
                    traffic_light=colour,
                    days_until_deadline=days,
                )
            )
        return events

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create_event(
        db: AsyncSession,
        event_in: CalendarEventCreate,
        user_id: int,
    ) -> CalendarEventModel:
        """
        Persist a new calendar event.

        user_id comes from the authenticated user, not the request body.
        """
        db_event = CalendarEventModel(
            title=event_in.title,
            description=event_in.description,
            event_type=event_in.event_type,
            start_datetime=event_in.start_datetime,
            end_datetime=event_in.end_datetime,
            all_day=event_in.all_day,
            order_id=event_in.order_id,
            user_id=user_id,
            color=event_in.color,
            recurrence=event_in.recurrence,
        )
        db.add(db_event)
        try:
            await db.commit()
            await db.refresh(db_event)
        except Exception:
            await db.rollback()
            raise

        # Re-fetch with relationships for the response
        refreshed = await CalendarService.get_event(db, db_event.id)
        assert refreshed is not None
        return refreshed

    @staticmethod
    async def update_event(
        db: AsyncSession,
        event_id: int,
        event_in: CalendarEventUpdate,
    ) -> Optional[CalendarEventModel]:
        """
        Apply a partial update to an existing event.

        Returns None if the event does not exist.
        """
        existing = await CalendarService.get_event(db, event_id)
        if existing is None:
            return None

        update_data = event_in.model_dump(exclude_unset=True)
        if not update_data:
            return existing

        try:
            await db.execute(
                update(CalendarEventModel)
                .where(CalendarEventModel.id == event_id)
                .values(**update_data)
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        return await CalendarService.get_event(db, event_id)

    @staticmethod
    async def delete_event(db: AsyncSession, event_id: int) -> bool:
        """
        Delete an event by ID.

        Returns True if the event was deleted, False if it was not found.
        """
        existing = await CalendarService.get_event(db, event_id)
        if existing is None:
            return False

        try:
            await db.execute(
                delete(CalendarEventModel).where(CalendarEventModel.id == event_id)
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            "Calendar event deleted",
            extra={"event_id": event_id},
        )
        return True
