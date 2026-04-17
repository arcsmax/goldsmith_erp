"""add QR / barcode core tables (Slice 1 — Migration 1)

Creates the three new tables introduced by the V1.1 QR / barcode workflow
and seeds the 7 system-default label templates:

  * ``barcode_aliases``   — lookup from scanned external code → ERP entity.
  * ``scan_logs``         — append-only audit / analytics log, RANGE-
                            partitioned by ``scanned_at`` (monthly, 13
                            partitions covering 2026-04 through 2027-04
                            plus a default partition for out-of-range rows).
  * ``label_templates``   — printable label definitions; 7 rows seeded with
                            ``is_system_default=TRUE`` per spec §9.c.

Amendments applied from V1.1-AMENDMENTS.md (§Slice 1):

  * A1.1 — ``barcode_aliases.supplier_id INTEGER NULL``
  * A1.2 — ``scan_logs.client_tap_at TIMESTAMPTZ NULL``
  * A1.3 — ``scan_logs.server_resolved_at TIMESTAMPTZ NULL``
  * A1.4 — ``scan_logs.fallback_reason VARCHAR(40) NULL``
  * A1.6 — ``scan_logs.retention_class VARCHAR(32) DEFAULT 'standard_24m'``

FK hardening (Anna B2 / Slice 0 anonymisation contract):

  * ``scan_logs.user_id``, ``barcode_aliases.created_by``,
    ``label_templates.created_by`` are all created with
    ``ON DELETE RESTRICT``. Hard deletes of a user who authored any of
    these rows are therefore impossible; anonymisation must go through
    ``UserService.anonymize_user`` (registered in ``ANONYMIZABLE_FK_TARGETS``).

Deviation from the spec — ``barcode_aliases.supplier_id`` FK:

  The spec (§9.a) and A1.1 call for ``REFERENCES suppliers(id) ON DELETE
  SET NULL``. The ``suppliers`` table does NOT yet exist in the V1.1
  schema (it is planned for V1.2). Rather than introduce an orphan FK
  constraint we declare ``supplier_id INTEGER NULL`` WITHOUT the foreign
  key constraint in this migration; the FK will be added by the V1.2
  migration that creates ``suppliers``. The column itself is in place now
  so the future backfill is a no-op. See the Slice 1 report for the
  flag raised to Max.

SQLite fallback:

  PostgreSQL RANGE partitioning is not supported by SQLite (used by the
  unit-test suite via ``conftest.py``). When the migration runs against a
  SQLite dialect it falls back to a plain, non-partitioned ``scan_logs``
  table with identical columns, identical indexes, and a single-column
  primary key on ``id`` (composite PK is not required without
  partitioning). The production PostgreSQL path is the authoritative
  schema.

Revision ID: 20260418_qr_core
Revises: 20260417_anonymize_user
Create Date: 2026-04-18
"""

from __future__ import annotations

import json
from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from goldsmith_erp.db.migration_helpers import (
    create_index_if_not_exists,
    create_table_if_not_exists,
)

# revision identifiers, used by Alembic.
revision: str = "20260418_qr_core"
down_revision: Union[str, None] = "20260417_anonymize_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Partition window — current month (2026-04) through 2027-04 inclusive.
# 13 month partitions + 1 default partition. A rolling cron job (scheduled
# post-ship, out of scope for this migration) will add future months.
# ---------------------------------------------------------------------------
_PARTITION_MONTHS: list[tuple[int, int]] = [
    (2026, 4),
    (2026, 5),
    (2026, 6),
    (2026, 7),
    (2026, 8),
    (2026, 9),
    (2026, 10),
    (2026, 11),
    (2026, 12),
    (2027, 1),
    (2027, 2),
    (2027, 3),
    (2027, 4),
]


def _partition_bounds(year: int, month: int) -> tuple[str, str, str]:
    """Return (partition_name, lower_bound, upper_bound) for a month."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    name = f"scan_logs_{year:04d}_{month:02d}"
    return name, start.isoformat(), end.isoformat()


# ---------------------------------------------------------------------------
# Default label templates — 7 rows seeded with is_system_default=TRUE.
# `fields` is JSONB describing the label layout. We keep the payloads minimal
# and focused on what the spec §9.c documents as the fields that must render.
# Frontends are free to render additional fields; the seed is the floor.
# ---------------------------------------------------------------------------
_SEED_TEMPLATES: list[dict] = [
    {
        "entity_type": "order",
        "name": "Standard Auftragsetikett",
        "width_mm": 89,
        "height_mm": 36,
        "fields": {
            "lines": [
                {"field": "order_code", "font_size": 14, "bold": True},
                {"field": "title", "max_chars": 40},
                {"field": "customer_short"},
                {"field": "due_date"},
                {"field": "qr_code", "size_mm": 18, "position": "right"},
            ]
        },
    },
    {
        "entity_type": "repair",
        "name": "Standard Reparaturetikett",
        "width_mm": 89,
        "height_mm": 36,
        "fields": {
            "lines": [
                {"field": "bag_number", "font_size": 14, "bold": True},
                {"field": "item_type"},
                {"field": "customer_short"},
                {"field": "received_at"},
                {"field": "qr_code", "size_mm": 18, "position": "right"},
            ]
        },
    },
    {
        "entity_type": "metal",
        "name": "Metallchargen-Etikett",
        "width_mm": 89,
        "height_mm": 36,
        "fields": {
            "lines": [
                {"field": "alloy_name", "font_size": 14, "bold": True},
                {"field": "lot_number"},
                {"field": "supplier_lot"},
                {"field": "weight_g"},
                {"field": "qr_code", "size_mm": 18, "position": "right"},
            ]
        },
    },
    {
        "entity_type": "material",
        "name": "Material-Etikett",
        "width_mm": 62,
        "height_mm": 29,
        "fields": {
            "lines": [
                {"field": "name", "font_size": 12, "bold": True},
                {"field": "unit"},
                {"field": "qr_code", "size_mm": 14, "position": "right"},
            ]
        },
    },
    {
        "entity_type": "gemstone",
        "name": "Edelstein-Etikett",
        "width_mm": 25,
        "height_mm": 10,
        "fields": {
            "lines": [
                {"field": "stone_type", "font_size": 6, "bold": True},
                {"field": "carat"},
                {"field": "qr_code", "size_mm": 6, "position": "right"},
            ]
        },
    },
    {
        "entity_type": "scrap",
        "name": "Altgold-Etikett",
        "width_mm": 89,
        "height_mm": 36,
        "fields": {
            "lines": [
                {"field": "batch_number", "font_size": 14, "bold": True},
                {"field": "customer_short"},
                {"field": "received_at"},
                {"field": "fine_weight_g"},
                {"field": "qr_code", "size_mm": 18, "position": "right"},
            ]
        },
    },
    {
        "entity_type": "station",
        "name": "Stations-Etikett",
        "width_mm": 89,
        "height_mm": 36,
        "fields": {
            "lines": [
                {"field": "station_code", "font_size": 18, "bold": True},
                {"field": "station_name"},
                {"field": "qr_code", "size_mm": 20, "position": "right"},
            ]
        },
    },
]


# ---------------------------------------------------------------------------
# upgrade()
# ---------------------------------------------------------------------------


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # -------------------------------------------------------------------
    # 1. barcode_aliases — straightforward, same on every dialect.
    # -------------------------------------------------------------------
    # NOTE on supplier_id: the `suppliers` table does not yet exist (V1.2).
    # We declare the column WITHOUT a FK constraint; V1.2 migration will
    # add the FK when the table is introduced. Using a named FK constraint
    # name upfront would still not create the constraint because the
    # referenced table is missing — the cheap forward-compat move is the
    # column alone.
    create_table_if_not_exists(
        "barcode_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "external_code",
            sa.String(length=500),
            nullable=False,
            unique=True,
        ),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("supplier_lot", sa.String(length=100), nullable=True),
        sa.Column("supplier_cert", sa.String(length=200), nullable=True),
        # A1.1 — forward-compat column. FK constraint added in V1.2 when
        # `suppliers` table is created.
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                name="fk_barcode_aliases_created_by_users",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_scanned_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "scan_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    create_index_if_not_exists(
        "idx_alias_external_code",
        "barcode_aliases",
        ["external_code"],
    )
    create_index_if_not_exists(
        "idx_alias_entity",
        "barcode_aliases",
        ["entity_type", "entity_id"],
    )

    # -------------------------------------------------------------------
    # 2. scan_logs — partitioned on PostgreSQL, plain table on SQLite.
    #
    # The columns are identical across dialects so the ORM can target
    # either. The primary key is composite (id, scanned_at) on PostgreSQL
    # because RANGE partitioning requires the partition key to appear in
    # any unique/primary-key constraint. On SQLite we keep a single-column
    # PK on `id` to avoid the usual "PK first column must be INTEGER for
    # autoincrement" surprises while still allowing the ORM model to
    # declare a composite PK (SQLAlchemy uses the ORM-level PK at insert
    # time, not the DB-level one).
    # -------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        op.execute(
            """
            CREATE TABLE scan_logs (
                id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
                scanned_at          TIMESTAMP   NOT NULL,
                user_id             INTEGER     NOT NULL,
                raw_payload         VARCHAR(500) NOT NULL,
                resolved_type       VARCHAR(50),
                resolved_id         VARCHAR(100),
                resolution_path     VARCHAR(20),
                action_taken        VARCHAR(50),
                context             JSONB,
                offline_queued      BOOLEAN     NOT NULL DEFAULT FALSE,
                synced_at           TIMESTAMP,
                idempotency_key     UUID,
                client_tap_at       TIMESTAMPTZ,
                server_resolved_at  TIMESTAMPTZ,
                fallback_reason     VARCHAR(40),
                retention_class     VARCHAR(32) NOT NULL DEFAULT 'standard_24m',
                CONSTRAINT pk_scan_logs PRIMARY KEY (id, scanned_at),
                CONSTRAINT fk_scan_logs_user_id_users
                    FOREIGN KEY (user_id) REFERENCES users (id)
                    ON DELETE RESTRICT
            ) PARTITION BY RANGE (scanned_at)
            """
        )

        # Month partitions — 2026-04 … 2027-04 inclusive.
        for year, month in _PARTITION_MONTHS:
            name, lower, upper = _partition_bounds(year, month)
            op.execute(
                f"""
                CREATE TABLE {name} PARTITION OF scan_logs
                FOR VALUES FROM ('{lower}') TO ('{upper}')
                """
            )

        # Default partition for stray timestamps outside the window.
        op.execute(
            "CREATE TABLE scan_logs_default PARTITION OF scan_logs DEFAULT"
        )

        # Indexes on the partitioned parent — PostgreSQL propagates them.
        op.execute(
            "CREATE INDEX idx_scan_user_date ON scan_logs (user_id, scanned_at)"
        )
        op.execute(
            "CREATE INDEX idx_scan_entity ON scan_logs (resolved_type, resolved_id)"
        )
        # Idempotency-key lookup index.
        # Design note: PostgreSQL forbids a UNIQUE index on a partitioned
        # table unless the partition key (scanned_at) is included — but
        # including scanned_at defeats idempotency semantics (two scans
        # with the same key at different times would both be allowed).
        # Resolution: application-layer dedupe is the source of truth
        # (scanner_service.log_scan does SELECT-by-key first, returns the
        # existing row for replays). This partial index serves lookup
        # performance only, NOT uniqueness — the service is responsible
        # for the dedupe contract.
        op.execute(
            """
            CREATE INDEX idx_scan_idem ON scan_logs (idempotency_key)
            WHERE idempotency_key IS NOT NULL
            """
        )
    else:
        # SQLite fallback — non-partitioned, same columns. UUIDs as TEXT.
        create_table_if_not_exists(
            "scan_logs",
            sa.Column(
                "id",
                sa.String(length=36),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("scanned_at", sa.DateTime(timezone=False), nullable=False),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey(
                    "users.id",
                    name="fk_scan_logs_user_id_users",
                    ondelete="RESTRICT",
                ),
                nullable=False,
            ),
            sa.Column("raw_payload", sa.String(length=500), nullable=False),
            sa.Column("resolved_type", sa.String(length=50), nullable=True),
            sa.Column("resolved_id", sa.String(length=100), nullable=True),
            sa.Column("resolution_path", sa.String(length=20), nullable=True),
            sa.Column("action_taken", sa.String(length=50), nullable=True),
            sa.Column("context", sa.JSON(), nullable=True),
            sa.Column(
                "offline_queued",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("synced_at", sa.DateTime(timezone=False), nullable=True),
            sa.Column("idempotency_key", sa.String(length=36), nullable=True),
            sa.Column("client_tap_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "server_resolved_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column("fallback_reason", sa.String(length=40), nullable=True),
            sa.Column(
                "retention_class",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'standard_24m'"),
            ),
        )
        create_index_if_not_exists(
            "idx_scan_user_date", "scan_logs", ["user_id", "scanned_at"]
        )
        create_index_if_not_exists(
            "idx_scan_entity", "scan_logs", ["resolved_type", "resolved_id"]
        )
        # Partial unique index — SQLite supports WHERE clauses on indexes.
        create_index_if_not_exists(
            "idx_scan_idem",
            "scan_logs",
            ["idempotency_key"],
            unique=True,
            sqlite_where=sa.text("idempotency_key IS NOT NULL"),
        )

    # -------------------------------------------------------------------
    # 3. label_templates — same shape on every dialect.
    # -------------------------------------------------------------------
    create_table_if_not_exists(
        "label_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "width_mm",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("89"),
        ),
        sa.Column(
            "height_mm",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("36"),
        ),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_system_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                name="fk_label_templates_created_by_users",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "entity_type", "name", name="uq_label_templates_entity_name"
        ),
    )
    create_index_if_not_exists(
        "idx_template_entity_type", "label_templates", ["entity_type"]
    )

    # -------------------------------------------------------------------
    # 4. Seed the 7 system-default templates. Idempotent via ON CONFLICT
    #    (PostgreSQL) / INSERT OR IGNORE (SQLite).
    # -------------------------------------------------------------------
    for tpl in _SEED_TEMPLATES:
        fields_payload = json.dumps(tpl["fields"])

        if dialect == "postgresql":
            bind.execute(
                sa.text(
                    """
                    INSERT INTO label_templates (
                        entity_type, name, width_mm, height_mm,
                        fields, is_default, is_system_default,
                        created_by, created_at, updated_at
                    ) VALUES (
                        :entity_type, :name, :width_mm, :height_mm,
                        CAST(:fields AS jsonb), FALSE, TRUE,
                        NULL, NOW(), NOW()
                    )
                    ON CONFLICT (entity_type, name) DO NOTHING
                    """
                ),
                {
                    "entity_type": tpl["entity_type"],
                    "name": tpl["name"],
                    "width_mm": tpl["width_mm"],
                    "height_mm": tpl["height_mm"],
                    "fields": fields_payload,
                },
            )
        else:
            bind.execute(
                sa.text(
                    """
                    INSERT OR IGNORE INTO label_templates (
                        entity_type, name, width_mm, height_mm,
                        fields, is_default, is_system_default,
                        created_by, created_at, updated_at
                    ) VALUES (
                        :entity_type, :name, :width_mm, :height_mm,
                        :fields, 0, 1,
                        NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "entity_type": tpl["entity_type"],
                    "name": tpl["name"],
                    "width_mm": tpl["width_mm"],
                    "height_mm": tpl["height_mm"],
                    "fields": fields_payload,
                },
            )


# ---------------------------------------------------------------------------
# downgrade() — drop partitions first, then parent, then the other tables.
# Reversible. No data migration to undo.
# ---------------------------------------------------------------------------


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # label_templates — indexes first, then table.
    op.drop_index("idx_template_entity_type", table_name="label_templates")
    op.drop_table("label_templates")

    # scan_logs — partitions first on PostgreSQL; plain drop on SQLite.
    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_scan_idem")
        op.execute("DROP INDEX IF EXISTS idx_scan_entity")
        op.execute("DROP INDEX IF EXISTS idx_scan_user_date")
        op.execute("DROP TABLE IF EXISTS scan_logs_default")
        for year, month in _PARTITION_MONTHS:
            name, _, _ = _partition_bounds(year, month)
            op.execute(f"DROP TABLE IF EXISTS {name}")
        op.execute("DROP TABLE IF EXISTS scan_logs")
    else:
        op.drop_index("idx_scan_idem", table_name="scan_logs")
        op.drop_index("idx_scan_entity", table_name="scan_logs")
        op.drop_index("idx_scan_user_date", table_name="scan_logs")
        op.drop_table("scan_logs")

    # barcode_aliases.
    op.drop_index("idx_alias_entity", table_name="barcode_aliases")
    op.drop_index("idx_alias_external_code", table_name="barcode_aliases")
    op.drop_table("barcode_aliases")
