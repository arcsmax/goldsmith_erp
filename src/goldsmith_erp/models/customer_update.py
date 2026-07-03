# src/goldsmith_erp/models/customer_update.py
"""
Pydantic schemas for the V1.2 Customer Updates & §649 BGB Cost Approval
module (Kundeninfo & Kostenfreigabe).

Precedent: models/repair.py (Create/Read split, ConfigDict(from_attributes=True),
field_validator/model_validator, German error messages) and models/consultation.py.

These names are a contract — Task 5 (services/routers) imports them verbatim.
Financial fields (amounts, deltas) are visible only to GOLDSMITH/ADMIN roles;
that gate is enforced at the router level (Task 5), not here.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from goldsmith_erp.db.models import (
    CostChangeResponseMethod,
    CostChangeStatus,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    UpdateDeliveryMethod,
)

# Minimum non-whitespace length for legally/evidentially relevant free text.
_REASON_MIN_LENGTH = 10
_RESPONSE_EVIDENCE_MIN_LENGTH = 5


def _strip_or_raise(value: str, field_label: str, min_length: int) -> str:
    """
    Strip whitespace and enforce a minimum length on the stripped result.

    Length constraints are enforced here (post-strip) rather than via
    ``Field(min_length=...)`` because a ``Field`` constraint runs against
    the raw input — a string padded with whitespace to clear the raw
    threshold but too short once stripped (e.g. ``"   ok grund   "``)
    would otherwise slip through. Failing loudly on blank/near-blank
    input matches CLAUDE.md ("Fail loudly — never swallow exceptions
    silently") rather than silently accepting throwaway text for a
    field that is later relied on as evidence.
    """
    stripped = value.strip()
    if len(stripped) < min_length:
        raise ValueError(
            f"{field_label} muss mindestens {min_length} Zeichen enthalten"
        )
    return stripped


# ============================================================================
# CUSTOMER UPDATE SCHEMAS
# ============================================================================


class CustomerUpdateCreate(BaseModel):
    """
    Schema for creating a CustomerUpdate draft.

    Does NOT carry ``order_id`` / ``repair_job_id``: those come from the
    URL path in Task 5's router (``POST /orders/{id}/updates`` /
    ``POST /repairs/{id}/updates`` or equivalent), not the request body —
    so there is deliberately NO "exactly one target" validator on this
    schema. That invariant lives on the ``CustomerUpdate`` ORM model
    (enforced at the Pydantic layer that DOES see both FKs: the service
    layer constructs the ORM row from the path-supplied target plus this
    body). ``subject`` / ``body`` are optional — when omitted, the service
    fills them from the matching German template for ``kind``.
    """

    kind: CustomerUpdateKind
    subject: Optional[str] = Field(None, max_length=300)
    body: Optional[str] = Field(None, max_length=20_000)
    photo_ids: Optional[List[str]] = Field(
        None,
        max_length=20,
        description="Explizit ausgewaehlte OrderPhoto-UUIDs — nie automatisch geteilt",
    )

    @field_validator("subject", "body")
    @classmethod
    def _reject_blank_if_provided(cls, v: Optional[str]) -> Optional[str]:
        """A provided-but-blank override is ambiguous with 'omitted' (which
        triggers template prefill) — reject rather than silently treating
        whitespace as an intentional empty override."""
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Feld darf nicht nur aus Leerzeichen bestehen")
        return stripped

    @field_validator("subject")
    @classmethod
    def _reject_crlf_in_subject(cls, v: Optional[str]) -> Optional[str]:
        """
        Review fix: ``subject`` becomes an email ``Subject:`` header
        (EmailService.send_email / send_customer_update / send_cost_change)
        and is also embedded verbatim into the customer-update PDF's
        ``/Info`` metadata. A raw CR/LF in staff-authored free text
        (kind=custom) is never legitimate here — reject it at the input
        boundary instead of relying on downstream libraries (Python's
        ``email`` module folds/escapes header values safely today, but
        that is an implementation detail of a dependency, not a contract
        this schema should lean on).
        """
        if v is None:
            return v
        if "\r" in v or "\n" in v:
            raise ValueError("Betreff darf keine Zeilenumbrueche enthalten")
        return v


class CustomerUpdateRead(BaseModel):
    """
    Full CustomerUpdate detail — GET /orders/{id}/updates history and the
    send-result payload. Carries both possible attachment targets (exactly
    one of ``order_id`` / ``repair_job_id`` is set per the ORM invariant)
    plus the optional linked CostChangeRequest.
    """

    id: int
    order_id: Optional[int] = None
    repair_job_id: Optional[int] = None
    kind: CustomerUpdateKind
    subject: str
    body: str
    photo_ids: List[str] = Field(default_factory=list)
    cost_change_request_id: Optional[int] = None
    token: str
    status: CustomerUpdateStatus
    sent_at: Optional[datetime] = None
    sent_by: int
    delivery_method: Optional[UpdateDeliveryMethod] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("photo_ids", mode="before")
    @classmethod
    def _default_empty_photo_ids(cls, v: Optional[List[str]]) -> List[str]:
        """The ORM column is nullable JSON — normalise NULL to [] so callers
        never have to None-check a list field."""
        return v if v is not None else []


class MarkDeliveredRequest(BaseModel):
    """
    Schema for ``POST /updates/{id}/mark-delivered``.

    Added in Task 5 (not part of the original Task 2 contract): the plan's
    binding semantics require an EXPLICIT confirmation step for the
    PDF-manual delivery path — ``GET /updates/{id}/pdf`` must stay a pure
    read (downloading a PDF must not itself mark the update delivered).
    Restricted to ``pdf_manual`` — the ``email`` delivery method is only
    ever set by ``CustomerUpdateService.send``'s own successful-send path,
    never by this manual confirmation endpoint.
    """

    method: Literal["pdf_manual"] = "pdf_manual"


class CustomerUpdateSendResult(BaseModel):
    """
    Result of POST /updates/{id}/send.

    Always 200, even on delivery failure or when SMTP is unset — the draft
    persists either way (CLAUDE.md: fail loudly, but a failed send is a
    recorded outcome, not a 5xx). ``method`` is None when SMTP is unset
    (send skipped) or when delivery genuinely failed before a method could
    be attributed.
    """

    update: CustomerUpdateRead
    delivered: bool
    method: Optional[UpdateDeliveryMethod] = None


# ============================================================================
# COST CHANGE REQUEST SCHEMAS
# ============================================================================


class CostChangeLineItem(BaseModel):
    """One itemized line of a CostChangeRequest.line_items JSON list."""

    label: str = Field(..., min_length=1, max_length=200)
    amount: float
    kind: Literal["add", "remove", "change"]

    model_config = ConfigDict(from_attributes=True)


class CostChangeCreate(BaseModel):
    """
    Schema for creating a CostChangeRequest.

    Does NOT carry ``order_id``: path-supplied in Task 5's router
    (``POST /orders/{id}/cost-changes``). ``original_amount`` is likewise
    absent here — the service derives it from the order's referenceable
    Quote (Task 3's CostWatchService quote-selection rule), not from client
    input, so a customer-facing "prior amount" can't be spoofed by the
    request body.
    """

    new_amount: float = Field(..., gt=0)
    reason: str = Field(
        ..., max_length=2000, description="Begruendung fuer die Kostenaenderung"
    )
    line_items: Optional[List[CostChangeLineItem]] = Field(
        None,
        max_length=30,
        description="Einzelposten der Kostenaenderung — begrenzt auf 30 Zeilen",
    )

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        return _strip_or_raise(v, "Begründung", _REASON_MIN_LENGTH)


class CostChangeRead(BaseModel):
    """Full CostChangeRequest detail — financial data, ADMIN/GOLDSMITH only
    (enforced at the router level, Task 5)."""

    id: int
    order_id: int
    quote_id: Optional[int] = None
    original_amount: float
    new_amount: float
    delta_percent: float
    reason: str
    line_items: List[CostChangeLineItem] = Field(default_factory=list)
    status: CostChangeStatus
    response_method: Optional[CostChangeResponseMethod] = None
    response_evidence: Optional[str] = None
    responded_at: Optional[datetime] = None
    recorded_by: Optional[int] = None
    created_at: datetime
    created_by: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("line_items", mode="before")
    @classmethod
    def _default_empty_line_items(
        cls, v: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        return v if v is not None else []


class CostChangeRecordResponse(BaseModel):
    """
    Schema for POST /cost-changes/{id}/record-response.

    This is evidence logging, not click-tracking (spec §Domain model /
    CostChangeRequest): the goldsmith records how the customer actually
    responded. Only valid from CostChangeStatus.SENT (enforced in the
    service, Task 5).
    """

    status: Literal["approved", "declined"]
    response_method: CostChangeResponseMethod
    response_evidence: str = Field(
        ...,
        max_length=2000,
        description="Nachweistext — z.B. zitierte Email-Antwort oder Gespraechsnotiz",
    )

    @field_validator("response_evidence")
    @classmethod
    def _validate_response_evidence(cls, v: str) -> str:
        return _strip_or_raise(v, "Nachweistext", _RESPONSE_EVIDENCE_MIN_LENGTH)


# ============================================================================
# PROJECTED COST SCHEMA (CostWatchService, Task 3)
# ============================================================================


class ProjectedCost(BaseModel):
    """
    Projected cost breakdown for an order — returned by
    ``CostWatchService.get_projected_cost`` and
    ``GET /orders/{id}/projected-cost``.

    ``quote_id`` / ``quote_total`` / ``delta_percent`` / ``delta_abs`` are
    None when the order has no referenceable Quote to compare against (see
    Task 3's quote-selection rule: latest SENT/APPROVED, fallback latest
    DRAFT). Deltas are signed (can be negative when actuals run under the
    quote) so they are intentionally not constrained to ``ge=0``.

    NETTO/BRUTTO — all amounts here are NET (netto): the cost rollup
    (material/gemstone/labor) carries no VAT, so ``quote_total`` is
    populated with ``Quote.subtotal`` (the net quote amount), NOT
    ``Quote.total`` (gross incl. VAT). ``delta_abs`` is therefore in NET
    euros and ``settings.COST_ALERT_THRESHOLD_ABS_EUR`` is interpreted as
    a net amount; ``delta_percent`` is scale-invariant, so net-vs-net
    yields the legally correct §649 overrun percentage. Comparing net
    costs against the gross total would understate overruns by the VAT
    factor (~19%), firing the 15% threshold only at ~37% real overrun.
    """

    material_cost: float = Field(..., ge=0)
    gemstone_cost: float = Field(..., ge=0)
    labor_minutes_billable: float = Field(..., ge=0)
    labor_cost: float = Field(..., ge=0)
    projected_total: float = Field(..., ge=0)
    quote_id: Optional[int] = None
    quote_total: Optional[float] = Field(None, ge=0)
    delta_percent: Optional[float] = None
    delta_abs: Optional[float] = None
    over_threshold: bool

    model_config = ConfigDict(from_attributes=True)
