"""Pydantic schemas for Scrap Gold (Altgold) module."""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


# Alloy fine content ratios
ALLOY_RATIOS = {
    "999": 0.999,
    "900": 0.900,
    "750": 0.750,
    "585": 0.585,
    "375": 0.375,
    "333": 0.333,
    "ag999": 0.999,
    "ag925": 0.925,
    "ag800": 0.800,
    "pt950": 0.950,
}


class ScrapGoldItemCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=200)
    alloy: str = Field(..., description="Alloy type (e.g., 585, 750, 333)")
    weight_g: float = Field(..., gt=0, description="Total weight in grams")
    photo_path: Optional[str] = None


class ScrapGoldItemRead(BaseModel):
    id: int
    scrap_gold_id: int
    description: str
    alloy: str
    weight_g: float
    fine_content_g: float
    photo_path: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScrapGoldCreate(BaseModel):
    order_id: int
    customer_id: int
    gold_price_per_g: Optional[float] = Field(None, gt=0, description="Gold price per gram in EUR")
    price_source: str = Field("fixed_rate", description="daily_rate or fixed_rate")
    notes: Optional[str] = None


class ScrapGoldUpdate(BaseModel):
    gold_price_per_g: Optional[float] = Field(None, gt=0)
    price_source: Optional[str] = None
    notes: Optional[str] = None


class ScrapGoldRead(BaseModel):
    id: int
    order_id: int
    customer_id: int
    created_by: int
    status: str
    total_fine_gold_g: float
    total_value_eur: float
    gold_price_per_g: Optional[float] = None
    price_source: str
    signature_data: Optional[str] = None
    signed_at: Optional[datetime] = None
    receipt_pdf_path: Optional[str] = None
    notes: Optional[str] = None
    items: List[ScrapGoldItemRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScrapGoldSignRequest(BaseModel):
    signature_data: str = Field(..., min_length=10, description="Base64 encoded signature image")


class AlloyCalculation(BaseModel):
    """Response for alloy calculation."""
    alloy: str
    weight_g: float
    fine_content_g: float
    fine_content_percent: float
