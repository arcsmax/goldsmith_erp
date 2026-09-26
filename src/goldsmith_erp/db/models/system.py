"""Calendar, barcode aliases, scan logs and label templates."""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import Base, SAEnum
from goldsmith_erp.db.types import UtcDateTime, UtcDateTimeNaiveStorage


class CalendarEventType(str, enum.Enum):
    """Event types for the calendar/planning system."""

    ORDER_DEADLINE = "order_deadline"
    WORKSHOP_TASK = "workshop_task"
    APPOINTMENT = "appointment"
    REMINDER = "reminder"


class CalendarEvent(Base):
    """
    Calendar events for workshop planning.

    Covers manual events (appointments, reminders, tasks) as well as
    system-generated entries (order_deadline type is created on-the-fly from
    Order.deadline and is NOT stored here — use CalendarService.get_order_deadlines
    for those).
    """

    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(
        SAEnum(CalendarEventType),
        nullable=False,
        default=CalendarEventType.WORKSHOP_TASK,
        index=True,
    )

    # Time range
    start_datetime = Column(UtcDateTime, nullable=False, index=True)
    end_datetime = Column(UtcDateTime, nullable=True)
    all_day = Column(Boolean, default=False, nullable=False)

    # Optional link to an order
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Owner / creator
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Visual styling
    color = Column(String(7), nullable=True)  # Hex color, e.g. "#FF6B6B"

    # Simple recurrence note (free-text, not a full RFC 5545 implementation)
    recurrence = Column(String(100), nullable=True)  # e.g. "weekly", "monthly"

    # Metadata
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    updated_at = Column(
        UtcDateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # Relationships
    order = relationship("Order")
    user = relationship("User")


# ============================================================================
# QR / BARCODE WORKFLOW MODELS (V1.1 — Slice 1)
# ============================================================================
# The three tables below are created by Alembic migration
# `20260418_qr_core` (Slice 1). The ORM classes exist so the service layer
# and tests can query them via SQLAlchemy, BUT the partitioning of
# `scan_logs` is a PostgreSQL feature that lives at the DDL level and is
# not expressed by SQLAlchemy; the ORM treats it as a plain table.
#
# FK semantics: `scan_logs.user_id`, `barcode_aliases.created_by` and
# `label_templates.created_by` all use `ON DELETE RESTRICT` at the DB
# level. Hard-deleting a user who created any of these rows is blocked;
# anonymisation is required via `UserService.anonymize_user` (registered
# in `ANONYMIZABLE_FK_TARGETS`).


class BarcodeAlias(Base):
    """Lookup from a scanned external code (QR or barcode) to an ERP entity.

    Populated at label-print time and on first-scan of an unknown external
    code (e.g. supplier barcodes). One entry per external code; the same
    ERP entity may have many aliases (order qr + metal-lot barcode + etc).
    """

    __tablename__ = "barcode_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_code = Column(String(500), nullable=False, unique=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    label = Column(String(200), nullable=True)
    supplier_lot = Column(String(100), nullable=True)
    supplier_cert = Column(String(200), nullable=True)
    # Forward-compat: `suppliers` table is introduced in V1.2. The FK will
    # be added then; today the column stands alone. See migration docstring.
    supplier_id = Column(Integer, nullable=True)
    created_by = Column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_barcode_aliases_created_by_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    last_scanned_at = Column(UtcDateTime, nullable=True)
    scan_count = Column(Integer, default=0, nullable=False)

    creator = relationship("User", foreign_keys=[created_by])


class ScanLog(Base):
    """Append-only audit / analytics log for every scan event.

    Partitioned by `scanned_at` (monthly) on PostgreSQL. The composite PK
    `(id, scanned_at)` is REQUIRED by RANGE partitioning — the partition
    key must appear in every unique/primary-key constraint on a
    partitioned table. SQLAlchemy uses the ORM-level PK for INSERTs and
    does not emit the PostgreSQL `PARTITION BY` clause; that is handled
    entirely by the migration.
    """

    __tablename__ = "scan_logs"

    # Stored as TEXT (36 chars) on SQLite and as UUID on PostgreSQL. Using
    # String(36) at the ORM level keeps the type portable; the migration
    # upgrades the column to native UUID on PG.
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )
    # Stays TIMESTAMP WITHOUT TIME ZONE in PostgreSQL: it is the RANGE
    # partition key and a partition key column cannot change type. The
    # type still stores naive UTC and hands back aware UTC (BE-15).
    scanned_at = Column(UtcDateTimeNaiveStorage, primary_key=True, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_scan_logs_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    raw_payload = Column(String(500), nullable=False)
    resolved_type = Column(String(50), nullable=True)
    resolved_id = Column(String(100), nullable=True)
    resolution_path = Column(String(20), nullable=True)
    action_taken = Column(String(50), nullable=True)
    context = Column(JSON, nullable=True)
    offline_queued = Column(Boolean, default=False, nullable=False)
    synced_at = Column(UtcDateTime, nullable=True)
    idempotency_key = Column(String(36), nullable=True)
    # A1.2 — client-side FAB tap timestamp for adoption metrics.
    client_tap_at = Column(UtcDateTime, nullable=True)
    # A1.3 — server-side resolution completion, pairs with client_tap_at.
    server_resolved_at = Column(UtcDateTime, nullable=True)
    # A1.4 — camera-denied / manual-fallback tracking.
    fallback_reason = Column(String(40), nullable=True)
    # A1.6 — retention bucket for future retention-engine.
    retention_class = Column(String(32), nullable=False, default="standard_24m")
    # SC-04 (follow-up) — configured workshop location (W8
    # ``workshop_locations``), promoted out of ``context`` JSON into a real,
    # indexed FK column. Migration: 20260926_sc04_scan_log_location.
    # Unknown/deactivated ids are never stored (scanner_service resolves and
    # drops them before the row is built), so this FK is never violated by
    # application writes.
    location_id = Column(
        Integer,
        ForeignKey(
            "workshop_locations.id",
            name="fk_scan_logs_location_id_workshop_locations",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    user = relationship("User", foreign_keys=[user_id])


class LabelTemplate(Base):
    """Printable label layout definition.

    The `fields` JSON column carries the per-template layout; the 7
    system-default rows are seeded by the Slice 1 migration with
    `is_system_default=TRUE` and may NOT be overwritten by re-running
    the seed. Admin-edited copies have `is_system_default=FALSE` and are
    preserved across re-seeding via `ON CONFLICT (entity_type, name) DO
    NOTHING`.
    """

    __tablename__ = "label_templates"
    __table_args__ = (
        UniqueConstraint("entity_type", "name", name="uq_label_templates_entity_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    width_mm = Column(Integer, default=89, nullable=False)
    height_mm = Column(Integer, default=36, nullable=False)
    fields = Column(JSON, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    is_system_default = Column(Boolean, default=False, nullable=False)
    created_by = Column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_label_templates_created_by_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    updated_at = Column(
        UtcDateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    creator = relationship("User", foreign_keys=[created_by])


# Slice 1 — QR / barcode workflow indexes.
# Named identically to the Alembic migration indexes so that CREATE INDEX
# from `Base.metadata.create_all()` (used by the test conftest) produces
# the same DB shape as `alembic upgrade head`.
Index("idx_alias_external_code", BarcodeAlias.external_code)
Index(
    "idx_alias_entity",
    BarcodeAlias.entity_type,
    BarcodeAlias.entity_id,
)
Index("idx_scan_user_date", ScanLog.user_id, ScanLog.scanned_at)
Index("idx_scan_entity", ScanLog.resolved_type, ScanLog.resolved_id)
Index(
    "idx_scan_idem",
    ScanLog.idempotency_key,
    unique=True,
    sqlite_where=ScanLog.idempotency_key.isnot(None),
    postgresql_where=ScanLog.idempotency_key.isnot(None),
)
Index("idx_template_entity_type", LabelTemplate.entity_type)
