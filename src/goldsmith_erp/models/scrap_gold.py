"""Pydantic schemas for Scrap Gold (Altgold) module.

DOM-19 / DOM-20 fix: the alloy contract is now the shared, database-backed
``AlloyType`` enum (``goldsmith_erp.db.models.AlloyType``) instead of a bare
``str`` field. This means:

- The frontend must send one of the canonical alloy codes ("999", "900",
  "750", "585", "375", "333", "ag999", "ag925", "ag800", "pt950"); anything
  else (a number, "925" instead of "ag925", an unsupported alloy) is
  rejected by Pydantic with a 422 instead of silently costing the shop
  money via ``ALLOY_RATIOS.get(alloy, 0.0)``.
- Fine-content ratios and the alloy's base metal (for spot-price lookup)
  are derived from that same enum, so gold/silver/platinum items can never
  drift out of sync with each other.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import AlloyType, MetalType
from goldsmith_erp.models._common import Money, Weight

# ---------------------------------------------------------------------------
# Alloy contract: fineness (Feingehalt) and base metal, keyed by the shared
# AlloyType enum. These are the single source of truth for valuation.
# ---------------------------------------------------------------------------

#: Exact fine-content ratio per alloy, as Decimal to avoid float rounding
#: error when valuing scrap gold (CLAUDE.md: Decimal for money).
ALLOY_FINENESS: Dict[AlloyType, Decimal] = {
    AlloyType.GOLD_999: Decimal("0.999"),
    AlloyType.GOLD_900: Decimal("0.900"),
    AlloyType.GOLD_750: Decimal("0.750"),
    AlloyType.GOLD_585: Decimal("0.585"),
    AlloyType.GOLD_375: Decimal("0.375"),
    AlloyType.GOLD_333: Decimal("0.333"),
    AlloyType.SILVER_999: Decimal("0.999"),
    AlloyType.SILVER_925: Decimal("0.925"),
    AlloyType.SILVER_800: Decimal("0.800"),
    AlloyType.PLATINUM_950: Decimal("0.950"),
}

#: The pure/base metal each alloy is priced against (a MetalPriceService
#: spot-price key). An item's EUR value is its fine content (already net of
#: alloy dilution) times the spot price of this PURE metal — never a
#: different metal's price (DOM-20).
ALLOY_BASE_METAL: Dict[AlloyType, MetalType] = {
    AlloyType.GOLD_999: MetalType.GOLD_24K,
    AlloyType.GOLD_900: MetalType.GOLD_24K,
    AlloyType.GOLD_750: MetalType.GOLD_24K,
    AlloyType.GOLD_585: MetalType.GOLD_24K,
    AlloyType.GOLD_375: MetalType.GOLD_24K,
    AlloyType.GOLD_333: MetalType.GOLD_24K,
    AlloyType.SILVER_999: MetalType.SILVER_999,
    AlloyType.SILVER_925: MetalType.SILVER_999,
    AlloyType.SILVER_800: MetalType.SILVER_999,
    AlloyType.PLATINUM_950: MetalType.PLATINUM_950,
}

#: Human-facing metal family, e.g. for grouping on the receipt PDF.
ALLOY_METAL_LABEL: Dict[AlloyType, str] = {
    AlloyType.GOLD_999: "gold",
    AlloyType.GOLD_900: "gold",
    AlloyType.GOLD_750: "gold",
    AlloyType.GOLD_585: "gold",
    AlloyType.GOLD_375: "gold",
    AlloyType.GOLD_333: "gold",
    AlloyType.SILVER_999: "silver",
    AlloyType.SILVER_925: "silver",
    AlloyType.SILVER_800: "silver",
    AlloyType.PLATINUM_950: "platinum",
}

#: Backward-compatible string-keyed view (alloy code -> float ratio) for the
#: free-text ``/scrap-gold/alloy-calculator`` query-param endpoint, which
#: predates the enum contract and is not user-input-hardened the same way
#: (it 400s on an unknown key rather than relying on Pydantic).
ALLOY_RATIOS: Dict[str, float] = {
    alloy.value: float(ratio) for alloy, ratio in ALLOY_FINENESS.items()
}


class ScrapGoldItemCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=200)
    alloy: AlloyType = Field(
        ..., description="Alloy/fineness code, e.g. 585, 750, ag925, pt950"
    )
    weight_g: Weight = Field(..., gt=0, description="Total weight in grams")
    photo_path: Optional[str] = None


class ScrapGoldItemRead(BaseModel):
    id: int
    scrap_gold_id: int
    description: str
    alloy: str
    weight_g: Weight
    fine_content_g: Weight
    photo_path: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScrapGoldCreate(BaseModel):
    order_id: int
    customer_id: int
    gold_price_per_g: Optional[Money] = Field(
        None,
        gt=0,
        description=(
            "Manual override for the GOLD spot price per gram in EUR. "
            "Silver and platinum items always use the live "
            "MetalPriceService spot price — there is no equivalent "
            "override column for them."
        ),
    )
    price_source: str = Field("fixed_rate", description="daily_rate or fixed_rate")
    notes: Optional[str] = None


class ScrapGoldUpdate(BaseModel):
    gold_price_per_g: Optional[Money] = Field(None, gt=0)
    price_source: Optional[str] = None
    notes: Optional[str] = None


#: W2-16 / DOM-21: accepted identity documents for the Ankaufsbuch.
IdDocumentType = Literal[
    "personalausweis", "reisepass", "aufenthaltstitel", "sonstiges"
]

ID_DOCUMENT_LABELS: Dict[str, str] = {
    "personalausweis": "Personalausweis",
    "reisepass": "Reisepass",
    "aufenthaltstitel": "Aufenthaltstitel",
    "sonstiges": "Sonstiges Ausweisdokument",
}


def id_required_for(total_value_eur: Optional[Union[Decimal, float]]) -> bool:
    """True when a purchase of this value needs ID data before signing (D-16)."""
    return float(total_value_eur or 0.0) > float(settings.SCRAP_GOLD_ID_THRESHOLD_EUR)


class ScrapGoldIdentification(BaseModel):
    """Body for ``PUT /scrap-gold/{id}/identification`` (W2-16).

    Document number and issuing authority are PII: stored encrypted, never
    logged, shown in reads only as the last four characters.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id_document_type: IdDocumentType
    id_document_number: str = Field(..., min_length=4, max_length=40)
    id_issuing_authority: str = Field(..., min_length=2, max_length=200)

    @field_validator("id_document_number")
    @classmethod
    def _no_inner_whitespace(cls, v: str) -> str:
        return "".join(v.split()).upper()


class AnkaufsbuchQuery(BaseModel):
    """Period of an Ankaufsbuch export (both days inclusive)."""

    date_from: date
    date_to: date
    format: Literal["csv", "pdf"] = "csv"

    @model_validator(mode="after")
    def _ordered(self) -> "AnkaufsbuchQuery":
        if self.date_from > self.date_to:
            raise ValueError("Das Startdatum muss vor dem Enddatum liegen.")
        return self


class ScrapGoldRead(BaseModel):
    id: int
    order_id: int
    customer_id: int
    created_by: int
    status: str
    total_fine_gold_g: Weight
    total_value_eur: Money
    gold_price_per_g: Optional[Money] = None
    price_source: str
    signature_data: Optional[str] = None
    signed_at: Optional[datetime] = None
    receipt_pdf_path: Optional[str] = None
    notes: Optional[str] = None
    items: List[ScrapGoldItemRead] = []
    created_at: datetime
    updated_at: datetime
    # W2-16: identification, number masked to its last four characters.
    id_document_type: Optional[str] = None
    id_document_number_last4: Optional[str] = Field(
        None, validation_alias="id_document_number"
    )
    id_issuing_authority: Optional[str] = None
    id_checked_by: Optional[int] = None
    id_checked_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "populate_by_name": True}

    @field_validator("id_document_number_last4", mode="after")
    @classmethod
    def _mask(cls, v: Optional[str]) -> Optional[str]:
        return v[-4:] if v else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_identification(self) -> bool:
        return bool(self.id_document_type and self.id_document_number_last4)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id_required(self) -> bool:
        return id_required_for(self.total_value_eur)


class ScrapGoldSignRequest(BaseModel):
    signature_data: str = Field(
        ..., min_length=10, description="Base64 encoded signature image"
    )


class AlloyCalculation(BaseModel):
    """Response for alloy calculation."""

    alloy: str
    weight_g: Weight
    fine_content_g: Weight
    fine_content_percent: float
