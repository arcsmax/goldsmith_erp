# src/goldsmith_erp/models/ml.py
"""
Pydantic schemas for the ML prediction and monitoring API.

All float fields are guaranteed to be plain Python float/int — no numpy types.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


class DurationPredictionRequest(BaseModel):
    """Feature vector for a duration prediction request."""

    order_type: Optional[str] = Field(
        None,
        description="Type of jewelry piece (ring, chain, pendant, earrings, bracelet, …)",
        examples=["ring"],
    )
    complexity_rating: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Complexity from 1 (simple) to 5 (highly complex)",
    )
    metal_type: Optional[str] = Field(
        None,
        description="Metal alloy identifier, e.g. gold_18k, silver_925",
    )
    estimated_weight_g: Optional[float] = Field(
        None,
        gt=0,
        description="Expected metal weight in grams",
    )
    finish_type: Optional[str] = Field(
        None,
        description="Surface finish: high_polish, matte, brushed, hammered, oxidized, mixed",
    )
    # Gemstone details
    gemstone_count: Optional[int] = Field(
        None,
        ge=0,
        description="Number of stones to be set",
    )
    gemstone_type: Optional[str] = Field(
        None,
        description="Primary stone type, e.g. diamond, ruby",
    )
    gemstone_carat: Optional[float] = Field(
        None,
        gt=0,
        description="Total carat weight of stones",
    )


class SimilarOrder(BaseModel):
    """A past order used as a nearest-neighbour reference."""

    order_id: int
    actual_hours: float
    order_type: Optional[str] = None
    complexity_rating: Optional[int] = None
    similarity_score: float = Field(ge=0.0, le=1.0)


class DurationPredictionResponse(BaseModel):
    """Predicted duration with confidence information."""

    estimated_hours: float = Field(description="Point estimate in hours")
    confidence_interval_low: float = Field(description="Lower 80% CI bound in hours")
    confidence_interval_high: float = Field(description="Upper 80% CI bound in hours")
    confidence_level: str = Field(
        description="Qualitative level: high | medium | low",
    )
    similar_orders: list[SimilarOrder] = Field(
        default_factory=list,
        description="Up to 5 most similar completed orders",
    )
    model_status: str = Field(
        description="trained | not_trained | unavailable",
    )
    is_heuristic: bool = Field(
        default=False,
        description="True when the model was not trained and a rule-based estimate was used",
    )


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------


class AnomalyAlertResponse(BaseModel):
    """A single anomaly alert for a running time entry."""

    time_entry_id: str
    order_id: int
    order_title: Optional[str] = None
    activity_id: int
    activity_name: Optional[str] = None
    user_id: int
    elapsed_minutes: float
    expected_minutes: float
    anomaly_score: float = Field(
        description="Relative deviation: (elapsed - expected) / expected",
    )
    severity: str = Field(description="warning | critical")
    started_at: datetime
    detected_at: datetime


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------


class TrainingMetrics(BaseModel):
    """Regression metrics from the last model training run."""

    rmse: Optional[float] = None
    mape: Optional[float] = None
    r2: Optional[float] = None
    data_size: int = Field(description="Number of training samples")


class ModelStatusResponse(BaseModel):
    """Current state of the ML duration predictor."""

    model_name: str
    version: Optional[str] = None
    trained_at: Optional[datetime] = None
    metrics: Optional[TrainingMetrics] = None
    training_data_size: int = 0
    is_ready: bool
    message: Optional[str] = None


class TrainResponse(BaseModel):
    """Result of a manual training trigger."""

    success: bool
    message: str
    metrics: Optional[TrainingMetrics] = None
    duration_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------


class FieldCoverage(BaseModel):
    """Coverage statistics for a single ML feature field."""

    field_name: str
    total_records: int
    populated_records: int
    coverage_pct: float


class DataQualityResponse(BaseModel):
    """Overall dataset health for ML training."""

    total_completed_orders: int
    orders_with_actual_hours: int
    orders_with_order_type: int
    orders_with_complexity_rating: int
    orders_with_metal_type: int
    orders_with_estimated_weight: int
    readiness_score: float = Field(
        ge=0.0,
        le=1.0,
        description="0–1 composite readiness score for training",
    )
    field_coverage: list[FieldCoverage] = Field(default_factory=list)
    recommendation: Optional[str] = None


# ---------------------------------------------------------------------------
# Activity statistics
# ---------------------------------------------------------------------------


class ActivityDurationStats(BaseModel):
    """Aggregated time-tracking statistics for a single activity."""

    activity_id: int
    activity_name: str
    activity_category: Optional[str] = None
    sample_count: int
    mean_minutes: float
    median_minutes: float
    std_minutes: float
    p95_minutes: float
    min_minutes: float
    max_minutes: float


class ComplexityBreakdown(BaseModel):
    """Stats for one complexity level within an activity."""

    complexity_rating: int
    sample_count: int
    mean_minutes: float
    median_minutes: float


class ActivityDetailResponse(ActivityDurationStats):
    """Detailed stats for a single activity, including per-complexity breakdowns."""

    per_complexity: list[ComplexityBreakdown] = Field(default_factory=list)
