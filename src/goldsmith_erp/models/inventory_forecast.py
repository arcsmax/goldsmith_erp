# src/goldsmith_erp/models/inventory_forecast.py
"""
Pydantic response schemas for the inventory forecasting endpoint.

Only weight/date/confidence fields are exposed — material cost figures
are intentionally excluded per CLAUDE.md financial data rules.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from goldsmith_erp.db.models import MetalType


class MetalForecastItem(BaseModel):
    """
    Depletion and reorder forecast for a single metal type.

    Color-coding hint for the UI:
      - weeks_until_depletion > 4  => green
      - 2 <= weeks_until_depletion <= 4  => amber
      - weeks_until_depletion < 2 or reorder_is_overdue  => red
    """

    metal_type: MetalType

    # Stock
    remaining_stock_g: float = Field(
        ..., description="Current remaining stock in grams"
    )

    # Consumption
    weekly_consumption_g: float = Field(
        ..., description="Average grams consumed per week over the last 90 days"
    )

    # Depletion prediction
    depletion_date: Optional[date] = Field(
        None,
        description="Predicted date stock hits zero. Null when consumption is zero.",
    )
    weeks_until_depletion: Optional[float] = Field(
        None, description="Weeks until stock is depleted from today."
    )

    # Reorder
    reorder_by: Optional[date] = Field(
        None, description="Recommended date to place a purchase order."
    )
    reorder_is_overdue: bool = Field(
        False, description="True when the reorder date is already in the past."
    )
    reorder_message: str = Field(
        ..., description="Human-readable reorder recommendation (German)."
    )

    # Data quality
    confidence: str = Field(
        ..., description="Forecast confidence: 'high', 'medium', or 'low'."
    )
    confidence_note: str = Field(
        ..., description="Explanation of the confidence rating."
    )

    model_config = {"from_attributes": True}


class InventoryForecastResponse(BaseModel):
    """Top-level response for GET /api/v1/metal-inventory/forecast."""

    forecasts: List[MetalForecastItem]
    generated_at: date = Field(
        ..., description="Date the forecast was computed (UTC date)."
    )
    lookback_days: int = Field(
        ..., description="Number of days of consumption history used."
    )
    lead_time_days: int = Field(
        ..., description="Supplier lead time in days used for reorder calculation."
    )

    model_config = {"from_attributes": True}
