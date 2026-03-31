# src/goldsmith_erp/api/routers/calendar.py
"""
Calendar / planning API.

Endpoints:
  GET    /api/v1/calendar/events          — list stored events (date-range filterable)
  POST   /api/v1/calendar/events          — create a new event
  GET    /api/v1/calendar/events/{id}     — fetch a single stored event
  PUT    /api/v1/calendar/events/{id}     — update a stored event
  DELETE /api/v1/calendar/events/{id}     — delete a stored event
  GET    /api/v1/calendar/deadlines       — virtual events from order deadlines
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import CalendarEventType, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.calendar import (
    CalendarDeadlineEvent,
    CalendarEventCreate,
    CalendarEventResponse,
    CalendarEventUpdate,
)
from goldsmith_erp.services.calendar_service import CalendarService

router = APIRouter()


# ---------------------------------------------------------------------------
# List / query
# ---------------------------------------------------------------------------


@router.get("/events", response_model=List[CalendarEventResponse])
@require_permission(Permission.ORDER_VIEW)
async def list_events(
    date_from: Optional[str] = Query(
        None,
        description="ISO date string for range start, e.g. 2026-03-01",
    ),
    date_to: Optional[str] = Query(
        None,
        description="ISO date string for range end, e.g. 2026-03-31",
    ),
    event_type: Optional[CalendarEventType] = Query(
        None,
        description="Filter by event type",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[CalendarEventResponse]:
    """
    List stored calendar events with optional date-range and type filter.

    All authenticated users with ORDER_VIEW permission can query events.
    Events are ordered by start_datetime ascending.
    """
    try:
        events = await CalendarService.get_events(
            db,
            date_from=date_from,
            date_to=date_to,
            event_type=event_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return events  # type: ignore[return-value]


@router.get("/deadlines", response_model=List[CalendarDeadlineEvent])
@require_permission(Permission.ORDER_VIEW)
async def get_deadlines(
    start: Optional[str] = Query(
        None,
        description="ISO date string for range start, e.g. 2026-03-01",
    ),
    end: Optional[str] = Query(
        None,
        description="ISO date string for range end, e.g. 2026-03-31",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[CalendarDeadlineEvent]:
    """
    Return order deadlines as virtual calendar events.

    These are synthesised on-the-fly from the orders table — nothing is
    persisted in calendar_events.  The frontend calendarApi.getDeadlines()
    calls this endpoint.

    Query parameters use 'start'/'end' to match the existing
    /orders/calendar/deadlines contract the frontend already expects.
    """
    try:
        return await CalendarService.get_order_deadlines(
            db, date_from=start, date_to=end
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Single-event operations
# ---------------------------------------------------------------------------


@router.get("/events/{event_id}", response_model=CalendarEventResponse)
@require_permission(Permission.ORDER_VIEW)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalendarEventResponse:
    """Fetch a single stored calendar event by ID."""
    event = await CalendarService.get_event(db, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calendar event {event_id} not found",
        )
    return event  # type: ignore[return-value]


@router.post(
    "/events",
    response_model=CalendarEventResponse,
    status_code=status.HTTP_201_CREATED,
)
@require_permission(Permission.ORDER_CREATE)
async def create_event(
    event_in: CalendarEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalendarEventResponse:
    """
    Create a new calendar event.

    The event is owned by the authenticated user.  GOLDSMITH and ADMIN roles
    can create events (ORDER_CREATE permission required).
    """
    return await CalendarService.create_event(db, event_in, user_id=current_user.id)  # type: ignore[return-value]


@router.put("/events/{event_id}", response_model=CalendarEventResponse)
@require_permission(Permission.ORDER_EDIT)
async def update_event(
    event_id: int,
    event_in: CalendarEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalendarEventResponse:
    """
    Partially update a stored calendar event.

    Requires ORDER_EDIT permission (GOLDSMITH or ADMIN).
    """
    updated = await CalendarService.update_event(db, event_id, event_in)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calendar event {event_id} not found",
        )
    return updated  # type: ignore[return-value]


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permission(Permission.ORDER_DELETE)
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete a stored calendar event.

    Requires ORDER_DELETE permission (ADMIN only).
    Returns 204 No Content on success, 404 if not found.
    """
    deleted = await CalendarService.delete_event(db, event_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calendar event {event_id} not found",
        )
