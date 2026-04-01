# src/goldsmith_erp/models/metal_price.py
"""
Pydantic schemas for the metal price service.

All prices are expressed in EUR per gram, which is the standard unit
used in German goldsmith trade.
"""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

from goldsmith_erp.db.models import MetalPriceSource, MetalType


class MetalPriceResponse(BaseModel):
    """
    Current price for a single metal type.

    `price_per_gram` is the price for the specific alloy (e.g. 18K gold),
    not the fine-metal spot price.  Use `source` and `updated_at` to
    communicate data freshness to the frontend.
    """

    metal_type: MetalType
    price_per_gram: float = Field(
        ...,
        gt=0,
        description="Price in EUR per gram for this alloy",
        examples=[56.25],
    )
    currency: str = Field(default="EUR", description="ISO 4217 currency code")
    source: MetalPriceSource = Field(
        ...,
        description="Where this price came from (api/fallback/manual)",
    )
    updated_at: datetime = Field(
        ...,
        description="When this price was last refreshed",
    )

    model_config = {"from_attributes": True}


class MetalPriceListResponse(BaseModel):
    """Response wrapper for the full price list endpoint."""

    prices: List[MetalPriceResponse]
    count: int = Field(..., description="Number of metal types returned")

    model_config = {"from_attributes": True}


class MetalPriceHistoryPoint(BaseModel):
    """Single data point in the price history chart series."""

    fetched_at: datetime = Field(..., description="When this price was recorded")
    price_per_gram_eur: float = Field(..., description="Spot price in EUR/g at this timestamp")
    source: MetalPriceSource = Field(..., description="Data source for this point")

    model_config = {"from_attributes": True}


class MetalPriceHistoryResponse(BaseModel):
    """
    Price history for a single base metal over a requested time window.

    The `points` list is sorted ascending by `fetched_at` so it can be
    fed directly into a time-series chart without client-side sorting.
    """

    metal_type: MetalType
    days: int = Field(..., description="Number of days of history returned")
    points: List[MetalPriceHistoryPoint]
    avg_7d: float = Field(..., description="7-day simple moving average, EUR/g")
    avg_30d: float = Field(..., description="30-day simple moving average, EUR/g")
    current_price: float = Field(..., description="Most recent recorded price, EUR/g")

    model_config = {"from_attributes": True}
