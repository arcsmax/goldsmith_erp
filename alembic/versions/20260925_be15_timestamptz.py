"""BE-15: every naive TIMESTAMP column becomes TIMESTAMP WITH TIME ZONE.

The stored values are UTC (the application always wrote ``utcnow()``), so
PostgreSQL converts in place with ``USING col AT TIME ZONE 'UTC'`` (read the
naive value as UTC). The downgrade uses the same expression on the aware
column, which yields the naive UTC wall time again; the round trip is
lossless. See docs/architecture/ADR-2026-09-25-numeric-and-tz.md.

Not converted:

* the three columns that were already ``timestamptz``
  (``orders.punzierung_verified_at``, ``scan_logs.client_tap_at``,
  ``scan_logs.server_resolved_at``);
* ``scan_logs.scanned_at``: it is the RANGE partition key and PostgreSQL
  cannot change the type of a partition key column. It keeps naive UTC in
  the DB; ``UtcDateTime(timezone=False)`` returns it as aware UTC.

``scan_logs`` is partitioned: ALTER on the parent propagates to every
partition. SQLite (tests) has no time zone type; batch mode rewrites the
tables so the declared type matches, the stored strings stay naive UTC.

Revision ID: 20260925_be15_tz
Revises: 20260925_be14_numeric
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_be15_tz"
down_revision: Union[str, None] = "20260925_be14_numeric"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS: dict[str, tuple[str, ...]] = {
    "activities": (
        "last_used",
        "created_at",
    ),
    "barcode_aliases": (
        "created_at",
        "last_scanned_at",
    ),
    "calendar_events": (
        "start_datetime",
        "end_datetime",
        "created_at",
        "updated_at",
    ),
    "consultation_photos": ("timestamp",),
    "consultations": (
        "follow_up_at",
        "created_at",
        "updated_at",
    ),
    "cost_change_requests": (
        "responded_at",
        "created_at",
        "updated_at",
    ),
    "custom_metal_types": (
        "created_at",
        "updated_at",
    ),
    "customer_audit_logs": (
        "timestamp",
        "created_at",
    ),
    "customer_consents": (
        "granted_at",
        "revoked_at",
        "created_at",
    ),
    "customer_measurements": (
        "measured_at",
        "created_at",
        "updated_at",
    ),
    "customer_no_gos": ("created_at",),
    "customer_updates": (
        "sent_at",
        "created_at",
        "updated_at",
    ),
    "customers": (
        "birthday",
        "created_at",
        "updated_at",
        "deletion_scheduled_at",
        "retention_hold_until",
        "deleted_at",
    ),
    "estimate_accuracy": ("created_at",),
    "gdpr_requests": (
        "requested_at",
        "completed_at",
    ),
    "interruptions": (
        "timestamp",
        "resumed_at",
    ),
    "inventory_adjustments": ("adjusted_at",),
    "invoices": (
        "issue_date",
        "due_date",
        "paid_date",
        "service_date",
        "issued_at",
        "created_at",
        "updated_at",
    ),
    "label_templates": (
        "created_at",
        "updated_at",
    ),
    "location_history": ("timestamp",),
    "material_usage": (
        "used_at",
        "created_at",
    ),
    "metal_price_history": ("fetched_at",),
    "metal_purchases": (
        "date_purchased",
        "created_at",
        "updated_at",
    ),
    "notifications": (
        "read_at",
        "created_at",
    ),
    "order_comments": (
        "created_at",
        "updated_at",
    ),
    "order_events": ("created_at",),
    "order_hallmarks": (
        "submitted_at",
        "approved_at",
        "stamped_at",
        "created_at",
    ),
    "order_handoffs": (
        "created_at",
        "responded_at",
    ),
    "order_items": ("created_at",),
    "order_photos": ("timestamp",),
    "order_status_history": ("changed_at",),
    "orders": (
        "deadline",
        "completed_at",
        "fitting_date",
        "deleted_at",
        "created_at",
        "updated_at",
    ),
    "outbox_messages": (
        "next_attempt_at",
        "created_at",
        "sent_at",
    ),
    "quotes": (
        "valid_until",
        "approved_at",
        "rejected_at",
        "converted_at",
        "created_at",
        "updated_at",
    ),
    "repair_jobs": (
        "estimated_completion_date",
        "actual_completion_date",
        "customer_notified_at",
        "picked_up_at",
        "deleted_at",
        "created_at",
        "updated_at",
    ),
    "repair_photos": ("timestamp",),
    "scan_logs": ("synced_at",),
    "scrap_gold": (
        "signed_at",
        "created_at",
        "updated_at",
        "id_checked_at",
    ),
    "scrap_gold_items": ("created_at",),
    "time_entries": (
        "start_time",
        "end_time",
        "created_at",
    ),
    "users": (
        "created_at",
        "deleted_at",
    ),
    "valuation_certificates": (
        "valuation_date",
        "valid_until",
        "created_at",
        "updated_at",
    ),
    "workshop_settings": ("updated_at",),
}


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _convert(to_aware: bool) -> None:
    dialect = op.get_bind().dialect.name
    old_type = sa.DateTime(timezone=not to_aware)
    new_type = sa.DateTime(timezone=to_aware)
    for table, columns in COLUMNS.items():
        present = _existing_columns(table)
        missing = [name for name in columns if name not in present]
        if missing:
            raise RuntimeError(
                f"BE-15 migration: {table} is missing {missing}; the schema has "
                "drifted from the model, fix that before converting."
            )
        if dialect == "postgresql":
            for name in columns:
                op.alter_column(
                    table,
                    name,
                    existing_type=old_type,
                    type_=new_type,
                    postgresql_using=f"{name} AT TIME ZONE 'UTC'",
                )
            continue
        with op.batch_alter_table(table) as batch:
            for name in columns:
                batch.alter_column(name, existing_type=old_type, type_=new_type)


def upgrade() -> None:
    _convert(to_aware=True)


def downgrade() -> None:
    _convert(to_aware=False)
