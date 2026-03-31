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
