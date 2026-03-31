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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import datetime
from typing import Optional, List

from goldsmith_erp.db.models import InvoiceStatus, InvoiceLineType


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
    quantity: float = Field(
        ..., gt=0, description="Quantity (Menge) - must be positive"
    )
    unit_price: float = Field(
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
    quantity: float
    unit_price: float
    total: float

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
    due_date: datetime = Field(
        ..., description="Payment due date (Faelligkeitsdatum)"
    )
    tax_rate: float = Field(
        default=19.0,
        ge=0,
        le=100,
        description="VAT rate in percent (MwSt-Satz, default 19%)",
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
    To mark as paid use the dedicated mark-paid endpoint.
    """

    status: Optional[InvoiceStatus] = Field(None, description="New invoice status")
    due_date: Optional[datetime] = Field(None, description="Updated due date")
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
    subtotal: float = Field(..., description="Zwischensumme (net)")
    tax_rate: float = Field(..., description="MwSt-Satz in Prozent")
    tax_amount: float = Field(..., description="MwSt-Betrag")
    total: float = Field(..., description="Gesamtbetrag (gross)")
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
    total: float
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

    paid_date: Optional[datetime] = Field(
        default=None,
        description="Actual payment date (defaults to now if omitted)",
    )
    payment_method: Optional[str] = Field(
        None, max_length=50, description="Payment method used"
    )
