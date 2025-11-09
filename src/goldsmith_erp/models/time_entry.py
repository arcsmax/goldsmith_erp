# src/goldsmith_erp/models/time_entry.py
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from typing import Optional, Dict, Any, List

class TimeEntryBase(BaseModel):
    """Basis-Schema für TimeEntry mit Input Validation."""
    order_id: int = Field(..., gt=0, description="Order ID (must be positive)")
    activity_id: int = Field(..., gt=0, description="Activity ID (must be positive)")
    location: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Storage location (1-50 characters)"
    )
    notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Notes (max 2000 characters)"
    )

class TimeEntryStart(BaseModel):
    """Schema zum Starten einer Time-Entry mit Input Validation."""
    order_id: int = Field(..., gt=0, description="Order ID (must be positive)")
    activity_id: int = Field(..., gt=0, description="Activity ID (must be positive)")
    user_id: int = Field(..., gt=0, description="User ID (must be positive)")
    location: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Storage location"
    )
    extra_metadata: Optional[Dict[str, Any]] = None

class TimeEntryStop(BaseModel):
    """Schema zum Stoppen einer Time-Entry."""
    complexity_rating: Optional[int] = Field(None, ge=1, le=5)
    quality_rating: Optional[int] = Field(None, ge=1, le=5)
    rework_required: bool = False
    notes: Optional[str] = None

class TimeEntryCreate(TimeEntryBase):
    """Schema für manuelle TimeEntry-Erstellung (mit Start/End) mit Input Validation."""
    user_id: int = Field(..., gt=0, description="User ID (must be positive)")
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(
        None,
        gt=0,
        le=1440,  # Max 24 hours (1440 minutes)
        description="Duration in minutes (1-1440)"
    )
    complexity_rating: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Complexity rating (1-5)"
    )
    quality_rating: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Quality rating (1-5)"
    )
    rework_required: bool = False
    extra_metadata: Optional[Dict[str, Any]] = None

    @field_validator('end_time')
    @classmethod
    def validate_end_time(cls, v: Optional[datetime], info) -> Optional[datetime]:
        """Validate end_time is after start_time."""
        if v is not None and 'start_time' in info.data:
            start_time = info.data['start_time']
            if v <= start_time:
                raise ValueError("end_time must be after start_time")
            # Prevent extremely long durations (more than 7 days)
            duration_days = (v - start_time).days
            if duration_days > 7:
                raise ValueError("Duration cannot exceed 7 days")
        return v

class TimeEntryUpdate(BaseModel):
    """Schema für TimeEntry-Updates mit Input Validation."""
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(
        None,
        gt=0,
        le=1440,  # Max 24 hours
        description="Duration in minutes (1-1440)"
    )
    location: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Storage location"
    )
    complexity_rating: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Complexity rating (1-5)"
    )
    quality_rating: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Quality rating (1-5)"
    )
    rework_required: Optional[bool] = None
    notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Notes (max 2000 characters)"
    )
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
