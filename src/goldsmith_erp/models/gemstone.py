"""Pydantic schemas for order gemstones (W2-06, DOM-04).

A stone on an order: type, count, carat, colour, clarity, cut, shape, the
setting ("Fassungsart") and whether the customer brought it (Kundenstein).

``setting_type`` codes are the ones the ML encoder already one-hot encodes
(``ml/encoders.py::KNOWN_SETTING_TYPES``), so new intake data feeds the
duration model directly. German labels live in ``SETTING_TYPE_LABELS`` and
in the frontend (``components/orders/gemstones.ts``).

Data classes (CLAUDE.md): ``cost`` / ``total_cost`` are financial (purchase
price, FINANCIAL_VIEW); the stone specification of a custom piece is design
IP (DESIGN_VIEW). A VIEWER only sees type, count and the Kundenstein flag.
"""

from __future__ import annotations

from typing import Dict, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from goldsmith_erp.models._common import Money, Weight, number_default

GemstoneSettingType = Literal[
    "bezel", "prong", "channel", "pave", "tension", "invisible"
]

SETTING_TYPE_LABELS: Dict[str, str] = {
    "bezel": "Zargenfassung",
    "prong": "Krappenfassung",
    "channel": "Kanalfassung",
    "pave": "Pavé",
    "tension": "Spannfassung",
    "invisible": "Unsichtbare Fassung",
}

#: Fields removed from a read without FINANCIAL_VIEW.
GEMSTONE_FINANCIAL_FIELDS: Tuple[str, ...] = ("cost", "total_cost")
#: Fields removed from a read without DESIGN_VIEW.
GEMSTONE_DESIGN_FIELDS: Tuple[str, ...] = (
    "carat",
    "color",
    "quality",
    "cut",
    "shape",
    "setting_type",
    "certificate_number",
    "certificate_authority",
    "notes",
)

_CUSTOMER_STONE_COST_ERROR = (
    "Ein Kundenstein hat keinen Einkaufspreis. Bitte den Preis auf 0 setzen "
    "oder „Kundenstein“ abwählen."
)


class _GemstoneFields(BaseModel):
    """Shared, optional field definitions (create makes some required)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    carat: Optional[Weight] = Field(None, gt=0, le=1000, description="Karat je Stein")
    color: Optional[str] = Field(None, max_length=20, description="Farbe, z.B. G")
    quality: Optional[str] = Field(
        None, max_length=20, description="Reinheit, z.B. VS1"
    )
    cut: Optional[str] = Field(None, max_length=50, description="Schliff")
    shape: Optional[str] = Field(None, max_length=50, description="Form, z.B. rund")
    setting_type: Optional[GemstoneSettingType] = Field(None, description="Fassungsart")
    certificate_number: Optional[str] = Field(None, max_length=100)
    certificate_authority: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=1000)


class GemstoneCreate(_GemstoneFields):
    """Body for ``POST /orders/{order_id}/gemstones``."""

    type: str = Field(..., min_length=1, max_length=50, description="Steinart")
    quantity: int = Field(1, ge=1, le=10_000, description="Anzahl")
    is_customer_stone: bool = Field(False, description="Kundenstein")
    cost: Money = Field(
        number_default(0.0),
        ge=0,
        le=1_000_000,
        validate_default=True,
        description="Einkaufspreis je Stein (netto, EUR)",
    )

    @model_validator(mode="after")
    def customer_stone_has_no_cost(self) -> "GemstoneCreate":
        if self.is_customer_stone and self.cost > 0:
            raise ValueError(_CUSTOMER_STONE_COST_ERROR)
        return self


class GemstoneUpdate(_GemstoneFields):
    """Body for ``PATCH /gemstones/{gemstone_id}`` (only sent fields change)."""

    type: Optional[str] = Field(None, min_length=1, max_length=50)
    quantity: Optional[int] = Field(None, ge=1, le=10_000)
    is_customer_stone: Optional[bool] = None
    cost: Optional[Money] = Field(None, ge=0, le=1_000_000)


class GemstoneRead(BaseModel):
    """A stone as returned to the caller (role projection strips fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    type: str
    quantity: int = 1
    is_customer_stone: bool = False
    carat: Optional[Weight] = None
    color: Optional[str] = None
    quality: Optional[str] = None
    cut: Optional[str] = None
    shape: Optional[str] = None
    # Plain str on read: legacy rows may hold free text ("Prong").
    setting_type: Optional[str] = None
    certificate_number: Optional[str] = None
    certificate_authority: Optional[str] = None
    notes: Optional[str] = None
    cost: Optional[Money] = None
    total_cost: Optional[Money] = None

    @field_validator("quantity", mode="before")
    @classmethod
    def _legacy_quantity(cls, v: object) -> object:
        # Rows written before W2-06 may carry quantity NULL (= one stone).
        return 1 if v is None else v

    @field_validator("is_customer_stone", mode="before")
    @classmethod
    def _legacy_flag(cls, v: object) -> bool:
        return bool(v)


def describe_gemstone(stone: object) -> str:
    """One German line for a PDF ("2 × Diamant 0,10 ct G/VS1, rund, Krappenfassung, Kundenstein")."""
    quantity = getattr(stone, "quantity", None) or 1
    parts = [f"{quantity} × {getattr(stone, 'type', '') or 'Stein'}"]
    carat = getattr(stone, "carat", None)
    if carat:
        parts[0] += f" {carat:.2f} ct".replace(".", ",")
    grade = "/".join(
        str(v)
        for v in (getattr(stone, "color", None), getattr(stone, "quality", None))
        if v
    )
    if grade:
        parts[0] += f" {grade}"
    for attr in ("shape", "cut"):
        value = getattr(stone, attr, None)
        if value:
            parts.append(str(value))
    setting = getattr(stone, "setting_type", None)
    if setting:
        parts.append(SETTING_TYPE_LABELS.get(str(setting), str(setting)))
    if getattr(stone, "is_customer_stone", False):
        parts.append("Kundenstein")
    return ", ".join(parts)
