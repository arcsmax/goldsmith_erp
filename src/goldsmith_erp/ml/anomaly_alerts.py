"""
Anomaly alert Pydantic models for time-tracking anomaly detection.

AnomalyResult is the low-level return from AnomalyDetector.check_anomaly().
AnomalyAlert is the richer model published over WebSocket / returned by the
active-alerts API endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    """
    Severity tiers based on the deviation factor (actual / expected duration).

    LOW    — 1.5x – 2x   expected duration: worth noting, not urgent
    MEDIUM — 2x   – 3x   expected duration: goldsmith should check in
    HIGH   — > 3x         expected duration: something is clearly wrong
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def severity_from_factor(deviation_factor: float) -> AlertSeverity:
    """Derive severity from a pre-computed deviation factor."""
    if deviation_factor >= 3.0:
        return AlertSeverity.HIGH
    if deviation_factor >= 2.0:
        return AlertSeverity.MEDIUM
    return AlertSeverity.LOW


class AnomalyResult(BaseModel):
    """
    Low-level result returned by AnomalyDetector.check_anomaly().

    Contains enough information to build a full AnomalyAlert without an
    additional database round-trip.
    """
    is_anomaly: bool
    severity: Optional[AlertSeverity] = None

    # Duration context
    expected_duration_minutes: float
    actual_duration_minutes: int
    deviation_factor: float  # actual / expected — e.g. 2.5 means 2.5x over

    # Human-readable explanation in German
    suggested_reasons: list[str] = Field(default_factory=list)

    # Detection method that fired
    detection_method: str = "statistical"  # "statistical" | "isolation_forest"


class AnomalyAlert(BaseModel):
    """
    Rich alert model published to the WebSocket channel ``anomaly_alerts``.

    Created after check_anomaly() returns is_anomaly=True and enriched with
    order/user context before publishing.
    """
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    time_entry_id: str
    order_id: int
    activity_name: str
    user_name: str

    # Duration
    expected_duration_minutes: float
    actual_duration_minutes: int
    deviation_factor: float

    # Severity
    severity: AlertSeverity

    # German suggested reasons
    suggested_reasons: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
