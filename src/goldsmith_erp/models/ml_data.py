# src/goldsmith_erp/models/ml_data.py
"""
Pydantic schemas for ML data quality monitoring and readiness reporting.

These schemas are returned by the MLDataService.get_training_data_quality()
endpoint (ADMIN and GOLDSMITH roles only).  They communicate whether the
workshop has accumulated enough clean data to train duration prediction models.

Readiness threshold: 100 completed orders with time entries and all core
ML features populated.  The data_readiness_score (0–100) indicates progress
toward that goal and highlights which fields have the lowest completeness so
the team knows where to focus data-capture improvements.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, List, Optional


class FieldCompleteness(BaseModel):
    """
    Per-field completeness statistics across all completed orders.

    completeness_pct is the percentage of completed orders (with time entries)
    where this field is non-null.  A value of 100.0 means every qualifying
    order has this field filled in.
    """
    field_name: str = Field(..., description="ORM column name")
    display_name: str = Field(..., description="Human-readable label for dashboard")
    total_orders: int = Field(..., ge=0, description="Total completed orders evaluated")
    filled_count: int = Field(..., ge=0, description="Orders where field is non-null")
    completeness_pct: float = Field(
        ..., ge=0.0, le=100.0,
        description="Percentage of completed orders with this field populated"
    )
    is_required_for_ml: bool = Field(
        ...,
        description="True if this field is a mandatory ML training feature"
    )

    model_config = ConfigDict(from_attributes=False)


class MLReadinessStatus(BaseModel):
    """
    High-level readiness verdict for ML model training.

    ready is True only when data_readiness_score reaches 80 and
    orders_with_all_features >= minimum_orders_for_training.

    The actionable_message provides a single plain-language next step.
    """
    ready: bool = Field(
        ...,
        description="True when there is sufficient clean data to start training"
    )
    data_readiness_score: float = Field(
        ..., ge=0.0, le=100.0,
        description="Composite score (0–100) combining quantity and completeness"
    )
    orders_with_all_features: int = Field(
        ..., ge=0,
        description="Completed orders that have every required ML feature filled"
    )
    minimum_orders_for_training: int = Field(
        100,
        ge=1,
        description="Minimum number of feature-complete orders required for training"
    )
    actionable_message: str = Field(
        ...,
        description="Single clear action to improve readiness — shown on dashboard"
    )

    model_config = ConfigDict(from_attributes=False)


class DataQualityReport(BaseModel):
    """
    Full data quality report returned by GET /ml/data-quality.

    Accessible by ADMIN and GOLDSMITH roles.  Designed for the analytics
    dashboard — every data point links to a concrete action.

    Operational interpretation:
    - data_readiness_score < 30 : Capture order_type and complexity on every
      new order intake form — this is the biggest gap.
    - 30–79 : Data exists but is incomplete; run a backfill sprint on older
      orders before training.
    - 80–100 and orders_with_all_features >= 100 : Ready to train.
    """
    # --- Volume metrics ---
    total_completed_orders: int = Field(
        ..., ge=0,
        description="Orders in COMPLETED or DELIVERED status"
    )
    orders_with_time_entries: int = Field(
        ..., ge=0,
        description="Completed orders that have at least one closed time entry"
    )
    orders_with_all_features: int = Field(
        ..., ge=0,
        description="Completed orders where all required ML fields are non-null"
    )

    # --- Time-entry metrics ---
    time_entries_count: int = Field(
        ..., ge=0,
        description="Total closed time entries across all completed orders"
    )
    avg_entries_per_order: float = Field(
        ..., ge=0.0,
        description="Average number of closed time entries per completed order"
    )
    entries_with_complexity_rating_pct: float = Field(
        ..., ge=0.0, le=100.0,
        description="Percentage of time entries that have complexity_rating set"
    )
    entries_with_quality_rating_pct: float = Field(
        ..., ge=0.0, le=100.0,
        description="Percentage of time entries that have quality_rating set"
    )
    entries_with_activity_pct: float = Field(
        ..., ge=0.0, le=100.0,
        description="Percentage of time entries linked to an Activity"
    )

    # --- Per-field completeness for order-level ML features ---
    field_completeness: List[FieldCompleteness] = Field(
        ...,
        description="Completeness stats per key ML feature column on Order"
    )

    # --- Readiness summary ---
    readiness: MLReadinessStatus = Field(
        ...,
        description="High-level training-readiness verdict and recommended action"
    )

    model_config = ConfigDict(from_attributes=False)
