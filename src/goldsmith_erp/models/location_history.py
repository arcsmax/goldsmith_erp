# src/goldsmith_erp/models/location_history.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LocationHistoryBase(BaseModel):
    """Basis-Schema für LocationHistory."""

    order_id: int
    location: str


class LocationHistoryCreate(LocationHistoryBase):
    """Schema für LocationHistory-Erstellung."""

    changed_by: int


class LocationHistoryRead(LocationHistoryBase):
    """Schema für LocationHistory-Anzeige."""

    id: int
    changed_by: int
    timestamp: datetime
    user_name: Optional[str] = None  # Für erweiterte Anzeige

    model_config = ConfigDict(from_attributes=True)
