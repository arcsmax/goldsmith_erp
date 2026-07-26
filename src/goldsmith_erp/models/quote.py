# src/goldsmith_erp/models/quote.py
"""
Pydantic schemas for the quote system (Kostenvoranschlag).

German quote terminology:
  Kostenvoranschlag  = Quote / Estimate
  KV-Nummer          = Quote number (format: KV-YYYY-NNNN)
  Angebotsposition   = Line item
  Gueltig bis        = Valid until
  Zwischensumme      = Subtotal (net amount before tax)
  MwSt               = Mehrwertsteuer (VAT)
  Gesamtbetrag       = Total amount (gross, including tax)
"""

from datetime import datetime, timedelta
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field, model_validator

from goldsmith_erp.db.models import QuoteStatus, QuoteLineType


# ============================================================================
# LINE ITEM SCHEMAS
# ============================================================================


class QuoteLineItemCreate(BaseModel):
    """Schema for creating a single quote line item (Angebotsposition)."""

    line_type: QuoteLineType = Field(
        ..., description="Type of line item (material, labor, gemstone, other)"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Description of the line item (Beschreibung)",
    )
    quantity: float = Field(
        ..., gt=0, description="Quantity (Menge) - must be positive"
    )
    unit_price: float = Field(
        ..., ge=0, description="Net unit price in EUR (Einzelpreis netto)"
    )
    estimator_metadata: dict | None = Field(
        default=None,
        description="Snapshot of estimator inputs/outputs. Set on create; immutable on update.",
    )

    @model_validator(mode="after")
    def validate_amounts(self) -> "QuoteLineItemCreate":
        if self.quantity <= 0:
            raise ValueError("quantity must be greater than 0")
        if self.unit_price < 0:
            raise ValueError("unit_price cannot be negative")
        return self


class QuoteLineItemResponse(BaseModel):
    """Schema for returning a single quote line item."""

    id: int
    quote_id: int
    line_type: QuoteLineType
    description: str
    quantity: float
    unit_price: float
    total: float
    estimator_metadata: dict | None = Field(
        default=None,
        description="Snapshot of estimator inputs/outputs. Set on create; immutable on update.",
    )

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# QUOTE SCHEMAS
# ============================================================================


class QuoteCreate(BaseModel):
    """
    Schema for creating a new quote (Kostenvoranschlag erstellen).

    Either order_id or customer_id must be provided. When order_id is
    supplied the service auto-generates line items from the order's cost data.
    caller may also supply additional line items.
    """

    order_id: Optional[int] = Field(
        default=None, gt=0, description="Order ID to generate quote from (optional)"
    )
    customer_id: int = Field(..., gt=0, description="Customer ID (Kunden-ID)")
    tax_rate: float = Field(
        default=19.0,
        ge=0,
        le=100,
        description="VAT rate in percent (MwSt-Satz, default 19%)",
    )
    valid_days: int = Field(
        default=14,
        ge=1,
        le=365,
        description="Number of days the quote is valid (Gueltigkeitsdauer in Tagen)",
    )
    notes: Optional[str] = Field(
        None, max_length=2000, description="Optional notes (Anmerkungen)"
    )
    additional_line_items: Optional[List[QuoteLineItemCreate]] = Field(
        default=None,
        description="Additional line items beyond those auto-generated from the order",
    )


class QuoteUpdate(BaseModel):
    """Schema for updating mutable quote fields."""

    status: Optional[QuoteStatus] = Field(None, description="New quote status")
    valid_until: Optional[datetime] = Field(None, description="Updated validity date")
    notes: Optional[str] = Field(None, max_length=2000, description="Updated notes")
    tax_rate: Optional[float] = Field(None, ge=0, le=100, description="Updated MwSt rate")


class ApproveQuoteRequest(BaseModel):
    """Request body for approving a quote with optional customer signature."""

    signature_data: Optional[str] = Field(
        default=None,
        description="Base64-encoded PNG of the customer's signature (optional)",
    )


class RejectQuoteRequest(BaseModel):
    """Request body for rejecting a quote."""

    reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional rejection reason (Ablehnungsgrund)",
    )


class QuoteResponse(BaseModel):
    """Full quote response schema including line items."""

    id: int
    quote_number: str = Field(..., description="KV-Nummer (KV-YYYY-NNNN)")
    order_id: Optional[int] = None
    customer_id: int
    created_by: int
    status: QuoteStatus
    valid_until: datetime
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    subtotal: float = Field(..., description="Zwischensumme (net)")
    tax_rate: float = Field(..., description="MwSt-Satz in Prozent")
    tax_amount: float = Field(..., description="MwSt-Betrag")
    total: float = Field(..., description="Gesamtbetrag (gross)")
    customer_signature_data: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    line_items: List[QuoteLineItemResponse] = []

    model_config = ConfigDict(from_attributes=True)


class QuoteListItem(BaseModel):
    """Lightweight quote representation for list views."""

    id: int
    quote_number: str
    order_id: Optional[int] = None
    customer_id: int
    status: QuoteStatus
    valid_until: datetime
    total: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuoteListResponse(BaseModel):
    """Paginated quote list response."""

    items: List[QuoteListItem]
    total: int
    skip: int
    limit: int
