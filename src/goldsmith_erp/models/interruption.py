# src/goldsmith_erp/models/interruption.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
    # D-15 / W2-14: set once work resumes (see migration
    # 20260925_w214_interrupt_resume). ``None`` with ``duration_minutes ==
    # 0`` means the interruption is still open (the timer is paused).
    resumed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
