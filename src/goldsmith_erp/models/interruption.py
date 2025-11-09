# src/goldsmith_erp/models/interruption.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class InterruptionBase(BaseModel):
    """Basis-Schema für Interruption."""
    reason: str  # customer_call, material_fetch, etc.
    duration_minutes: int

class InterruptionCreate(InterruptionBase):
    """Schema für Interruption-Erstellung."""
    time_entry_id: str  # UUID

class InterruptionRead(InterruptionBase):
    """Schema für Interruption-Anzeige."""
    id: int
    time_entry_id: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
