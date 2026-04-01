"""
Pydantic schemas for CustomMetalType and unified metal-type dropdown support.

Three schema families:
- CustomMetalTypeCreate / CustomMetalTypeUpdate / CustomMetalTypeRead
  CRUD schemas for the custom_metal_types table.
- MetalTypeOption
  Unified read-only schema used by the GET /metal-types list endpoint.
  Merges built-in MetalType enum values with active custom types.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


# ---------------------------------------------------------------------------
# CRUD schemas
# ---------------------------------------------------------------------------


class CustomMetalTypeCreate(BaseModel):
    """Payload for creating a new custom metal type."""

    code: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^[a-z0-9_]+$",
        description="Unique machine-readable code, e.g. 'rose_gold_9k'. "
                    "Lowercase letters, digits, and underscores only.",
    )
    display_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Human-readable label shown in UI, e.g. 'Roségold 375 (9K)'",
    )
    fine_content_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Precious-metal fine content ratio, 0.0–1.0 (e.g. 0.375 for 9K gold)",
    )
    base_metal: str = Field(
        ...,
        pattern=r"^(gold|silver|platinum|palladium)$",
        description="Base precious metal: 'gold', 'silver', 'platinum', or 'palladium'",
    )
    color: Optional[str] = Field(
        None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Optional hex colour for UI badge, e.g. '#D4A843'",
    )

    @field_validator("code")
    @classmethod
    def code_lowercase(cls, v: str) -> str:
        return v.lower()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "code": "rose_gold_9k",
                    "display_name": "Roségold 375 (9K)",
                    "fine_content_ratio": 0.375,
                    "base_metal": "gold",
                    "color": "#D4A843",
                }
            ]
        }
    }


class CustomMetalTypeUpdate(BaseModel):
    """Partial update payload — all fields optional."""

    display_name: Optional[str] = Field(None, min_length=2, max_length=100)
    fine_content_ratio: Optional[float] = Field(None, ge=0.0, le=1.0)
    base_metal: Optional[str] = Field(
        None, pattern=r"^(gold|silver|platinum|palladium)$"
    )
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_active: Optional[bool] = None


class CustomMetalTypeRead(BaseModel):
    """Full read schema for a custom metal type record."""

    id: int
    code: str
    display_name: str
    fine_content_ratio: float
    base_metal: str
    color: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Unified dropdown schema
# ---------------------------------------------------------------------------


class MetalTypeOption(BaseModel):
    """
    Unified representation of a metal type for UI dropdowns.

    Returned by GET /api/v1/metal-types.  Consumers must not assume
    that `id` is set — it is None for built-in types.
    """

    code: str = Field(..., description="Unique code (matches MetalType enum value for built-ins)")
    display_name: str
    fine_content_ratio: float
    base_metal: str
    color: Optional[str] = None
    is_builtin: bool = Field(
        ...,
        description="True for built-in MetalType enum values, False for custom DB rows",
    )
    id: Optional[int] = Field(
        None, description="Database ID — only set for custom types"
    )
