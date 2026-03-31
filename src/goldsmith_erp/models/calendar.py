# src/goldsmith_erp/models/calendar.py
"""
Pydantic schemas for the calendar/planning system.

CalendarEvent — manually created events stored in the calendar_events table.
CalendarDeadlineEvent — virtual event synthesised on-the-fly from Order.deadline;
    it is never persisted to calendar_events.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from goldsmith_erp.db.models import CalendarEventType


class CalendarEventBase(BaseModel):
    """Shared fields for create / update."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Event title (1-200 characters)",
    )
    description: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional event description",
    )
    event_type: CalendarEventType = Field(
        CalendarEventType.WORKSHOP_TASK,
        description="Event category",
    )
    start_datetime: datetime = Field(..., description="Start date/time of the event")
    end_datetime: Optional[datetime] = Field(
        None,
        description="End date/time (optional for reminders)",
    )
    all_day: bool = Field(False, description="True when the event spans the whole day")
    order_id: Optional[int] = Field(
        None,
        gt=0,
        description="Associated order ID (optional)",
    )
    color: Optional[str] = Field(
        None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Hex colour code for UI display, e.g. #FF6B6B",
    )
    recurrence: Optional[str] = Field(
        None,
        max_length=100,
        description="Simple recurrence label, e.g. 'weekly', 'monthly'",
    )

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty or only whitespace")
        return v

    @field_validator("end_datetime")
    @classmethod
    def end_after_start(
        cls, v: Optional[datetime], info: "FieldValidationInfo"  # type: ignore[name-defined]
    ) -> Optional[datetime]:
        # Pydantic v2: use model_fields_set; fall back gracefully if start not yet set
        start = info.data.get("start_datetime") if hasattr(info, "data") else None
        if v is not None and start is not None and v < start:
            raise ValueError("end_datetime must not be before start_datetime")
        return v


class CalendarEventCreate(CalendarEventBase):
    """Schema for creating a new calendar event."""

    # user_id is injected from the authenticated user in the router —
    # not supplied by the client.


class CalendarEventUpdate(BaseModel):
    """Schema for partial updates.  All fields optional."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    event_type: Optional[CalendarEventType] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    all_day: Optional[bool] = None
    order_id: Optional[int] = Field(None, gt=0)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    recurrence: Optional[str] = Field(None, max_length=100)

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty or only whitespace")
        return v


class CalendarEventResponse(BaseModel):
    """Full event response returned by the API."""

    id: int
    title: str
    description: Optional[str] = None
    event_type: CalendarEventType
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    all_day: bool
    order_id: Optional[int] = None
    user_id: int
    color: Optional[str] = None
    recurrence: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CalendarDeadlineEvent(BaseModel):
    """
    Virtual calendar entry synthesised from an Order's deadline field.

    Never persisted — generated at query-time by CalendarService.get_order_deadlines().
    The shape mirrors a subset of CalendarEventResponse so the frontend can treat
    both types uniformly.
    """

    id: int  # The order ID — unique within the deadline event namespace
    title: str
    event_type: CalendarEventType = CalendarEventType.ORDER_DEADLINE
    start_datetime: datetime
    all_day: bool = True
    order_id: int
    status: str
    customer_name: Optional[str] = None
    traffic_light: str  # "green" | "yellow" | "red" | "grey"
    days_until_deadline: int
    color: Optional[str] = None

    model_config = ConfigDict(from_attributes=False)


class CalendarQuery(BaseModel):
    """Query parameters for listing calendar events."""

    date_from: Optional[str] = Field(
        None,
        description="ISO date string for range start (inclusive), e.g. 2026-03-01",
    )
    date_to: Optional[str] = Field(
        None,
        description="ISO date string for range end (inclusive), e.g. 2026-03-31",
    )
    event_type: Optional[CalendarEventType] = Field(
        None,
        description="Filter by event type",
    )
