# src/goldsmith_erp/models/repair.py
"""
Pydantic schemas for the Repair Tracking module (Reparaturverwaltung).

All financial fields (estimated_cost, actual_cost, estimated_value) are
visible only to holders of FINANCIAL_VIEW (GOLDSMITH, ADMIN): the repair
router strips them via api/role_projection.py (SEC-01, GDPR-03).
"""

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from goldsmith_erp.core.timeutil import ensure_utc
from goldsmith_erp.db.models import RepairItemType, RepairJobStatus, RepairPhotoPhase
from goldsmith_erp.models._common import Money
from goldsmith_erp.models.scan_history import LastScanRead


def _strip_tzinfo(value: Optional[datetime]) -> Optional[datetime]:
    """
    Normalise to aware UTC (BE-15; the name is kept for the validators).

    The browser submits ISO timestamps with a ``Z`` suffix; the columns are
    ``TIMESTAMP WITH TIME ZONE`` now, so aware values are kept (converted to
    UTC) and a naive value is read as UTC.
    """
    return ensure_utc(value)


INTAKE_PROBLEM_MAX_LENGTH = 1000
INTAKE_CONDITION_MAX_ITEMS = 12
INTAKE_CONDITION_MAX_LENGTH = 80


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
# INTAKE CHECKLIST SCHEMAS
# ============================================================================


class IntakeChecklistItem(BaseModel):
    """
    One item of the repair intake checklist (Eingangs-Checkliste).

    Dispute protection mirroring insurance-industry intake practice: every
    item is satisfied EITHER by an INTAKE-phase photo (status="photo",
    photo_id set) OR by an explicit "nicht zutreffend" declaration with a
    reason (status="na", na_reason set, >=3 non-whitespace characters).
    "open" items have neither set yet — the initial seeded state.

    The two satisfaction paths are mutually exclusive by construction: a
    "photo" item may not also carry an na_reason, and an "na" item may not
    also carry a photo_id. This keeps the stored shape unambiguous for
    downstream consumers (UI status chips, audit review).
    """

    key: str = Field(
        ..., min_length=1, max_length=100, description="Stabiler Schluessel (Slug)"
    )
    label: str = Field(..., min_length=1, max_length=200, description="Anzeigetext")
    status: Literal["open", "photo", "na"] = "open"
    photo_id: Optional[int] = Field(
        None, gt=0, description="Verknuepftes INTAKE-Phase-Foto"
    )
    na_reason: Optional[str] = Field(
        None, max_length=500, description="Begruendung fuer 'nicht zutreffend'"
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _validate_status_consistency(self) -> "IntakeChecklistItem":
        if self.status == "na":
            if not self.na_reason or len(self.na_reason.strip()) < 3:
                raise ValueError(
                    "Status 'nicht zutreffend' erfordert eine Begruendung "
                    "mit mindestens 3 Zeichen"
                )
            if self.photo_id is not None:
                raise ValueError(
                    "Status 'nicht zutreffend' darf kein verknuepftes Foto haben"
                )
        elif self.status == "photo":
            if self.photo_id is None:
                raise ValueError("Status 'photo' erfordert eine verknuepfte photo_id")
            if self.na_reason is not None:
                raise ValueError("Status 'photo' darf keine na_reason haben")
        else:  # "open"
            if self.photo_id is not None or self.na_reason is not None:
                raise ValueError(
                    "Status 'open' darf weder photo_id noch na_reason haben"
                )
        return self


class IntakeChecklistUpdate(BaseModel):
    """Request body for PUT /repairs/{id}/intake-checklist."""

    items: List[IntakeChecklistItem] = Field(..., max_length=20)


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
    estimated_value: Optional[Money] = Field(
        None, ge=0, description="Versicherungswert in EUR"
    )
    estimated_completion_date: Optional[datetime] = Field(
        None, description="Zugesagter Fertigstellungstermin"
    )
    # W2-12 counter intake (FE-17, DOM-08). No dedicated columns yet: the
    # service folds problem and condition into item_description (see
    # repair_service.compose_intake_description); the price indication is
    # stored as estimated_cost and replaced by the KVA at diagnosis.
    customer_problem: Optional[str] = Field(
        None,
        max_length=INTAKE_PROBLEM_MAX_LENGTH,
        description="Vom Kunden geschildertes Problem",
    )
    condition_notes: List[str] = Field(
        default_factory=list,
        max_length=INTAKE_CONDITION_MAX_ITEMS,
        description="Zustand bei Annahme, z.B. ['Kratzer', 'Tragespuren']",
    )
    estimated_cost: Optional[Money] = Field(
        None, ge=0, description="Erste Preisindikation in EUR (unverbindlich)"
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

    @field_validator("customer_problem")
    @classmethod
    def sanitize_problem(cls, v: Optional[str]) -> Optional[str]:
        """Blank problem text counts as not given."""
        if v is None:
            return None
        return v.strip() or None

    @field_validator("condition_notes")
    @classmethod
    def sanitize_conditions(cls, v: List[str]) -> List[str]:
        """Trim, drop blanks and duplicates, cap each note's length."""
        cleaned: List[str] = []
        for note in v:
            text = note.strip()
            if len(text) > INTAKE_CONDITION_MAX_LENGTH:
                raise ValueError(
                    f"Zustandsnotiz ist zu lang (max. {INTAKE_CONDITION_MAX_LENGTH} "
                    "Zeichen)"
                )
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned


class RepairDiagnoseInput(BaseModel):
    """
    Schema for recording a diagnosis and cost estimate.

    Called after the goldsmith has inspected the piece and determined
    what work is needed and what it will cost.
    """

    diagnosis_notes: str = Field(
        ..., min_length=1, max_length=5000, description="Befundbeschreibung"
    )
    estimated_cost: Money = Field(..., ge=0, description="Kostenvoranschlag in EUR")
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

    actual_cost: Money = Field(..., ge=0, description="Tatsaechliche Kosten in EUR")
    notes: Optional[str] = Field(None, max_length=2000)


# ============================================================================
# REPAIR JOB SCHEMAS — READ
# ============================================================================


class CustomerSummary(BaseModel):
    """Minimal customer info embedded in repair responses."""

    id: int
    first_name: str
    last_name: str
    email: Optional[str] = None  # W2-10: customers may have no email
    phone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RepairJobRead(BaseModel):
    """
    Full repair job detail — returned by GET /repairs/{id}.

    Financial fields (estimated_cost, actual_cost, estimated_value) and
    ``photos`` are included here; the router strips them for callers without
    FINANCIAL_VIEW / DESIGN_VIEW (api/role_projection.py).
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
    estimated_value: Optional[Money] = None
    status: RepairJobStatus
    diagnosis_notes: Optional[str] = None
    estimated_cost: Optional[Money] = None
    actual_cost: Optional[Money] = None
    estimated_completion_date: Optional[datetime] = None
    actual_completion_date: Optional[datetime] = None
    customer_notified_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    photos: List[RepairPhotoRead] = []
    intake_checklist: Optional[List[IntakeChecklistItem]] = None
    # "Zuletzt gescannt von … um … in …" (scan tracking); detail read only.
    last_scan: Optional[LastScanRead] = None

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
    estimated_cost: Optional[Money] = None
    estimated_completion_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
