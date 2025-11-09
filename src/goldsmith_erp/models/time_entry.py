# src/goldsmith_erp/models/time_entry.py
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, Dict, Any, List

class TimeEntryBase(BaseModel):
    """Basis-Schema für TimeEntry."""
    order_id: int
    activity_id: int
    location: Optional[str] = None
    notes: Optional[str] = None

class TimeEntryStart(BaseModel):
    """Schema zum Starten einer Time-Entry."""
    order_id: int
    activity_id: int
    user_id: int
    location: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None

class TimeEntryStop(BaseModel):
    """Schema zum Stoppen einer Time-Entry."""
    complexity_rating: Optional[int] = Field(None, ge=1, le=5)
    quality_rating: Optional[int] = Field(None, ge=1, le=5)
    rework_required: bool = False
    notes: Optional[str] = None

class TimeEntryCreate(TimeEntryBase):
    """Schema für manuelle TimeEntry-Erstellung (mit Start/End)."""
    user_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    complexity_rating: Optional[int] = Field(None, ge=1, le=5)
    quality_rating: Optional[int] = Field(None, ge=1, le=5)
    rework_required: bool = False
    extra_metadata: Optional[Dict[str, Any]] = None

class TimeEntryUpdate(BaseModel):
    """Schema für TimeEntry-Updates."""
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    complexity_rating: Optional[int] = Field(None, ge=1, le=5)
    quality_rating: Optional[int] = Field(None, ge=1, le=5)
    rework_required: Optional[bool] = None
    notes: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None

class TimeEntryRead(TimeEntryBase):
    """Schema für TimeEntry-Anzeige."""
    id: str  # UUID
    user_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    complexity_rating: Optional[int] = None
    quality_rating: Optional[int] = None
    rework_required: bool
    extra_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Nested schemas für relationships
from .activity import ActivityRead

class TimeEntryWithDetails(TimeEntryRead):
    """TimeEntry mit eingebetteten Activity, Order und User Details."""
    activity: Optional[ActivityRead] = None
    order_title: Optional[str] = None
    user_name: Optional[str] = None
