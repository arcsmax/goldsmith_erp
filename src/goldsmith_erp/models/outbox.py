# src/goldsmith_erp/models/outbox.py
"""API schemas for the admin outbox view (ARCH-04, ADR-2026-09-25-outbox)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict

OutboxStatusLiteral = Literal["pending", "sent", "failed", "dead"]


class OutboxMessageRead(BaseModel):
    """One queued message. ``payload`` holds ids only (no address/subject/body)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    status: OutboxStatusLiteral
    attempts: int
    payload: Dict[str, Any]
    next_attempt_at: datetime
    last_error: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None


class OutboxCounts(BaseModel):
    pending: int = 0
    sent: int = 0
    failed: int = 0
    dead: int = 0


class OutboxListResponse(BaseModel):
    items: List[OutboxMessageRead]
    counts: OutboxCounts
    mode: Literal["inline", "worker"]
