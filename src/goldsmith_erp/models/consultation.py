"""Pydantic schemas for the V1.1 consultation module (Beratung & Annahme)."""

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from goldsmith_erp.db.models import (
    ConsultationOccasion,
    ConsultationPhotoKind,
    ConsultationStatus,
    NoGoCategory,
    OrderTypeEnum,
)


class ConsultationPhotoRead(BaseModel):
    id: str
    consultation_id: int
    order_id: Optional[int] = None
    kind: ConsultationPhotoKind
    notes: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class ConsultationBase(BaseModel):
    occasion: ConsultationOccasion = ConsultationOccasion.OTHER
    occasion_date: Optional[date] = None
    budget_min: Optional[float] = Field(None, ge=0)
    budget_max: Optional[float] = Field(None, ge=0)
    piece_type: Optional[OrderTypeEnum] = None
    wishes: Optional[str] = Field(None, max_length=5000)
    materials_discussed: Optional[List[Dict[str, Any]]] = None
    source_material: Optional[str] = Field(None, max_length=2000)
    notes: Optional[str] = Field(None, max_length=5000)
    follow_up_at: Optional[datetime] = None

    @model_validator(mode="after")
    def budget_range_ordered(self) -> "ConsultationBase":
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("budget_min darf nicht größer als budget_max sein")
        return self


class ConsultationCreate(ConsultationBase):
    customer_id: int = Field(..., gt=0)


class ConsultationUpdate(ConsultationBase):
    """PATCH-Autosave: alle Felder optional; nur gesetzte Felder werden übernommen."""

    occasion: Optional[ConsultationOccasion] = None
    status: Optional[ConsultationStatus] = None


class ConsultationRead(ConsultationBase):
    id: int
    customer_id: int
    conducted_by: int
    status: ConsultationStatus
    converted_quote_id: Optional[int] = None
    converted_order_id: Optional[int] = None
    photos: List[ConsultationPhotoRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConsultationListItem(BaseModel):
    id: int
    customer_id: int
    occasion: ConsultationOccasion
    piece_type: Optional[OrderTypeEnum] = None
    status: ConsultationStatus
    follow_up_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConsultationConvertRequest(BaseModel):
    target: Literal["quote", "order"]


class NoGoCreate(BaseModel):
    category: NoGoCategory
    value: str = Field(..., min_length=1, max_length=200)
    note: Optional[str] = Field(None, max_length=1000)

    @field_validator("value")
    @classmethod
    def strip_value(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("No-Go darf nicht leer sein")
        return v


class NoGoRead(BaseModel):
    id: int
    customer_id: int
    category: NoGoCategory
    value: str
    note: Optional[str] = None
    source_consultation_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NoGoConflict(BaseModel):
    no_go_id: int
    category: NoGoCategory
    value: str
    matched_against: str


class StyleProfileUpdate(BaseModel):
    metal_tones: Optional[List[str]] = None
    finishes: Optional[List[str]] = None
    stone_preferences: Optional[List[str]] = None
    style_words: Optional[List[str]] = None


class StyleProfileRead(BaseModel):
    metal_tones: List[str] = []
    finishes: List[str] = []
    stone_preferences: List[str] = []
    style_words: List[str] = []
