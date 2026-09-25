# src/goldsmith_erp/models/location.py
"""Schemas for the configurable workshop locations (Standorte)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

LOCATION_NAME_MAX = 50


class LocationKindEnum(str, Enum):
    """API mirror of ``db.models.LocationKind``."""

    BENCH = "bench"
    SAFE = "safe"
    SHOWROOM = "showroom"
    EXTERNAL = "external"
    OTHER = "other"


def _clean_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Der Name darf nicht leer sein.")
    return cleaned


class LocationCreate(BaseModel):
    """New Standort (ADMIN)."""

    name: str = Field(..., min_length=1, max_length=LOCATION_NAME_MAX)
    kind: LocationKindEnum = LocationKindEnum.OTHER
    sort_order: Optional[int] = Field(None, ge=0, le=100_000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return str(_clean_name(v))


class LocationUpdate(BaseModel):
    """Rename / re-kind / reorder / (re)activate a Standort (ADMIN)."""

    name: Optional[str] = Field(None, min_length=1, max_length=LOCATION_NAME_MAX)
    kind: Optional[LocationKindEnum] = None
    sort_order: Optional[int] = Field(None, ge=0, le=100_000)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        return _clean_name(v)


class LocationRead(BaseModel):
    """A Standort as returned by the API."""

    id: int
    name: str
    kind: LocationKindEnum
    is_active: bool
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
