# src/goldsmith_erp/models/activity.py
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from typing import Optional

class ActivityBase(BaseModel):
    """Basis-Schema für Activities mit Input Validation."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Activity name (1-100 characters)"
    )
    category: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Activity category (fabrication, administration, waiting)"
    )
    icon: Optional[str] = Field(
        None,
        max_length=10,
        description="Emoji icon (max 10 characters)"
    )
    color: Optional[str] = Field(
        None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Hex color code (e.g., #FF6B6B)"
    )

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Validate category is one of the allowed values."""
        allowed = ["fabrication", "administration", "waiting"]
        if v.lower() not in allowed:
            raise ValueError(
                f"Category must be one of: {', '.join(allowed)}. Got: {v}"
            )
        return v.lower()

class ActivityCreate(ActivityBase):
    """Schema für Activity-Erstellung mit Validation."""
    is_custom: bool = True
    created_by: Optional[int] = Field(
        None,
        gt=0,
        description="User ID who created this activity"
    )

class ActivityUpdate(BaseModel):
    """Schema für Activity-Updates mit Input Validation."""
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="Activity name"
    )
    category: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Activity category"
    )
    icon: Optional[str] = Field(
        None,
        max_length=10,
        description="Emoji icon"
    )
    color: Optional[str] = Field(
        None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Hex color code"
    )

    @field_validator('category')
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        """Validate category is one of the allowed values."""
        if v is not None:
            allowed = ["fabrication", "administration", "waiting"]
            if v.lower() not in allowed:
                raise ValueError(
                    f"Category must be one of: {', '.join(allowed)}. Got: {v}"
                )
            return v.lower()
        return v

class ActivityRead(ActivityBase):
    """Schema für Activity-Anzeige."""
    id: int
    usage_count: int
    average_duration_minutes: Optional[float] = None
    last_used: Optional[datetime] = None
    is_custom: bool
    created_by: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ActivityWithStats(ActivityRead):
    """Activity mit erweiterten Statistiken für Analytics."""
    total_time_minutes: Optional[float] = None
    most_common_order_type: Optional[str] = None
