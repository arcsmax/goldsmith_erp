# src/goldsmith_erp/models/activity.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class ActivityBase(BaseModel):
    """Basis-Schema für Activities."""
    name: str
    category: str  # fabrication, administration, waiting
    icon: Optional[str] = None  # Emoji
    color: Optional[str] = None  # Hex color #FF6B6B

class ActivityCreate(ActivityBase):
    """Schema für Activity-Erstellung."""
    is_custom: bool = True
    created_by: Optional[int] = None

class ActivityUpdate(BaseModel):
    """Schema für Activity-Updates."""
    name: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None

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
