"""Job spine (ARCH-02, ARCH phase 5, ADR-2026-09-25-jobs-spine).

One ``jobs`` row per Auftrag (``orders``) and per Reparatur
(``repair_jobs``). The per-kind tables stay the source of truth for this
release: ``services/job_service.py`` copies customer, number, title,
status, deadline and hold fields into the job whenever the service layer
creates a row or changes its status. Nothing writes ``jobs`` directly.

``status`` is the unified lifecycle (:class:`JobStatus`) mapped from
``OrderStatusEnum`` / ``RepairJobStatus``; ``kind_status`` keeps the raw
per-kind value so a kanban can still show the finer stage.

Statuses are String columns with CHECK constraints (the ``media_assets``
precedent), so adding a value needs no ``ALTER TYPE``.
"""

import enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import Base
from goldsmith_erp.db.types import UtcDateTime


class JobKind(str, enum.Enum):
    """What a job wraps."""

    ORDER = "order"  # Auftrag (Neuanfertigung)
    REPAIR = "repair"  # Reparatur


class JobStatus(str, enum.Enum):
    """Unified lifecycle across orders and repairs (kanban columns)."""

    DRAFT = "draft"  # Entwurf (order draft / legacy new)
    INTAKE = "intake"  # Eingang / Diagnose (repair received, diagnosed)
    AWAITING_APPROVAL = "awaiting_approval"  # Angebot beim Kunden (repair quoted)
    CONFIRMED = "confirmed"  # Bestätigt / genehmigt
    IN_PROGRESS = "in_progress"  # In Arbeit (bench, fitting, setting, repair)
    QUALITY_CHECK = "quality_check"  # Qualitätskontrolle
    READY = "ready"  # Fertig / abholbereit
    DELIVERED = "delivered"  # Ausgeliefert / abgeholt
    ON_HOLD = "on_hold"  # Pausiert
    CANCELLED = "cancelled"  # Storniert


JOB_KIND_VALUES = tuple(member.value for member in JobKind)
JOB_STATUS_VALUES = tuple(member.value for member in JobStatus)

#: Number-sequence kinds (``number_sequences.kind``) of the job numbers.
ORDER_NUMBER_KIND = "AU"
REPAIR_NUMBER_KIND = "REP"


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class Job(Base):
    """A Vorgang: one order or one repair, as the shared spine."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in_list("kind", JOB_KIND_VALUES), name="ck_jobs_kind"),
        CheckConstraint(_in_list("status", JOB_STATUS_VALUES), name="ck_jobs_status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(10), nullable=False, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Auftragsnummer AU-YYYY-NNNN / Reparaturnummer REP-YYYY-NNNN, both
    # from the per-year number_sequences counters (D-12).
    number = Column(String(20), nullable=False, unique=True, index=True)
    # Copy of orders.title / repair_jobs.item_description (GDPR scrub
    # target "jobs.title", services/customer_service.SCRUBBABLE_FIELDS).
    title = Column(String(200), nullable=True)
    status = Column(String(30), nullable=False, index=True)
    kind_status = Column(String(30), nullable=False)
    deadline = Column(UtcDateTime, nullable=True, index=True)
    on_hold_since = Column(UtcDateTime, nullable=True)
    resume_date = Column(Date, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    customer = relationship("Customer")
    order = relationship(
        "Order", back_populates="job", uselist=False, foreign_keys="Order.job_id"
    )
    repair = relationship(
        "RepairJob",
        back_populates="job",
        uselist=False,
        foreign_keys="RepairJob.job_id",
    )

    def __repr__(self) -> str:
        return f"<Job {self.number} kind={self.kind} status={self.status}>"


Index("ix_jobs_status_deadline", Job.status, Job.deadline)
