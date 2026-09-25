"""Activities, time entries, interruptions, location history, estimate accuracy."""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import MONEY_NUMERIC, Base
from goldsmith_erp.db.types import UtcDateTime


class Activity(Base):
    """Aktivitäts-Presets für Time-Tracking"""

    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(
        String(50), nullable=False, index=True
    )  # fabrication, administration, waiting
    icon = Column(String(10))  # Emoji
    color = Column(String(7))  # Hex color #FF6B6B
    usage_count = Column(Integer, default=0, index=True)
    average_duration_minutes = Column(Float)
    last_used = Column(UtcDateTime)
    is_custom = Column(Boolean, default=False)
    is_billable = Column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )  # fabrication billable; administration/waiting non-billable by default
    hourly_rate = Column(Numeric(10, 2), nullable=True)
    # Per-activity labor rate (EUR/hour). NULL = use the shop default
    # (settings.DEFAULT_HOURLY_RATE) — see CostCalculationService.
    # Deliberately Numeric(10, 2), not Float, even though the legacy cost
    # module (Order.hourly_rate/labor_cost above) works in float — money
    # needs exact decimal arithmetic, so this column is an intentional
    # exception, not an inconsistency to "fix".
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at = Column(UtcDateTime, default=utcnow)

    # Beziehungen
    creator = relationship("User", foreign_keys=[created_by])
    time_entries = relationship("TimeEntry", back_populates="activity")


class TimeEntry(Base):
    """Haupt-Zeiterfassung"""

    __tablename__ = "time_entries"
    # BE-12 (W1-17): at most one running timer (end_time IS NULL) per user.
    # Partial unique index on both dialects so a double tap cannot create two
    # open entries; the service maps the IntegrityError to a 409.
    # Migration: 20260925_w117_one_running_timer.
    __table_args__ = (
        Index(
            "uq_time_entries_one_running",
            "user_id",
            unique=True,
            postgresql_where=text("end_time IS NULL"),
            sqlite_where=text("end_time IS NULL"),
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    activity_id = Column(
        Integer, ForeignKey("activities.id"), nullable=False, index=True
    )
    start_time = Column(UtcDateTime, nullable=False, index=True)
    end_time = Column(UtcDateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    # Legacy text column, kept in sync with ``location_id`` for one release
    # (migration 20260925_w8_workshop_locations).
    location = Column(String(50))
    location_id = Column(
        Integer,
        ForeignKey("workshop_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    complexity_rating = Column(Integer)  # 1-5
    quality_rating = Column(Integer)  # 1-5
    rework_required = Column(Boolean, default=False)
    notes = Column(Text)
    extra_metadata = Column(JSON)  # Flexible für zusätzliche Daten
    created_at = Column(UtcDateTime, default=utcnow)

    # ── Slice 2 — origin + correction tracking + retention ────────────
    # A2-origin — Lena §1 adoption metric. Values: 'manual' | 'scan' |
    # 'recovery' | 'import'. Back-populated to 'manual' for pre-Slice-2
    # rows by the migration; every new row must set this explicitly.
    origin = Column(
        String(20),
        nullable=False,
        server_default=text("'manual'"),
        default="manual",
    )
    # A2.2 — self-FK to the entry this row corrects (admin payroll fix).
    # ON DELETE SET NULL so that deleting the original entry (rare, only
    # via admin tools) leaves the correction in place as a standalone row.
    correction_of = Column(
        String(36),
        ForeignKey(
            "time_entries.id",
            name="fk_time_entries_correction_of_self",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    # A2.7 — HGB §257 requires 10-year financial retention.
    retention_class = Column(
        String(32),
        nullable=False,
        server_default=text("'financial_10y'"),
        default="financial_10y",
    )

    # Beziehungen
    order = relationship("Order", back_populates="time_entries")
    user = relationship("User")
    activity = relationship("Activity", back_populates="time_entries")
    interruptions = relationship(
        "Interruption", back_populates="time_entry", cascade="all, delete-orphan"
    )
    photos = relationship("OrderPhoto", back_populates="time_entry")


# --------------------------------------------------------------------------- #
# Defence-in-depth guard for `time_entries.extra_metadata` (O3)
# --------------------------------------------------------------------------- #
#
# Layer A (Pydantic `TimeEntryMetadata` on the API boundary) covers every
# legitimate HTTP write. This listener covers the residual surface:
# service-layer code that constructs a `TimeEntry` ORM instance without
# routing through the Pydantic schema, tests, fixtures, seed data, and
# any future code path that bypasses the router. Both insert and update
# paths are hooked.
#
# Limitations (known and documented):
#   * Only fires on ORM-mediated writes. Raw SQL issued via
#     `AsyncSession.execute(insert(TimeEntryModel.__table__)...)` or
#     directly through a DBAPI cursor will NOT trigger this listener —
#     SQLAlchemy's mapper events are an ORM-level mechanism. Raw-SQL
#     writes must be separately covered by the DB-level constraint or
#     a CI lint; see the audit script at
#     `scripts/audit_time_entry_metadata.py` for the compensating
#     control during rollout.
#   * `AsyncSession.execute(update(TimeEntryModel)...)` likewise
#     bypasses the mapper hook. The existing service code uses that
#     pattern (see `TimeTrackingService.update_time_entry`) — the
#     Pydantic layer catches the payload before it reaches there, so
#     the two layers together cover the update path.
#
# Not swallowed: a `ValidationError` here propagates out of the
# flush/commit and aborts the transaction. That is the desired
# behaviour — fail loudly on schema violation rather than silently
# writing PII.

from goldsmith_erp.models.time_entry_metadata import TimeEntryMetadata  # noqa: E402


@event.listens_for(TimeEntry, "before_insert")
@event.listens_for(TimeEntry, "before_update")
def _validate_time_entry_metadata(mapper, connection, target) -> None:
    """Validate ``target.extra_metadata`` against the whitelist schema.

    Runs on every ORM insert / update of a ``TimeEntry`` row before
    the statement is sent to the database. ``None`` and empty-dict
    payloads are accepted (there is nothing to scrub).
    """
    metadata = target.extra_metadata
    if metadata is None or metadata == {}:
        return
    # Raises ValidationError — do not swallow; we want the transaction
    # to fail so the caller sees the schema violation.
    TimeEntryMetadata.model_validate(metadata)


class Interruption(Base):
    """Unterbrechungen während der Arbeit"""

    __tablename__ = "interruptions"

    id = Column(Integer, primary_key=True, index=True)
    time_entry_id = Column(
        String(36),
        ForeignKey("time_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason = Column(String(100), nullable=False)  # customer_call, material_fetch, etc.
    duration_minutes = Column(Integer, nullable=False)
    timestamp = Column(UtcDateTime, default=utcnow)
    # W2-14 / BE-19: set when work resumes; duration_minutes then holds the
    # measured minutes. NULL with duration 0 = still open. Migration
    # 20260925_w214_interrupt_resume.
    resumed_at = Column(UtcDateTime, nullable=True)

    # Beziehungen
    time_entry = relationship("TimeEntry", back_populates="interruptions")


class LocationHistory(Base):
    """Lagerort-Verlauf für Aufträge"""

    __tablename__ = "location_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    location = Column(String(50), nullable=False)
    timestamp = Column(UtcDateTime, default=utcnow, index=True)
    changed_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Beziehungen
    order = relationship("Order")
    user = relationship("User")


# ============================================================================
# V1.3 ESTIMATOR — ESTIMATE ACCURACY / CALIBRATION
# ============================================================================


class EstimateAccuracy(Base):
    """Estimate-vs-actual record — the statistical labor estimator's learning
    loop feedback (V1.3 Phase 1, Task 4).

    Written when a completed order had a prior STORED estimate. Estimate
    storage itself (where on `Order`/`Quote` a prior estimate lives) is
    Task 5's job (`EstimatorService` + endpoints) — this table and
    `EstimateAccuracyService.record()` are estimate-source-agnostic: they
    persist whatever estimated/actual values the caller supplies. Until
    Task 5 wires a real stored estimate, the `OrderService.update_order`
    completion hook calls `EstimateAccuracyService.safe_record_on_completion`
    with no values, which is a documented, tested no-op (see that method's
    docstring and `services/estimate_accuracy_service.py`).

    `estimator_version` lets calibration be sliced by estimator revision if
    the median/P20/P80 logic changes later without conflating old and new
    accuracy numbers.

    Financial data (estimated/actual hours feed a labor cost) — ADMIN/
    GOLDSMITH visibility only, audit-logged reads (CLAUDE.md: "All
    financial data access MUST be audit-logged"). No API surface in this
    task; Task 5 adds `GET /estimates/accuracy` + its `_RESOURCE_ROUTES`
    entry in `middleware/audit_logging.py`.

    FK deletion semantics: `order_id` uses `ondelete="RESTRICT"` — an
    accuracy row is Art. 30-relevant calibration evidence tied to one
    specific completed order, so (matching `CostChangeRequest.order_id` /
    `Invoice.order_id`) a hard delete of the order must not silently
    orphan or cascade away this financial record.
    """

    __tablename__ = "estimate_accuracy"

    id = Column(Integer, primary_key=True, index=True)
    # RESTRICT, not CASCADE/SET NULL — financial-retention backstop, see
    # docstring (same rationale as CostChangeRequest.order_id).
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    estimated_hours = Column(Float, nullable=False)
    actual_hours = Column(Float, nullable=False)
    estimated_total = Column(MONEY_NUMERIC, nullable=False)
    actual_total = Column(MONEY_NUMERIC, nullable=False)

    # Free-form tag identifying which estimator revision produced the
    # estimate (e.g. "labor_estimator_v1") — lets calibration slice by
    # revision once the median/tier logic changes. Not an enum: this is
    # meant to be bumped freely as the estimator evolves, without a schema
    # migration each time (mirrors Activity.category's free-text choice).
    estimator_version = Column(String(50), nullable=False)

    created_at = Column(
        UtcDateTime, server_default=func.now(), nullable=False, index=True
    )

    # One-directional — no back_populates on Order, matching the
    # CostChangeRequest / CustomerUpdate precedent (no existing need to
    # traverse Order -> its accuracy rows from the ORM side).
    order = relationship("Order")

    def __repr__(self) -> str:
        return (
            f"<EstimateAccuracy {self.id} order={self.order_id} "
            f"estimated_hours={self.estimated_hours} "
            f"actual_hours={self.actual_hours}>"
        )


# ============================================================================
# PERFORMANCE INDEXES
# ============================================================================

# Performance indexes for frequent query patterns
Index("ix_time_entries_end_time", TimeEntry.end_time)

# Slice 2 — security floor + audit indexes. Names match the Alembic
# migration (20260419_security_floor) so both create_all() and
# `alembic upgrade head` produce identical index shapes.
#
# Composite index for the 30-day scan-adoption metric query (Lena §1).
Index(
    "idx_time_entries_origin_created_at",
    TimeEntry.origin,
    TimeEntry.created_at,
)
# Partial on PG / plain on SQLite — the migration emits the WHERE clause
# conditionally, and create_all honours the kwargs below on PG only.
Index(
    "idx_time_entries_correction_of",
    TimeEntry.correction_of,
    postgresql_where=TimeEntry.correction_of.isnot(None),
)
Index("idx_time_entries_retention_class", TimeEntry.retention_class)
