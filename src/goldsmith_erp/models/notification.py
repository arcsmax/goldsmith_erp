# src/goldsmith_erp/models/notification.py
"""
Pydantic schemas for the notification system.

Notification — persisted per-user in-app alert.
NotificationPreference — per-user opt-in/advance-days configuration.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from goldsmith_erp.db.models import NotificationSeverityEnum, NotificationTypeEnum


# ---------------------------------------------------------------------------
# Notification schemas
# ---------------------------------------------------------------------------


class NotificationBase(BaseModel):
    """Fields shared across notification schemas."""
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    notification_type: NotificationTypeEnum
    severity: NotificationSeverityEnum = NotificationSeverityEnum.INFO
    related_order_id: Optional[int] = Field(None, gt=0)
    related_customer_id: Optional[int] = Field(None, gt=0)


class NotificationCreate(NotificationBase):
    """Schema for creating a notification (internal service use)."""
    user_id: int = Field(..., gt=0, description="Recipient user ID")


class NotificationRead(NotificationBase):
    """Schema returned to the API consumer."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    is_read: bool
    read_at: Optional[datetime]
    created_at: datetime


class UnreadCountResponse(BaseModel):
    """Response schema for the unread-count badge endpoint."""
    unread_count: int


# ---------------------------------------------------------------------------
# NotificationPreference schemas
# ---------------------------------------------------------------------------


class NotificationPreferenceBase(BaseModel):
    notification_type: NotificationTypeEnum
    enabled: bool = True
    advance_days: int = Field(default=3, ge=1, le=30)


class NotificationPreferenceCreate(NotificationPreferenceBase):
    pass


class NotificationPreferenceUpdate(BaseModel):
    """Partial update — all fields optional."""
    enabled: Optional[bool] = None
    advance_days: Optional[int] = Field(None, ge=1, le=30)


class NotificationPreferenceRead(NotificationPreferenceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
