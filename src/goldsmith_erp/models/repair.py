# src/goldsmith_erp/models/repair.py
"""
Pydantic schemas for the Repair Tracking module (Reparaturverwaltung).

All financial fields (estimated_cost, actual_cost, estimated_value) are
visible only to GOLDSMITH and ADMIN roles — enforced at the router level.
"""

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from goldsmith_erp.db.models import RepairItemType, RepairJobStatus, RepairPhotoPhase


def _strip_tzinfo(value: Optional[datetime]) -> Optional[datetime]:
    """
    Convert any tz-aware datetime to naive UTC.

    The browser submits ISO timestamps with a ``Z`` suffix (e.g.
    ``2026-05-14T00:00:00.000Z``); Pydantic parses those as tz-aware.
    The repair_jobs columns are ``TIMESTAMP WITHOUT TIME ZONE`` (asyncpg
    refuses to bind a tz-aware datetime there). Normalise to naive UTC
    so the DB write succeeds and stored times remain comparable to the
    other naive timestamps in the same row (created_at / updated_at).
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# ============================================================================
# REPAIR PHOTO SCHEMAS
# ============================================================================


class RepairPhotoRead(BaseModel):
    """Read-only schema for a repair photo."""

    id: int
    repair_job_id: int
    phase: RepairPhotoPhase
    file_path: str
    timestamp: datetime
    taken_by: Optional[int] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# REPAIR JOB SCHEMAS — CREATE / UPDATE
# ============================================================================


class RepairJobCreate(BaseModel):
    """
    Schema for creating a new repair intake (Reparatur-Eingang).

    Required at intake: customer, item description, item type.
    Everything else (diagnosis, cost estimate, dates) comes later.
    """

    customer_id: Optional[int] = Field(
        None, gt=0, description="Kunden-ID (optional — Laufkunde moeglich)"
    )
    item_description: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Beschreibung des Stuecks, z.B. 'Ehering Gelbgold 585, Stein lose'",
    )
    item_type: RepairItemType = Field(..., description="Art des Schmuckstuecks")
    metal_type: Optional[str] = Field(
        None, max_length=100, description="Metallbezeichnung, z.B. '585 Gelbgold'"
    )
    estimated_value: Optional[float] = Field(
        None, ge=0, description="Versicherungswert in EUR"
    )
    estimated_completion_date: Optional[datetime] = Field(
        None, description="Voraussichtliches Fertigstellungsdatum"
    )

    _strip_tz_completion = field_validator("estimated_completion_date", mode="after")(
        lambda cls, v: _strip_tzinfo(v)
    )

    @field_validator("item_description")
    @classmethod
    def sanitize_description(cls, v: str) -> str:
        """Strip whitespace and reject empty strings."""
        v = v.strip()
        if not v:
            raise ValueError("Beschreibung darf nicht leer sein")
        return v


class RepairDiagnoseInput(BaseModel):
    """
    Schema for recording a diagnosis and cost estimate.

    Called after the goldsmith has inspected the piece and determined
    what work is needed and what it will cost.
    """

    diagnosis_notes: str = Field(
        ..., min_length=1, max_length=5000, description="Befundbeschreibung"
    )
    estimated_cost: float = Field(..., ge=0, description="Kostenvoranschlag in EUR")
    estimated_completion_date: Optional[datetime] = Field(
        None, description="Voraussichtliches Fertigstellungsdatum (aktualisiert)"
    )

    _strip_tz_completion = field_validator("estimated_completion_date", mode="after")(
        lambda cls, v: _strip_tzinfo(v)
    )


class RepairStatusUpdate(BaseModel):
    """Generic status update — used for simple transitions like APPROVED or CANCELLED."""

    notes: Optional[str] = Field(
        None, max_length=2000, description="Optionale Anmerkung"
    )


class RepairCompleteInput(BaseModel):
    """
    Schema for marking a repair as READY (Fertigmeldung).

    Records the actual cost which may differ from the estimate.
    """

    actual_cost: float = Field(..., ge=0, description="Tatsaechliche Kosten in EUR")
    notes: Optional[str] = Field(None, max_length=2000)


# ============================================================================
# REPAIR JOB SCHEMAS — READ
# ============================================================================


class CustomerSummary(BaseModel):
    """Minimal customer info embedded in repair responses."""

    id: int
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RepairJobRead(BaseModel):
    """
    Full repair job detail — returned by GET /repairs/{id}.

    Financial fields (estimated_cost, actual_cost, estimated_value) are
    included here; the router enforces GOLDSMITH/ADMIN access.
    """

    id: int
    repair_number: str
    bag_number: str
    customer_id: Optional[int] = None
    customer: Optional[CustomerSummary] = None
    received_by: Optional[int] = None
    item_description: str
    item_type: RepairItemType
    metal_type: Optional[str] = None
    estimated_value: Optional[float] = None
    status: RepairJobStatus
    diagnosis_notes: Optional[str] = None
    estimated_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    estimated_completion_date: Optional[datetime] = None
    actual_completion_date: Optional[datetime] = None
    customer_notified_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    photos: List[RepairPhotoRead] = []

    model_config = ConfigDict(from_attributes=True)


class RepairJobListItem(BaseModel):
    """
    Condensed repair job for the list view (GET /repairs/).

    Excludes heavy fields (photos, diagnosis_notes) for list performance.
    """

    id: int
    repair_number: str
    bag_number: str
    customer_id: Optional[int] = None
    customer: Optional[CustomerSummary] = None
    item_description: str
    item_type: RepairItemType
    metal_type: Optional[str] = None
    status: RepairJobStatus
    estimated_cost: Optional[float] = None
    estimated_completion_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
