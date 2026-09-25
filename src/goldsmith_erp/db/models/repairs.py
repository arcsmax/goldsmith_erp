"""Repair jobs and repair photos."""

import enum

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import MONEY_NUMERIC, Base, SAEnum
from goldsmith_erp.db.types import UtcDateTime

# ============================================================================
# REPAIR TRACKING (REPARATURVERWALTUNG)
# ============================================================================


class RepairJobStatus(str, enum.Enum):
    """
    Lifecycle states for a repair job.

    Follows the physical flow through the workshop:
    Eingang -> Diagnose -> Angebot -> Genehmigt -> Reparatur ->
    Qualitaetskontrolle -> Abholbereit -> Abgeholt | Storniert
    """

    RECEIVED = "received"  # Eingang — Stueck angenommen
    DIAGNOSED = "diagnosed"  # Diagnose — Fehler festgestellt
    QUOTED = "quoted"  # Angebot erstellt, wartet auf Kundenzusage
    APPROVED = "approved"  # Kunde hat Angebot genehmigt
    IN_REPAIR = "in_repair"  # Reparatur laeuft
    QUALITY_CHECK = "quality_check"  # Qualitaetskontrolle
    READY = "ready"  # Abholbereit
    PICKED_UP = "picked_up"  # Abgeholt
    CANCELLED = "cancelled"  # Storniert


class RepairItemType(str, enum.Enum):
    """Type of jewelry item being repaired."""

    RING = "ring"  # Ring
    CHAIN = "chain"  # Kette
    BRACELET = "bracelet"  # Armband
    EARRING = "earring"  # Ohrringe
    WATCH = "watch"  # Uhr
    BROOCH = "brooch"  # Brosche
    OTHER = "other"  # Sonstiges


class RepairPhotoPhase(str, enum.Enum):
    """Phase during which a repair photo was taken."""

    INTAKE = "intake"  # Eingang — Zustand bei Annahme
    DURING_REPAIR = "during_repair"  # Waehrend der Reparatur
    COMPLETED = "completed"  # Fertig — Ergebnis


class RepairJob(Base):
    """
    Reparaturauftrag — repair order for an existing piece of jewelry.

    Repair jobs are distinct from production orders (Order table):
    - They have a physical bag/envelope with a number for physical tracking
    - They go through an estimate → approval workflow before work begins
    - Customer notification events (REPAIR_RECEIVED, REPAIR_READY) are tracked
    - Estimated and actual costs are both recorded for Nachkalkulation
    """

    __tablename__ = "repair_jobs"

    id = Column(Integer, primary_key=True, index=True)

    # Repair number: REP-YYYY-NNNN (unique, auto-generated)
    repair_number = Column(String(20), unique=True, nullable=False, index=True)

    # Physical bag/envelope number for workshop floor tracking
    # (piece sits in a numbered paper tray until pickup)
    bag_number = Column(String(20), nullable=False, index=True)

    # Links
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    received_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # ARCH phase 5: the job spine row (services/job_service keeps it in sync).
    job_id = Column(
        Integer,
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Item details
    item_description = Column(Text, nullable=False)
    item_type = Column(
        SAEnum(RepairItemType), nullable=False, default=RepairItemType.OTHER
    )
    metal_type = Column(
        String(50), nullable=True
    )  # Free text: "585 Gelbgold", "Silber 925"
    estimated_value = Column(
        MONEY_NUMERIC, nullable=True
    )  # Versicherungswert des Stuecks in EUR

    # Status
    status = Column(
        SAEnum(RepairJobStatus),
        nullable=False,
        default=RepairJobStatus.RECEIVED,
        index=True,
    )

    # Diagnosis & cost
    diagnosis_notes = Column(Text, nullable=True)
    estimated_cost = Column(MONEY_NUMERIC, nullable=True)  # Kostenvoranschlag in EUR
    actual_cost = Column(
        MONEY_NUMERIC, nullable=True
    )  # Tatsaechliche Kosten nach Reparatur

    # Dates
    estimated_completion_date = Column(UtcDateTime, nullable=True, index=True)
    actual_completion_date = Column(UtcDateTime, nullable=True)
    customer_notified_at = Column(
        UtcDateTime, nullable=True
    )  # When READY notification was sent
    picked_up_at = Column(UtcDateTime, nullable=True)

    # Soft delete (30-day grace period before hard delete per GDPR Art. 17)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(UtcDateTime, nullable=True)

    # Audit timestamps
    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # V1.1 — Eingangs-Checkliste (repair photo-intake checklist). Seeded from
    # settings.REPAIR_INTAKE_CHECKLIST at creation; item shape documented in
    # models.repair.IntakeChecklistItem (not enforced by the DB), e.g.
    # {"key": str, "label": str, "status": "open"|"photo"|"na",
    #  "photo_id": int|None, "na_reason": str|None}. Mirrors
    # Customer.style_profile's JSON-column pattern.
    intake_checklist = Column(JSON, nullable=True)

    # Relationships
    customer = relationship("Customer")
    received_by_user = relationship("User", foreign_keys=[received_by])
    job = relationship("Job", back_populates="repair", foreign_keys=[job_id])
    photos = relationship(
        "RepairPhoto",
        back_populates="repair_job",
        cascade="all, delete-orphan",
        order_by="RepairPhoto.timestamp.asc()",
    )

    def __repr__(self) -> str:
        return (
            f"<RepairJob {self.repair_number} "
            f"status={self.status.value} "
            f"bag={self.bag_number}>"
        )


class RepairPhoto(Base):
    """
    Foto-Dokumentation fuer Reparaturauftraege.

    Photos are grouped by phase (INTAKE / DURING_REPAIR / COMPLETED) so the
    customer can see before/after documentation and the workshop has a visual
    audit trail for each step.

    DEPRECATED (ARCH phase 4): superseded by ``media_assets`` (MediaAsset).
    Still dual-written for one release; read new code from media_assets.
    """

    __tablename__ = "repair_photos"

    id = Column(Integer, primary_key=True, index=True)
    repair_job_id = Column(
        Integer,
        ForeignKey("repair_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase = Column(
        SAEnum(RepairPhotoPhase), nullable=False, default=RepairPhotoPhase.INTAKE
    )
    file_path = Column(String(500), nullable=False)
    timestamp = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    taken_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes = Column(Text, nullable=True)

    # Relationships
    repair_job = relationship("RepairJob", back_populates="photos")
    taken_by_user = relationship("User", foreign_keys=[taken_by])

    def __repr__(self) -> str:
        return f"<RepairPhoto repair={self.repair_job_id} " f"phase={self.phase.value}>"
