"""Customer/Client Pydantic Models for CRM"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class CustomerBase(BaseModel):
    """Base Customer schema with common fields"""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    email: EmailStr = Field(..., description="Customer email address")
    phone: Optional[str] = Field(None, max_length=50)
    mobile: Optional[str] = Field(None, max_length=50)
    street: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: str = Field("Deutschland", max_length=100)
    customer_type: str = Field("private", description="private or business")
    source: Optional[str] = Field(
        None, max_length=100, description="How customer found us"
    )
    notes: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)

    # Measurement Library (Mass-Bibliothek). Bounds match the wider
    # anthropometric ranges enforced by `models/measurement.py` so that a
    # value accepted by the per-measurement endpoint can also be stored on
    # the legacy convenience fields here.
    ring_size: Optional[float] = Field(
        None, ge=30, le=90, description="EU ring size (mm inner circumference)"
    )
    chain_length_cm: Optional[float] = Field(
        None, ge=25, le=150, description="Chain length in cm"
    )
    bracelet_length_cm: Optional[float] = Field(
        None, ge=8, le=35, description="Bracelet length in cm (= wrist circumference)"
    )
    allergies: Optional[str] = Field(
        None, max_length=500, description="e.g. Nickel, Kupfer"
    )
    preferences: Optional[dict] = Field(
        default_factory=dict, description="Key-value preferences"
    )
    birthday: Optional[datetime] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name contains only allowed characters"""
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        v = v.strip()
        # Allow letters, spaces, hyphens, apostrophes, and common diacritics
        if not re.match(r"^[a-zA-ZäöüÄÖÜßàáâãèéêìíîòóôõùúûçñ\s'\-\.]+$", v):
            raise ValueError("Name contains invalid characters")
        return v

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate company name if provided"""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # Allow alphanumeric, spaces, and common business characters
        if not re.match(r"^[a-zA-Z0-9äöüÄÖÜß\s&.,\-()]+$", v):
            raise ValueError("Company name contains invalid characters")
        return v

    @field_validator("customer_type")
    @classmethod
    def validate_customer_type(cls, v: str) -> str:
        """Validate customer type"""
        allowed_types = ["private", "business"]
        if v not in allowed_types:
            raise ValueError(
                f"Customer type must be one of: {', '.join(allowed_types)}"
            )
        return v

    @field_validator("phone", "mobile")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format"""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # Allow numbers, spaces, +, -, (), /
        if not re.match(r"^[\d\s+\-()\/]+$", v):
            raise ValueError("Phone number contains invalid characters")
        return v

    @field_validator("postal_code")
    @classmethod
    def validate_postal_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate postal code format"""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # For Germany: 5 digits, but allow international formats
        if not re.match(r"^[\d\s\-A-Z]{3,10}$", v):
            raise ValueError("Invalid postal code format")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> List[str]:
        """Validate tags list"""
        if v is None:
            return []
        # Remove empty tags and duplicates
        tags = [tag.strip() for tag in v if tag and tag.strip()]
        return list(set(tags))  # Remove duplicates


class CustomerCreate(CustomerBase):
    """Schema for creating a new customer"""

    pass


class CustomerUpdate(BaseModel):
    """Schema for updating a customer (all fields optional)"""

    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    mobile: Optional[str] = Field(None, max_length=50)
    street: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    customer_type: Optional[str] = None
    source: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None

    # Measurement Library
    ring_size: Optional[float] = Field(None, ge=30, le=90)
    chain_length_cm: Optional[float] = Field(None, ge=25, le=150)
    bracelet_length_cm: Optional[float] = Field(None, ge=8, le=35)
    allergies: Optional[str] = Field(None, max_length=500)
    preferences: Optional[dict] = None
    birthday: Optional[datetime] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate name if provided"""
        if v is None:
            return v
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        v = v.strip()
        if not re.match(r"^[a-zA-ZäöüÄÖÜßàáâãèéêìíîòóôõùúûçñ\s'\-\.]+$", v):
            raise ValueError("Name contains invalid characters")
        return v


class CustomerRead(CustomerBase):
    """Schema for reading a customer (includes DB fields)"""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomerListItem(BaseModel):
    """Lightweight schema for customer lists"""

    id: int
    first_name: str
    last_name: str
    company_name: Optional[str]
    email: str
    phone: Optional[str]
    customer_type: str
    tags: List[str]
    is_active: bool

    class Config:
        from_attributes = True


class CustomerWithOrders(CustomerRead):
    """Customer schema with order count"""

    order_count: int = 0
    total_spent: float = 0.0
    last_order_date: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# GDPR Art. 15 export — typed response for GET /customers/{id}/export
# (item D, ECC-review fix wave). Replaces the previous
# ``response_model=Dict[str, Any]``, which let any key silently ride along
# in the response body with zero structural enforcement — including, in
# principle, a future accidental addition of a design-IP field to the
# consultations list. Every field below mirrors exactly what
# ``api/routers/customers.py``'s ``gdpr_export_customer`` endpoint already
# serializes; nothing here changes the wire shape, it only types it.
# ---------------------------------------------------------------------------


class CustomerGdprExportCustomer(BaseModel):
    """The ``customer`` block of the GDPR export payload."""

    id: int
    first_name: str
    last_name: str
    company_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    mobile: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    customer_type: str
    source: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    ring_size: Optional[float] = None
    chain_length_cm: Optional[float] = None
    bracelet_length_cm: Optional[float] = None
    allergies: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None
    # Pre-formatted ISO-8601 string — the endpoint already calls
    # ``.isoformat()`` before building this dict; typed as ``str`` (not
    # ``datetime``) to match exactly what's serialized today.
    birthday: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None


class CustomerOrderExport(BaseModel):
    """One entry in the export payload's ``orders`` list.

    ``status`` is typed ``str`` (the enum's ``.value``), not
    ``db.models.OrderStatusEnum``, deliberately: importing anything from
    ``db.models`` at module load time here re-creates a real circular
    import (``db.models`` -> ``models.time_entry_metadata`` triggers
    ``goldsmith_erp.models.__init__`` -> ``models.order`` -> (forward-ref
    resolution) -> ``models.customer`` -> back into the still-mid-import
    ``db.models``) that breaks ``OrderRead``'s forward-reference rebuild
    in ``models/order.py`` for the rest of the process. Verified
    empirically — do not reintroduce a ``from goldsmith_erp.db.models
    import ...`` at this module's top level.
    """

    id: int
    status: str
    description: Optional[str] = None
    price: Optional[float] = None
    created_at: Optional[str] = None
    deadline: Optional[str] = None


class CustomerMeasurementExport(BaseModel):
    """One entry in the export payload's ``measurements`` list."""

    id: int
    measurement_type: Optional[str] = None
    value: float
    unit: str
    hand: Optional[str] = None
    finger: Optional[str] = None
    notes: Optional[str] = None
    measured_at: Optional[str] = None


class NoGoExport(BaseModel):
    """One entry in the export payload's ``no_gos`` list.

    ``category`` is typed ``str`` (the enum's ``.value``), not
    ``db.models.NoGoCategory`` — see the circular-import note on
    ``CustomerOrderExport.status``; the same hazard applies here.
    """

    category: Optional[str] = None
    value: str
    note: Optional[str] = None
    created_at: Optional[str] = None


class ConsultationExportItem(BaseModel):
    """One entry in the export payload's ``consultations`` list.

    Design-IP exclusion (CLAUDE.md, binding; issue #14): this model
    deliberately declares NO ``wishes``, ``notes``, ``source_material``, or
    ``materials_discussed`` fields — those are the GOLDSMITH's design work
    product, not the data subject's personal data, and must never appear in
    a GDPR export. ``extra="forbid"`` makes that a STRUCTURAL guarantee
    rather than a convention: if a future change to the export endpoint
    ever adds one of those keys (or any other undeclared key) to a
    consultation dict, response validation fails loudly (500) instead of
    silently leaking design IP into an Art. 15 export. See
    ``design_data_excluded`` on ``CustomerGdprExport`` and the docstring on
    the export endpoint for the full rationale.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    occasion: Optional[str] = None
    occasion_date: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    converted_order_id: Optional[int] = None
    converted_quote_id: Optional[int] = None


class CustomerGdprExport(BaseModel):
    """GDPR Art. 15 data export payload — GET /customers/{id}/export.

    ``response_model`` for the export endpoint (item D, ECC-review fix
    wave). See ``ConsultationExportItem`` for the design-IP structural
    enforcement rationale.
    """

    export_date: str
    customer: CustomerGdprExportCustomer
    orders: List[CustomerOrderExport] = Field(default_factory=list)
    measurements: List[CustomerMeasurementExport] = Field(default_factory=list)
    no_gos: List[NoGoExport] = Field(default_factory=list)
    style_profile: Dict[str, Any] = Field(default_factory=dict)
    consultations: List[ConsultationExportItem] = Field(default_factory=list)
    # Machine-readable companion to the design-IP exclusion documented on
    # ConsultationExportItem — always True (the export endpoint has no
    # code path that includes design IP).
    design_data_excluded: bool = True
