"""Typed seed-data definitions for ``scripts/seed_demo.py``.

Provides frozen :func:`dataclasses.dataclass` shapes for the seed payloads so
that typos and schema drift surface at type-check time instead of at DB-write
time.  The ``*Seed.to_dict()`` convention returns a plain ``dict`` that
:func:`goldsmith_erp.db._seed_helpers.filter_model_fields` can then trim to
the columns the live model actually declares.

Why ``frozen=True``?  A seed script must not mutate the constants it works
from — accidental mutation during a deep ``dict()`` copy propagates back into
sibling entries and produces the kind of subtle "row N inherits row 0's last
value" bug that is near-impossible to bisect.  Forcing an explicit
``dataclasses.replace()`` clone for any tweak keeps the bug surface obvious.

Scope: this file targets the NEW V1.1 (Consultation + ConsultationPhoto) and
V1.2 (QuoteLineItemEdit, CustomerUpdate, CostChangeRequest) entity payloads
plus the four high-value existing types (User, Customer, Material,
OrderPhoto).  Wrapping the rest of the inline payloads would be a sprawling
mechanical port for marginal type-safety gain — left as a follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_dict_factory() -> dict[str, Any]:
    """Standard dict factory — ``field(default_factory=...)`` consumes this."""
    return {}


@dataclass(frozen=True)
class _SeedMixin:
    """Common ``to_dict()`` for every seed dataclass in this module."""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict view — pass through :func:`filter_model_fields`
        before handing to the ORM constructor."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Core entity seeds (subset — User, Customer, Material, OrderPhoto)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserSeed(_SeedMixin):
    """Staff user — admin / goldsmith / viewer."""

    email: str
    first_name: str
    last_name: str
    role: str  # 'admin' | 'goldsmith' | 'viewer'
    hashed_password: str
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class CustomerSeed(_SeedMixin):
    """Customer (encrypted-PII contact)."""

    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    mobile: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "Deutschland"
    customer_type: str = "private"
    source: Optional[str] = None
    notes: Optional[str] = None
    tags: tuple[str, ...] = ()
    ring_size: Optional[float] = None
    chain_length_cm: Optional[float] = None
    bracelet_length_cm: Optional[float] = None
    allergies: Optional[str] = None
    birthday: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)

    def with_field(self, **overrides: Any) -> "CustomerSeed":
        """Return a copy with one or more fields overridden — convenience for
        the seeder to project a common profile onto a one-off variation."""
        return replace(self, **overrides)


@dataclass(frozen=True)
class MaterialSeed(_SeedMixin):
    """Material in the inventory."""

    name: str
    description: str
    unit_price: float
    stock: float
    unit: str  # 'g' | 'Stueck' | 'pcs'
    supplier: Optional[str] = None
    webshop_url: Optional[str] = None
    image_url: Optional[str] = None
    min_stock: float = 0.0


@dataclass(frozen=True)
class OrderPhotoSeed(_SeedMixin):
    """OrderPhoto — uuid PK, links to order + time_entry.

    Used to demo the photo pipeline (V1.0) and to drive the V1.2
    customer-update "explicitly selected photos" feature.
    """

    order_id: int
    file_path: str
    taken_by: int
    notes: Optional[str] = None
    time_entry_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    id: Optional[str] = None  # filled by ``_seed_helpers.fresh_uuid()`` if None

    def with_uuid(self, fresh_id: str) -> "OrderPhotoSeed":
        return replace(self, id=fresh_id)


# ---------------------------------------------------------------------------
# V1.1 — Consultation + ConsultationPhoto
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsultationSeed(_SeedMixin):
    """V1.1 Beratungsgespräch — structured intake of a customer's wish.

    Wishes / notes / photos are design IP (GOLDSMITH+ADMIN only).
    Budget fields are financial data (ADMIN/GOLDSMITH only, audit-logged).
    """

    customer_id: int
    conducted_by: int
    occasion: str  # 'engagement' | 'wedding' | 'anniversary' | 'birthday' | 'self' | 'redesign' | 'repair_consult' | 'other'
    status: str = "draft"  # 'draft' | 'completed' | 'converted' | 'archived'
    piece_type: Optional[str] = None
    occasion_date: Optional[Any] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    wishes: Optional[str] = None
    materials_discussed: Optional[Any] = None  # JSON list
    source_material: Optional[str] = None
    notes: Optional[str] = None
    calendar_event_id: Optional[int] = None
    converted_quote_id: Optional[int] = None
    converted_order_id: Optional[int] = None
    follow_up_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class ConsultationPhotoSeed(_SeedMixin):
    """Sketch / reference / inspiration photo attached to a consultation.

    The point at which a sketch becomes the bench's working reference is
    ``ConsultationPhoto.order_id`` being set during consultation→order
    conversion — the photo is *linked*, never copied, so the bench file
    stays the canonical one.
    """

    consultation_id: int
    file_path: str
    taken_by: int
    kind: str = "sketch"  # 'sketch' | 'reference' | 'inspiration' | 'existing_piece'
    notes: Optional[str] = None
    order_id: Optional[int] = None  # set on conversion
    id: Optional[str] = None


# ---------------------------------------------------------------------------
# V1.2 — QuoteLineItemEdit, CustomerUpdate, CostChangeRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuoteLineItemEditSeed(_SeedMixin):
    """Audit log of an edit to a DRAFT-gated QuoteLineItem.

    Captures the BEFORE state, the AFTER state, who made the change, and a
    one-line summary rationale.  Used to drive the V1.2 quote-edit
    recalculation flow and to give the customer a traceable record of what
    they were quoted at each revision.
    """

    quote_line_item_id: int
    old_quantity: float
    new_quantity: float
    old_unit_price: float
    new_unit_price: float
    old_total: float
    new_total: float
    edited_by: int
    reason: Optional[str] = None
    edited_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class CustomerUpdateSeed(_SeedMixin):
    """V1.2 Kundeninfo — progress / cost-change / pickup update sent to a customer.

    Exactly one of ``order_id`` / ``repair_job_id`` must be set — the
    Pydantic layer enforces it.  ``photo_ids`` is an explicit-selection list
    (NEVER auto-includes) so the design-IP rule "nothing is shared by default"
    survives any naive frontend bug.
    """

    kind: str  # 'progress' | 'cost_change' | 'pickup_ready' | 'milestone'
    subject: str
    body: str
    sent_by: int
    order_id: Optional[int] = None
    repair_job_id: Optional[int] = None
    photo_ids: Optional[Any] = None  # list[str]
    cost_change_request_id: Optional[int] = None
    status: str = "draft"  # 'draft' | 'scheduled' | 'sent' | 'failed'
    delivery_method: Optional[str] = None  # 'email' | 'phone' | 'in_person'
    sent_at: Optional[datetime] = None
    token: Optional[str] = None  # portal-ready handle (uuid4 hex)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class CostChangeRequestSeed(_SeedMixin):
    """V1.2 §649 BGB cost-change request — change-order style approval record.

    Approval is evidence logging, not click-tracking — the customer replies
    to the email (or approves in person/by phone) and the goldsmith records
    the response via the service layer.  ``reason`` / ``response_evidence``
    are GDPR scrub targets.
    """

    order_id: int
    created_by: int
    original_amount: float
    new_amount: float
    reason: str
    line_items: Optional[Any] = (
        None  # JSON: [{"label": str, "amount": float, "kind": str}]
    )
    quote_id: Optional[int] = None
    delta_percent: Optional[float] = None  # service layer computes if None
    status: str = (
        "draft"  # 'draft' | 'sent' | 'approved' | 'declined' | 'expired' | 'superseded'
    )
    response_method: Optional[str] = None  # 'email' | 'phone' | 'in_person' | 'portal'
    response_evidence: Optional[str] = None
    responded_at: Optional[datetime] = None
    recorded_by: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


__all__ = [
    # core
    "UserSeed",
    "CustomerSeed",
    "MaterialSeed",
    "OrderPhotoSeed",
    # V1.1
    "ConsultationSeed",
    "ConsultationPhotoSeed",
    # V1.2
    "QuoteLineItemEditSeed",
    "CustomerUpdateSeed",
    "CostChangeRequestSeed",
    # mixin
    "_SeedMixin",
]
