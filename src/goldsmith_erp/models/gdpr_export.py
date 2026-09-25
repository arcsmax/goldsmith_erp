"""Art. 15 export: sections added by GDPR-05 (W5-08).

``CustomerGdprExportFull`` extends the original ``CustomerGdprExport``
(``models/customer.py``, unchanged) with every other customer-linked table.
Every model is ``extra="forbid"`` so a field that is not declared here can
never slip into a customer's export (same structural guarantee as the
design-IP models in ``models/customer.py``).

What is deliberately NOT declared (withheld, Art. 15 Abs. 4 DSGVO — rights
of others, trade secrets; decision D-13):

* the goldsmith's own design work: ``orders.description``,
  ``consultations.notes`` / ``materials_discussed``, consultation sketches,
  ``repair_jobs.diagnosis_notes``;
* employee identities (``created_by``, ``taken_by``, ``user_id``, IP
  addresses): third-party personal data;
* internal cost structure (material cost, hourly rate, margins);
* raw files, signature images and frozen PDFs: listed by metadata here, a
  copy is handed over on request (Art. 15 Abs. 3).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from goldsmith_erp.models.customer import CustomerGdprExport


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineItemExport(_Strict):
    description: str
    quantity: float
    unit_price: float
    total: float


class InvoiceExport(_Strict):
    id: int
    invoice_number: str
    order_id: Optional[int] = None
    status: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    paid_date: Optional[str] = None
    issued_at: Optional[str] = None
    subtotal: float
    tax_rate: float
    tax_amount: float
    total: float
    payment_method: Optional[str] = None
    line_items: List[LineItemExport] = Field(default_factory=list)


class QuoteExport(_Strict):
    id: int
    quote_number: str
    order_id: Optional[int] = None
    status: Optional[str] = None
    valid_until: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None
    converted_at: Optional[str] = None
    subtotal: float
    tax_rate: float
    tax_amount: float
    total: float
    customer_signature_present: bool
    created_at: Optional[str] = None
    line_items: List[LineItemExport] = Field(default_factory=list)


class ScrapGoldItemExport(_Strict):
    description: str
    alloy: Optional[str] = None
    weight_g: float
    fine_content_g: float
    photo_present: bool


class ScrapGoldExport(_Strict):
    id: int
    order_id: Optional[int] = None
    status: Optional[str] = None
    total_fine_gold_g: Optional[float] = None
    total_value_eur: Optional[float] = None
    gold_price_per_g: Optional[float] = None
    signed_at: Optional[str] = None
    signature_present: bool
    receipt_pdf_present: bool
    created_at: Optional[str] = None
    items: List[ScrapGoldItemExport] = Field(default_factory=list)


class ValuationExport(_Strict):
    id: int
    certificate_number: str
    order_id: Optional[int] = None
    item_description: str
    metal_type: Optional[str] = None
    metal_weight_g: Optional[float] = None
    metal_purity: Optional[str] = None
    gemstones_description: Optional[str] = None
    appraised_value: Optional[float] = None
    valuation_date: Optional[str] = None
    valid_until: Optional[str] = None
    pdf_present: bool


class RepairExport(_Strict):
    id: int
    repair_number: str
    bag_number: str
    item_description: str
    item_type: Optional[str] = None
    metal_type: Optional[str] = None
    estimated_value: Optional[float] = None
    status: Optional[str] = None
    estimated_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    estimated_completion_date: Optional[str] = None
    actual_completion_date: Optional[str] = None
    customer_notified_at: Optional[str] = None
    picked_up_at: Optional[str] = None
    created_at: Optional[str] = None


class CustomerUpdateExport(_Strict):
    id: int
    order_id: Optional[int] = None
    repair_job_id: Optional[int] = None
    kind: Optional[str] = None
    subject: str
    body: str
    status: Optional[str] = None
    delivery_method: Optional[str] = None
    photo_count: int
    sent_at: Optional[str] = None
    created_at: Optional[str] = None


class CostChangeExport(_Strict):
    id: int
    order_id: Optional[int] = None
    quote_id: Optional[int] = None
    original_amount: float
    new_amount: float
    delta_percent: float
    reason: str
    status: Optional[str] = None
    response_method: Optional[str] = None
    response_evidence: Optional[str] = None
    responded_at: Optional[str] = None
    created_at: Optional[str] = None


class PhotoExport(_Strict):
    id: str
    source: str  # order | repair
    order_id: Optional[int] = None
    repair_job_id: Optional[int] = None
    phase: Optional[str] = None
    taken_at: Optional[str] = None


class OrderEventExport(_Strict):
    order_id: int
    from_status: Optional[str] = None
    to_status: str
    created_at: Optional[str] = None


class ConsultationStatementExport(_Strict):
    """D-13: what the customer told us — disclosed, unlike the design work."""

    consultation_id: int
    wishes: Optional[str] = None
    source_material: Optional[str] = None


class GdprRequestExport(_Strict):
    request_type: str
    status: str
    requested_at: Optional[str] = None
    completed_at: Optional[str] = None


class AccessLogExport(_Strict):
    """C-579/21: when and what was done with the data; not by whom."""

    action: str
    entity: Optional[str] = None
    entity_id: Optional[int] = None
    timestamp: Optional[str] = None


class CustomerGdprExportFull(CustomerGdprExport):
    """Complete Art. 15 export (GDPR-05)."""

    invoices: List[InvoiceExport] = Field(default_factory=list)
    quotes: List[QuoteExport] = Field(default_factory=list)
    scrap_gold: List[ScrapGoldExport] = Field(default_factory=list)
    valuations: List[ValuationExport] = Field(default_factory=list)
    repairs: List[RepairExport] = Field(default_factory=list)
    customer_updates: List[CustomerUpdateExport] = Field(default_factory=list)
    cost_changes: List[CostChangeExport] = Field(default_factory=list)
    photos: List[PhotoExport] = Field(default_factory=list)
    order_events: List[OrderEventExport] = Field(default_factory=list)
    consultation_statements: List[ConsultationStatementExport] = Field(
        default_factory=list
    )
    gdpr_requests: List[GdprRequestExport] = Field(default_factory=list)
    access_log: List[AccessLogExport] = Field(default_factory=list)
    # Art. 15 Abs. 1 lit. a-h: purposes, recipients, storage, rights, source.
    meta: Dict[str, Any] = Field(default_factory=dict)
