# src/goldsmith_erp/models/order.py
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from goldsmith_erp.db.models import (
    CostingMethod,
    FinishTypeEnum,
    MetalType,
    OrderStatusEnum,
    OrderTypeEnum,
)
from goldsmith_erp.models._common import Money, Percent, Weight, number_default
from goldsmith_erp.models.scan_history import LastScanRead

# Deliberate models -> services import: the allowed Feingehalt vocabulary
# (W2-09; DOM-22, DOM-23, D-10) must never drift from the one
# order_workflow.py uses for the completion guard, so both read the same
# table in services/hallmark_vocabulary.py instead of each keeping their
# own allow-list.
from goldsmith_erp.services.hallmark_vocabulary import is_valid_mark

# Use TYPE_CHECKING to avoid circular import issues
if TYPE_CHECKING:
    from goldsmith_erp.models.customer import CustomerRead


class MaterialBase(BaseModel):
    """Material schema for order display."""

    id: int = Field(..., gt=0, description="Material ID (must be positive)")
    name: str = Field(..., min_length=1, max_length=200, description="Material name")
    unit_price: Money = Field(
        ..., ge=0, description="Unit price (must be non-negative)"
    )

    model_config = ConfigDict(from_attributes=True)


class OrderBase(BaseModel):
    """Basis-Schema für Orders mit Input Validation."""

    title: str = Field(
        ..., min_length=1, max_length=200, description="Order title (1-200 characters)"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Order description (1-2000 characters)",
    )
    price: Optional[Money] = Field(
        None, ge=0, description="Agreed order price, NET excl. VAT (ADR-2026-09-25)"
    )

    @field_validator("title", "description")
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        """Sanitize text fields to prevent injection attacks."""
        # Strip leading/trailing whitespace
        v = v.strip()
        # Ensure not empty after stripping
        if not v:
            raise ValueError("Field cannot be empty or only whitespace")
        # Prevent SQL injection by blocking dangerous SQL keywords
        dangerous_patterns = [
            "DROP TABLE",
            "DELETE FROM",
            "INSERT INTO",
            "UPDATE ",
            "TRUNCATE",
            "ALTER TABLE",
            "CREATE TABLE",
            "--",
            ";--",
        ]
        v_upper = v.upper()
        for pattern in dangerous_patterns:
            if pattern in v_upper:
                raise ValueError(
                    f"Text contains potentially dangerous SQL keyword: {pattern}"
                )
        return v

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate price is reasonable."""
        if v is not None:
            if v < 0:
                raise ValueError("Price cannot be negative")
            if v > 1_000_000:  # 1 million max
                raise ValueError("Price exceeds maximum allowed value (1,000,000)")
        return v


class OrderCreate(OrderBase):
    """Schema für Order-Erstellung mit Validation."""

    customer_id: int = Field(..., gt=0, description="Customer ID (must be positive)")
    deadline: Optional[datetime] = Field(
        None, description="Order deadline for calendar"
    )
    materials: Optional[List[int]] = Field(
        None,
        description="List of material IDs",
        max_length=100,  # Prevent abuse with huge lists
    )

    # Weight & Material (optional at creation)
    estimated_weight_g: Optional[Weight] = Field(
        None, ge=0, description="Estimated metal weight in grams"
    )
    scrap_percentage: Optional[Percent] = Field(
        5.0, ge=0, le=50, validate_default=True, description="Material loss percentage"
    )

    # Metal Inventory Integration (optional at creation)
    metal_type: Optional[MetalType] = Field(
        None, description="Type of metal to use (e.g., gold_18k, silver_925)"
    )
    costing_method: Optional[CostingMethod] = Field(
        CostingMethod.FIFO, description="Costing method (FIFO/LIFO/AVERAGE/SPECIFIC)"
    )
    specific_metal_purchase_id: Optional[int] = Field(
        None,
        gt=0,
        description="Specific metal batch ID (required if costing_method=SPECIFIC)",
    )

    # Cost Calculation (optional at creation)
    material_cost_override: Optional[Money] = Field(
        None, ge=0, description="Manual material cost override"
    )
    labor_hours: Optional[float] = Field(None, ge=0, description="Estimated work hours")
    hourly_rate: Optional[Money] = Field(
        75.00, ge=0, validate_default=True, description="Labor rate per hour"
    )

    # Pricing (optional at creation)
    profit_margin_percent: Optional[Percent] = Field(
        40.0,
        ge=0,
        le=100,
        validate_default=True,
        description="Profit margin percentage",
    )
    vat_rate: Optional[Percent] = Field(
        19.0, ge=0, le=100, validate_default=True, description="VAT rate percentage"
    )

    # ML feature fields (optional at creation — can be filled during intake)
    order_type: Optional[OrderTypeEnum] = Field(
        None, description="Type of jewelry piece (ring, chain, etc.)"
    )
    finish_type: Optional[FinishTypeEnum] = Field(
        None, description="Surface finish type"
    )
    complexity_rating: Optional[int] = Field(
        None, ge=1, le=5, description="Complexity 1-5 stars"
    )

    # Goldsmith Intake Fields (Pflichtfelder for order confirmation)
    alloy: Optional[str] = Field(
        None,
        max_length=20,
        description="Legierung: 333, 375, 585, 750, 900, 999, Ag925, Ag800, Pt950",
    )
    ring_size_mm: Optional[float] = Field(
        None, ge=30.0, le=100.0, description="Ringmass in mm (innerer Umfang)"
    )
    surface_finish: Optional[str] = Field(
        None,
        max_length=50,
        description="Oberflaechenbearbeitung: Hochglanz, Matt, Gebuerstet, etc.",
    )
    fitting_date: Optional[datetime] = Field(None, description="Anprobe-Datum")
    has_scrap_gold: Optional[bool] = Field(False, description="Altgold vorhanden?")
    special_instructions: Optional[str] = Field(
        None, max_length=2000, description="Sonderwuensche des Kunden"
    )

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Validate deadline is in the future."""
        if v is not None:
            # Allow deadlines in the past for historical orders
            # But warn if deadline is more than 10 years in the future
            if v.year > datetime.now(timezone.utc).year + 10:
                raise ValueError("Deadline cannot be more than 10 years in the future")
        return v

    @field_validator("materials")
    @classmethod
    def validate_materials(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        """Validate material IDs."""
        if v is not None:
            # Check all IDs are positive
            for material_id in v:
                if material_id <= 0:
                    raise ValueError(
                        f"Invalid material ID: {material_id}. Must be positive."
                    )
            # Check for duplicates
            if len(v) != len(set(v)):
                raise ValueError("Duplicate material IDs not allowed")
        return v


class OrderUpdate(BaseModel):
    """Schema für Order-Updates mit Validation."""

    title: Optional[str] = Field(
        None, min_length=1, max_length=200, description="New order title"
    )
    description: Optional[str] = Field(
        None, min_length=1, max_length=2000, description="New order description"
    )
    price: Optional[Money] = Field(
        None, ge=0, description="New agreed order price, NET excl. VAT"
    )
    status: Optional[OrderStatusEnum] = Field(
        None,
        description=(
            "Target status; validated by the W2-07 transition table "
            "(services/order_workflow.py). 409 when not allowed."
        ),
    )
    # W2-07 / DOM-13: inputs for the status change, not Order columns.
    status_reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Grund; required when status is on_hold or cancelled",
    )
    resume_date: Optional[date] = Field(
        None, description="Expected resume date when status is on_hold"
    )
    deadline: Optional[datetime] = Field(
        None, description="Order deadline for calendar"
    )
    current_location: Optional[str] = Field(
        None, min_length=1, max_length=50, description="Current storage location"
    )
    location_id: Optional[int] = Field(
        None, gt=0, description="Configured workshop location (Standort) id"
    )

    # Weight & Material
    estimated_weight_g: Optional[Weight] = Field(None, ge=0)
    actual_weight_g: Optional[Weight] = Field(None, ge=0)
    scrap_percentage: Optional[Percent] = Field(None, ge=0, le=50)

    # Metal Inventory Integration
    metal_type: Optional[MetalType] = Field(None, description="Type of metal to use")
    costing_method: Optional[CostingMethod] = Field(None, description="Costing method")
    specific_metal_purchase_id: Optional[int] = Field(
        None, gt=0, description="Specific metal batch ID"
    )

    # Cost Calculation
    material_cost_override: Optional[Money] = Field(None, ge=0)
    labor_hours: Optional[float] = Field(None, ge=0)
    hourly_rate: Optional[Money] = Field(None, ge=0)

    # Pricing
    profit_margin_percent: Optional[Percent] = Field(None, ge=0, le=100)
    vat_rate: Optional[Percent] = Field(None, ge=0, le=100)

    # ML feature fields (updatable at any point during order lifecycle)
    order_type: Optional[OrderTypeEnum] = Field(
        None, description="Type of jewelry piece"
    )
    finish_type: Optional[FinishTypeEnum] = Field(
        None, description="Surface finish type"
    )
    complexity_rating: Optional[int] = Field(
        None, ge=1, le=5, description="Complexity 1-5 stars"
    )

    # Goldsmith Intake Fields
    alloy: Optional[str] = Field(
        None,
        max_length=20,
        description="Legierung: 333, 375, 585, 750, 900, 999, Ag925, Ag800, Pt950",
    )
    ring_size_mm: Optional[float] = Field(
        None, ge=30.0, le=100.0, description="Ringmass in mm (innerer Umfang)"
    )
    surface_finish: Optional[str] = Field(
        None, max_length=50, description="Oberflaechenbearbeitung"
    )
    fitting_date: Optional[datetime] = Field(None, description="Anprobe-Datum")
    has_scrap_gold: Optional[bool] = Field(None, description="Altgold vorhanden?")
    special_instructions: Optional[str] = Field(
        None, max_length=2000, description="Sonderwuensche des Kunden"
    )

    # ── Slice 5 / A3.2 — Punzierungs-Check verification fields ──────────
    # Maria trimmed the dedicated /orders/{id}/punzierung-verify endpoint
    # from V1.1 scope; instead, the PunzierungsCheckModal calls the
    # existing PATCH /orders/{id} with these two fields. The service
    # layer (Slice 5 update_order) auto-sets retention_class='hallmark_10y'
    # the first time marks are recorded (A2.8).
    punzierung_verified_at: Optional[datetime] = Field(
        None,
        description=(
            "ISO timestamp at which the Punzierungs-Check was completed. "
            "Auto-filled by the service layer if omitted when marks are set."
        ),
    )
    punzierung_verified_marks: Optional[List[str]] = Field(
        None,
        description=(
            "Marks recorded during the Punzierungs-Check. At least one "
            "Feingehalt mark must be present; server validates the list."
        ),
        min_length=1,
    )

    @field_validator("punzierung_verified_marks")
    @classmethod
    def _validate_punzierung_marks(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Enforce the allowed-mark vocabulary (A3.2, widened by W2-09/D-10).

        Accepts, per entry:
          - a Feingehalt mark for *any* alloy (``goldsmith_erp.db.models.
            AlloyType``, the same enum the Altgold valuation uses) — both
            the legacy wire code (``feingehalt_585``) and the plain mark
            (``585``, ``Au585``) are allowed, see
            ``services/hallmark_vocabulary.py``;
          - the three non-Feingehalt marks (Meisterzeichen etc.);
          - a ``"nicht punziert: <Grund>"`` free-text entry (D-10 soft
            gate): the piece was deliberately not hallmarked, with a
            documented reason.

        This validator only checks each entry's *shape* against the full
        cross-alloy vocabulary — it cannot see the order's own alloy (a
        PATCH may set marks without resending alloy), so it does not
        reject a Feingehalt mark that does not match this particular
        order. That correlation is not needed either: the completion guard
        in ``services/order_workflow.py`` only requires *some* real
        Feingehalt mark or a documented reason, not proof it matches the
        stored alloy — the goldsmith is recording what they physically
        read off the piece.
        """
        if v is None:
            return v
        unknown = [m for m in v if not is_valid_mark(m)]
        if unknown:
            raise ValueError(
                f"Unknown punzierung marks: {unknown}. Allowed: a Feingehalt "
                "mark for the order's alloy (e.g. '585', 'Au585', "
                "'feingehalt_585'), meisterzeichen/herstellerzeichen/"
                "laenderzeichen, or 'nicht punziert: <Grund>'."
            )
        # Dedupe while preserving order so the audit trail matches the
        # goldsmith's selection order.
        seen: set[str] = set()
        deduped: List[str] = []
        for m in v:
            if m not in seen:
                seen.add(m)
                deduped.append(m)
        return deduped

    @field_validator("title", "description", "current_location")
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize text fields to prevent injection attacks."""
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Field cannot be empty or only whitespace")
        # Prevent SQL injection
        dangerous_patterns = [
            "DROP TABLE",
            "DELETE FROM",
            "INSERT INTO",
            "UPDATE ",
            "TRUNCATE",
            "ALTER TABLE",
            "CREATE TABLE",
            "--",
            ";--",
        ]
        v_upper = v.upper()
        for pattern in dangerous_patterns:
            if pattern in v_upper:
                raise ValueError(
                    f"Text contains potentially dangerous SQL keyword: {pattern}"
                )
        return v

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate price is reasonable."""
        if v is not None:
            if v < 0:
                raise ValueError("Price cannot be negative")
            if v > 1_000_000:
                raise ValueError("Price exceeds maximum allowed value (1,000,000)")
        return v


class OrderRead(OrderBase):
    """Schema für Order-Anzeige."""

    id: int
    status: OrderStatusEnum
    # W2-07 / DOM-13: set while on_hold / after cancelled.
    hold_reason: Optional[str] = None
    resume_date: Optional[date] = None
    cancel_reason: Optional[str] = None
    customer_id: int
    customer: Optional["CustomerRead"] = (
        None  # Optional - populated when explicitly requested
    )
    deadline: Optional[datetime] = None
    current_location: Optional[str] = None
    location_id: Optional[int] = None

    # Weight & Material
    estimated_weight_g: Optional[Weight] = None
    actual_weight_g: Optional[Weight] = None
    scrap_percentage: Optional[Percent] = number_default(5.0)

    # Metal Inventory Integration
    metal_type: Optional[MetalType] = None
    costing_method_used: Optional[CostingMethod] = CostingMethod.FIFO
    specific_metal_purchase_id: Optional[int] = None

    # Cost Calculation
    material_cost_calculated: Optional[Money] = None
    material_cost_override: Optional[Money] = None
    labor_hours: Optional[float] = None
    hourly_rate: Optional[Money] = number_default(75.00)
    labor_cost: Optional[Money] = None

    # Pricing
    profit_margin_percent: Optional[Percent] = number_default(40.0)
    vat_rate: Optional[Percent] = number_default(19.0)
    calculated_price: Optional[Money] = None

    created_at: datetime
    updated_at: datetime
    materials: Optional[List[MaterialBase]] = None

    # ML feature fields (read-only on responses — written by service layer)
    order_type: Optional[OrderTypeEnum] = None
    finish_type: Optional[FinishTypeEnum] = None
    complexity_rating: Optional[int] = None
    actual_hours: Optional[float] = None
    completed_at: Optional[datetime] = None

    # Goldsmith Intake Fields
    alloy: Optional[str] = None
    ring_size_mm: Optional[float] = None
    surface_finish: Optional[str] = None
    fitting_date: Optional[datetime] = None
    has_scrap_gold: Optional[bool] = None
    special_instructions: Optional[str] = None

    # "Zuletzt gescannt von … um … in …" (scan tracking). Filled on the
    # detail read only (GET /orders/{id}); null everywhere else.
    last_scan: Optional[LastScanRead] = None

    model_config = ConfigDict(from_attributes=True)


class OrderListRead(OrderRead):
    """Schema for one row of the orders list (``GET /orders/``).

    ``first_photo_id`` is the id of the order's oldest photo so the list can
    render a thumbnail via ``/photos/{id}/thumbnail`` (W2-01 / FE-13). It is
    design IP (DESIGN_VIEW): callers without it always receive ``None``.
    """

    first_photo_id: Optional[str] = None


class OrderStatusChange(BaseModel):
    """Body of ``PATCH /orders/{id}/status`` (W2-07)."""

    status: OrderStatusEnum = Field(..., description="Target status")
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Grund; required for on_hold and cancelled",
    )
    resume_date: Optional[date] = Field(
        None, description="Expected resume date (on_hold only)"
    )

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip() or None


TimelineKind = Literal["status", "customer_update", "photo", "time_entry"]


class OrderTimelineItem(BaseModel):
    """One entry of ``GET /orders/{id}/timeline`` (W2-07).

    ``data`` is already role-projected by the service: no prices, no
    customer free text, no design files.
    """

    kind: TimelineKind
    id: str
    at: datetime
    user_id: Optional[int] = None
    summary: str
    data: Dict[str, Any] = Field(default_factory=dict)


class OrderTimelineRead(BaseModel):
    """Merged, chronologically ascending order history."""

    order_id: int
    items: List[OrderTimelineItem]


class LocationChangeRequest(BaseModel):
    """Schema for changing an order's current location."""

    location: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Target workshop location (e.g. Werkbank 1, Tresor)",
    )
    location_id: Optional[int] = Field(
        None, gt=0, description="Configured workshop location (Standort) id"
    )

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Location cannot be empty")
        return v

    @model_validator(mode="after")
    def _location_or_id(self) -> "LocationChangeRequest":
        if self.location is None and self.location_id is None:
            raise ValueError("Bitte einen Standort angeben.")
        return self


class LocationHistoryRead(BaseModel):
    """Schema for a single location history entry."""

    id: int
    order_id: int
    location: str
    timestamp: datetime
    changed_by: int

    model_config = ConfigDict(from_attributes=True)


# Resolve forward references after all models are defined
# This allows the CustomerRead forward reference to be properly resolved
def _resolve_forward_refs():
    """Resolve forward references in OrderRead model."""
    try:
        from goldsmith_erp.models.customer import CustomerRead

        OrderRead.model_rebuild()
        OrderListRead.model_rebuild()
    except ImportError:
        # If customer module isn't available yet, that's okay
        # The forward reference will be resolved when it's imported elsewhere
        pass


# Call the resolver
_resolve_forward_refs()
