# src/goldsmith_erp/models/invoice.py
"""
Pydantic schemas for the invoice/billing system (Rechnungswesen).

German invoice terminology:
  Rechnung           = Invoice
  Rechnungsnummer    = Invoice number (format: RE-YYYY-NNNN)
  Zwischensumme      = Subtotal (net amount before tax)
  MwSt               = Mehrwertsteuer (VAT)
  Gesamtbetrag       = Total amount (gross, including tax)
  Faelligkeitsdatum  = Due date
  Rechnungsposition  = Line item
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from goldsmith_erp.db.models import InvoiceLineType, InvoiceStatus
from goldsmith_erp.models._common import (
    Money,
    Percent,
    UtcNaiveDatetime,
    Weight,
    number_default,
)

# ============================================================================
# LINE ITEM SCHEMAS
# ============================================================================


class InvoiceLineItemCreate(BaseModel):
    """Schema for creating a single invoice line item (Rechnungsposition)."""

    line_type: InvoiceLineType = Field(
        ..., description="Type of line item (material, labor, gemstone, other)"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Description of the line item (Beschreibung)",
    )
    quantity: Weight = Field(
        ..., gt=0, description="Quantity (Menge) - must be positive"
    )
    unit_price: Money = Field(
        ..., ge=0, description="Net unit price in EUR (Einzelpreis netto)"
    )

    @model_validator(mode="after")
    def compute_total(self) -> "InvoiceLineItemCreate":
        """Ensure total can be derived from quantity * unit_price."""
        # Validation only — total is computed server-side in the service layer
        if self.quantity <= 0:
            raise ValueError("quantity must be greater than 0")
        if self.unit_price < 0:
            raise ValueError("unit_price cannot be negative")
        return self


class InvoiceLineItemResponse(BaseModel):
    """Schema for returning a single invoice line item."""

    id: int
    invoice_id: int
    line_type: InvoiceLineType
    description: str
    quantity: Weight
    unit_price: Money
    total: Money

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# INVOICE SCHEMAS
# ============================================================================


class InvoiceCreate(BaseModel):
    """
    Schema for creating an invoice from an order.

    The service will auto-populate line items from the order's material,
    labor, and gemstone data. Caller may also supply additional line items.
    """

    order_id: int = Field(..., gt=0, description="Order ID to generate invoice from")
    due_date: UtcNaiveDatetime = Field(
        ..., description="Payment due date (Faelligkeitsdatum); normalised to UTC"
    )
    tax_rate: Optional[Percent] = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "VAT rate in percent (MwSt-Satz). Omitted: the workshop default "
            "(Werkstatt-Stammdaten, 19 % unless changed). Always 0 for a "
            "Kleinunternehmer (§19 UStG)."
        ),
    )
    service_date: Optional[UtcNaiveDatetime] = Field(
        default=None,
        description=(
            "Leistungsdatum (§14 Abs. 4 Nr. 6 UStG). Omitted: the order's "
            "completion date, else the invoice date."
        ),
    )
    notes: Optional[str] = Field(
        None, max_length=2000, description="Optional notes on the invoice (Anmerkungen)"
    )
    payment_method: Optional[str] = Field(
        None,
        max_length=50,
        description="Payment method (Zahlungsart): Ueberweisung, Bar, Karte",
    )
    # Optional additional line items supplied by the caller (appended to auto-generated ones)
    additional_line_items: Optional[List[InvoiceLineItemCreate]] = Field(
        default=None,
        description="Additional line items beyond those auto-generated from the order",
    )

    @field_validator("due_date")
    @classmethod
    def due_date_must_be_future(cls, v: datetime) -> datetime:
        if v <= datetime.utcnow():
            raise ValueError("due_date must be in the future")
        return v


class InvoiceUpdate(BaseModel):
    """
    Schema for updating an existing invoice.

    Only editable fields — invoice_number, order_id and customer_id are immutable.
    ``status`` is deliberately NOT editable here (BE-05): transitions go through
    the dedicated endpoints (send, mark-paid, cancel), which carry their own
    permission checks. Unknown fields are rejected so a stray ``status`` fails
    loudly instead of being ignored.
    """

    model_config = ConfigDict(extra="forbid")

    due_date: Optional[UtcNaiveDatetime] = Field(None, description="Updated due date")
    notes: Optional[str] = Field(None, max_length=2000, description="Updated notes")
    payment_method: Optional[str] = Field(
        None, max_length=50, description="Payment method"
    )


class InvoiceResponse(BaseModel):
    """Full invoice response schema including line items."""

    id: int
    invoice_number: str = Field(..., description="Rechnungsnummer (RE-YYYY-NNNN)")
    order_id: int
    customer_id: int
    created_by: int
    status: InvoiceStatus
    issue_date: datetime
    due_date: datetime
    paid_date: Optional[datetime] = None
    service_date: Optional[datetime] = Field(
        default=None, description="Leistungsdatum (§14 Abs. 4 Nr. 6 UStG)"
    )
    cancels_invoice_id: Optional[int] = Field(
        default=None,
        description="Set on a Stornorechnung: the invoice it cancels (W2-04)",
    )
    cancelled_by_invoice_id: Optional[int] = Field(
        default=None,
        description="Set on a cancelled invoice: its Stornorechnung (W2-04)",
    )
    subtotal: Money = Field(..., description="Zwischensumme (net)")
    tax_rate: Percent = Field(..., description="MwSt-Satz in Prozent")
    tax_amount: Money = Field(..., description="MwSt-Betrag")
    total: Money = Field(..., description="Gesamtbetrag (gross)")
    scrap_gold_credit: Money = Field(
        default=number_default(0.0),
        description="Altgold-Gutschrift, deducted after VAT (not part of the VAT base)",
    )
    amount_due: Optional[Money] = Field(
        default=None, description="Zahlbetrag = total - scrap_gold_credit"
    )
    notes: Optional[str] = None
    payment_method: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    line_items: List[InvoiceLineItemResponse] = []

    model_config = ConfigDict(from_attributes=True)


class InvoiceListItem(BaseModel):
    """Lightweight invoice representation for list views."""

    id: int
    invoice_number: str
    order_id: int
    customer_id: int
    status: InvoiceStatus
    issue_date: datetime
    due_date: datetime
    paid_date: Optional[datetime] = None
    cancels_invoice_id: Optional[int] = None
    total: Money
    scrap_gold_credit: Money = number_default(0.0)
    amount_due: Optional[Money] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceListResponse(BaseModel):
    """Paginated invoice list response."""

    items: List[InvoiceListItem]
    total: int
    skip: int
    limit: int


class MarkPaidRequest(BaseModel):
    """Request body for marking an invoice as paid (bezahlt)."""

    paid_date: Optional[UtcNaiveDatetime] = Field(
        default=None,
        description="Actual payment date (defaults to now if omitted)",
    )
    payment_method: Optional[str] = Field(
        None, max_length=50, description="Payment method used"
    )


class StornoRequest(BaseModel):
    """Request body for POST /invoices/{id}/storno (W2-04, DOM-24b)."""

    model_config = ConfigDict(extra="forbid")

    reason: Optional[str] = Field(
        None, max_length=500, description="Grund der Stornierung (Stornogrund)"
    )
