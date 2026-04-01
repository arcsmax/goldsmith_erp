# src/goldsmith_erp/models/handoff.py
"""
Pydantic schemas for the order handoff protocol (Stabuebergabe).

An order handoff represents the formal moment when one goldsmith finishes
their part of an order and passes it to the next craftsperson.  The
receiving goldsmith must explicitly accept or decline before the order
changes hands in the system.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from goldsmith_erp.db.models import HandoffStatusEnum, HandoffTypeEnum


# ---------------------------------------------------------------------------
# Request schemas (inbound from API consumer)
# ---------------------------------------------------------------------------


class HandoffCreate(BaseModel):
    """
    Payload for POST /api/v1/orders/{id}/handoff.

    The sending goldsmith specifies who should receive the order, what kind
    of handoff it is, and an optional message for the recipient.
    """
    to_user_id: int = Field(..., gt=0, description="ID des empfangenden Goldschmieds")
    handoff_type: HandoffTypeEnum
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Hinweis fuer den Empfaenger, z.B. 'Loeten fertig, Lot an Stelle 3 pruefen'",
    )


class HandoffAccept(BaseModel):
    """Payload for PUT /api/v1/handoffs/{id}/accept (optional response note)."""
    response_notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optionaler Kommentar bei Uebernahme",
    )


class HandoffDecline(BaseModel):
    """
    Payload for PUT /api/v1/handoffs/{id}/decline.

    A decline reason is required — in the workshop, the sender needs to know
    exactly what to fix before making another handoff attempt.
    """
    response_notes: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Begruendung fuer die Ablehnung (Pflichtfeld)",
    )


# ---------------------------------------------------------------------------
# Response schemas (outbound to API consumer)
# ---------------------------------------------------------------------------


class HandoffUserSummary(BaseModel):
    """Compact user representation embedded in handoff responses."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class HandoffRead(BaseModel):
    """
    Full handoff record returned to the API consumer.

    Includes embedded user summaries so the frontend can display
    "Von: Maria Schmidt  An: Klaus Huber" without additional lookups.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    from_user_id: Optional[int]
    to_user_id: Optional[int]
    handoff_type: HandoffTypeEnum
    status: HandoffStatusEnum
    notes: Optional[str]
    response_notes: Optional[str]
    created_at: datetime
    responded_at: Optional[datetime]

    # Embedded user info (populated via relationship eager-loading)
    from_user: Optional[HandoffUserSummary] = None
    to_user: Optional[HandoffUserSummary] = None
