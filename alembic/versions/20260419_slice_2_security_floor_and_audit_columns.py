"""Slice 2 — Security floor + audit columns (Migration 2)

Adds the columns every subsequent V1.1 slice depends on:

  * ``orders`` — ``punzierung_verified_at``, ``punzierung_verified_by``,
    ``punzierung_verified_marks`` (JSONB), ``retention_class``.
  * ``material_usage`` — ``alloy_override``, ``override_reason``,
    ``override_reason_category``, ``retention_class``, ``user_id``.
  * ``time_entries`` — ``origin`` (back-populated), ``correction_of``,
    ``retention_class``.
  * ``users`` — ``is_test_user``.

Scope is defined by V1.1-AMENDMENTS.md §Slice 2 (A2.1–A2.8) and V1.1-
PRIORITY-REVIEW.md M1, M2, M6, R5. The goal is a security / observability
floor — no business logic yet. Slices 3 – 13 rely on these columns;
breaking any of them later requires data-path rework.

Hardening invariants applied here:

  * Every new FK to ``users(id)`` is declared ``ON DELETE RESTRICT``.
    The only path to removing a user that references any of these rows
    is ``UserService.anonymize_user`` (which rewrites the FK to the
    sentinel per ``ANONYMIZABLE_FK_TARGETS``).
  * ``orders.punzierung_verified_marks`` uses JSONB on PostgreSQL with a
    server-side ``'[]'::jsonb`` default so concurrent writers cannot
    observe a NULL marks column during the transition window. SQLite
    falls back to a plain ``JSON`` column with a string ``'[]'`` default.
  * ``time_entries.origin`` is back-populated to ``'manual'`` for every
    existing row — the 30-day adoption metric (Lena §1) divides on this
    column and cannot tolerate NULLs.
  * ``material_usage.override_reason`` is DB-nullable. The 3–200-char
    freetext constraint and the mandatory pairing with
    ``override_reason_category`` are enforced at the Pydantic layer
    (service-level validators in Slice 3 / 5). Keeping them
    nullable at the DB level lets pre-Slice-2 rows continue to load.
  * ``orders.retention_class`` default is ``'indefinite_business'``;
    ``material_usage.retention_class`` and ``time_entries.retention_class``
    default to ``'financial_10y'`` per HGB §257 (A2.7).

Indexes created for read-path performance (R5 / metric queries):

  * ``idx_time_entries_origin_created_at`` — 30-day scan-adoption metric.
  * ``idx_time_entries_correction_of`` (partial, WHERE correction_of IS
    NOT NULL) — the corrected-entry exclusion in the adoption query.
  * ``idx_orders_punzierung_verified_at`` (partial) — "which orders are
    verified" queries for the QC dashboard.
  * ``idx_users_is_test_user`` (partial, WHERE is_test_user = TRUE) —
    tiny selective index used by every metric query.
  * ``idx_orders_retention_class`` / ``idx_material_usage_retention_class``
    / ``idx_time_entries_retention_class`` — future retention-engine.

Per-table ``updated_at`` audit (A2.6 — verify, don't blindly amend)
------------------------------------------------------------------

Each of the seven tables the plan calls out was inspected against the
ORM in ``src/goldsmith_erp/db/models.py`` on 2026-04-19:

  * ``orders``          — ``updated_at`` with Python-side ``onupdate=
    datetime.utcnow`` already present (line 442). **No-op.**
  * ``customers``       — ``updated_at`` with Python-side ``onupdate``
    already present (line 244). **No-op.**
  * ``metal_purchases`` — ``updated_at`` with Python-side ``onupdate``
    already present (lines 727–729). **No-op.**
  * ``repair_jobs``     — ``updated_at`` with Python-side ``onupdate``
    already present (lines 1622–1624). **No-op.**
  * ``activities``      — **has NO ``updated_at`` column at all** in
    the ORM (line 530). The prior plan claim that `activities` was
    "already covered" is inaccurate. Adding the column + backfill is
    out of scope for the Slice 2 security floor; tracked as a hygiene
    item and not a blocker for any Slice 2 dependency. Service writes
    to ``activities`` currently do not depend on ``updated_at``.
  * ``materials``       — **has NO ``updated_at`` column at all** in
    the ORM (line 510). Same reasoning as ``activities``.
  * ``time_entries``    — **has NO ``updated_at`` column at all** in
    the ORM (line 554). We add ``origin``, ``correction_of`` and
    ``retention_class`` here. Adding ``updated_at`` is scheduled for a
    later slice when the ``PATCH /time_entries/{id}/activity`` endpoint
    (Slice 5) needs the touch-tracker — adding it prematurely without a
    writer is dead weight and drifts the ORM from the DB.

Net audit outcome: three tables are correctly covered by SQLAlchemy's
Python-side ``onupdate``; three others lack any ``updated_at`` column
and are deliberately left as-is for Slice 2; no DB trigger is added
anywhere in this migration (per R5 — SQLAlchemy does the right thing).

SQLite fallback
---------------
PostgreSQL JSONB and partial indexes are honoured on PG. SQLite falls
back to TEXT / plain indexes via dialect detection inside ``upgrade()``
and ``downgrade()``. All idempotent guard helpers come from
``goldsmith_erp.db.migration_helpers`` (H6 — fresh-DB safe).

Revision ID: 20260419_security_floor
Revises: 20260418_qr_core
Create Date: 2026-04-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from goldsmith_erp.db.migration_helpers import (
    add_column_if_not_exists,
    column_exists,
    create_index_if_not_exists,
    drop_column_if_exists,
    drop_index_if_exists,
)

# revision identifiers, used by Alembic.
revision: str = "20260419_security_floor"
down_revision: Union[str, None] = "20260418_qr_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helper — dialect-aware JSONB / JSON column.
# ---------------------------------------------------------------------------


def _jsonb_or_json() -> sa.types.TypeEngine:
    """JSONB on PostgreSQL, plain JSON on SQLite (test suite)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB

        return JSONB()
    return sa.JSON()


def _jsonb_empty_array_default() -> sa.sql.elements.TextClause:
    """Server default for a JSONB ``[]`` — dialect-aware.

    PostgreSQL prefers ``'[]'::jsonb`` so the planner stores the value as
    JSONB and not as a cast expression on every insert. SQLite stores a
    plain TEXT value and accepts the unquoted form.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("'[]'::jsonb")
    return sa.text("'[]'")


def _add_fk_column(
    table: str,
    column_name: str,
    column_type: sa.types.TypeEngine,
    referent_table: str,
    referent_column: str,
    constraint_name: str,
    ondelete: str,
) -> None:
    """Add a new FK column idempotently across SQLite + PostgreSQL.

    SQLite does NOT support ``ALTER TABLE ADD COLUMN`` with an inline
    FK constraint — that path raises ``NotImplementedError: No support
    for ALTER of constraints in SQLite dialect``. Alembic's official
    remedy is batch-mode (copy + move); we instead add the raw column
    on SQLite and skip the constraint. PG gets both column and FK.

    On a fresh DB built via ``Base.metadata.create_all()`` the ORM
    class already carries the FK inline, so SQLite users of the test
    suite see the constraint anyway. Only the migration path against a
    legacy SQLite DB loses the constraint — a tradeoff the H6 helper
    docstring already calls out and that production (PostgreSQL) never
    hits.
    """
    if column_exists(table, column_name):
        return
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # Plain column — no FK on the ALTER path.
        op.add_column(table, sa.Column(column_name, column_type, nullable=True))
    else:
        op.add_column(
            table,
            sa.Column(
                column_name,
                column_type,
                sa.ForeignKey(
                    f"{referent_table}.{referent_column}",
                    name=constraint_name,
                    ondelete=ondelete,
                ),
                nullable=True,
            ),
        )


# ---------------------------------------------------------------------------
# upgrade()
# ---------------------------------------------------------------------------


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # -------------------------------------------------------------------
    # 1. orders — Punzierungs-Check + retention.
    # -------------------------------------------------------------------
    add_column_if_not_exists(
        "orders",
        sa.Column(
            "punzierung_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    _add_fk_column(
        table="orders",
        column_name="punzierung_verified_by",
        column_type=sa.Integer(),
        referent_table="users",
        referent_column="id",
        constraint_name="fk_orders_punzierung_verified_by_users",
        ondelete="RESTRICT",
    )
    add_column_if_not_exists(
        "orders",
        sa.Column(
            "punzierung_verified_marks",
            _jsonb_or_json(),
            nullable=False,
            server_default=_jsonb_empty_array_default(),
        ),
    )
    add_column_if_not_exists(
        "orders",
        sa.Column(
            "retention_class",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'indefinite_business'"),
        ),
    )

    # -------------------------------------------------------------------
    # 2. material_usage — alloy override + reason + user_id + retention.
    # -------------------------------------------------------------------
    add_column_if_not_exists(
        "material_usage",
        sa.Column(
            "alloy_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    add_column_if_not_exists(
        "material_usage",
        sa.Column(
            "override_reason",
            sa.Text(),
            nullable=True,
        ),
    )
    add_column_if_not_exists(
        "material_usage",
        sa.Column(
            "override_reason_category",
            sa.String(length=32),
            nullable=True,
        ),
    )
    add_column_if_not_exists(
        "material_usage",
        sa.Column(
            "retention_class",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'financial_10y'"),
        ),
    )
    # material_usage.user_id — NEW column (wasn't in the ORM per Henrik's
    # Slice 0 note). Anna B2 assumed it existed; we add it now so the
    # anonymisation contract covers MaterialUsage rows.
    _add_fk_column(
        table="material_usage",
        column_name="user_id",
        column_type=sa.Integer(),
        referent_table="users",
        referent_column="id",
        constraint_name="fk_material_usage_user_id_users",
        ondelete="RESTRICT",
    )

    # -------------------------------------------------------------------
    # 3. time_entries — origin + correction_of + retention.
    # -------------------------------------------------------------------
    # `origin` is added WITHOUT a server_default first so the back-
    # population can run predictably, then the column is tightened to
    # NOT NULL with the 'manual' default. On PostgreSQL the column is
    # added as NOT NULL with a default up-front; SQLite has the same
    # end-state because ``add_column`` with ``server_default`` writes
    # the default to existing rows at column-add time.
    add_column_if_not_exists(
        "time_entries",
        sa.Column(
            "origin",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )

    # Idempotent back-population of existing rows. ``add_column`` with
    # a server_default writes the default to existing rows at column-
    # creation time on both dialects, but we UPDATE explicitly so the
    # migration is self-documenting and safe against future refactors.
    op.execute("UPDATE time_entries SET origin = 'manual' WHERE origin IS NULL")

    _add_fk_column(
        table="time_entries",
        column_name="correction_of",
        column_type=sa.String(length=36),  # time_entries.id is String(36)
        referent_table="time_entries",
        referent_column="id",
        constraint_name="fk_time_entries_correction_of_self",
        ondelete="SET NULL",
    )
    add_column_if_not_exists(
        "time_entries",
        sa.Column(
            "retention_class",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'financial_10y'"),
        ),
    )

    # -------------------------------------------------------------------
    # 4. users — is_test_user flag.
    # -------------------------------------------------------------------
    add_column_if_not_exists(
        "users",
        sa.Column(
            "is_test_user",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # -------------------------------------------------------------------
    # 5. Indexes — every one has a justifying query pattern (R5).
    # -------------------------------------------------------------------

    # time_entries.origin — used by the 30-day scan-adoption metric
    # (Lena §1 corrected query). Composite with created_at because the
    # query filters on ``created_at > now() - '30 days'`` and groups by
    # ``origin``.
    create_index_if_not_exists(
        "idx_time_entries_origin_created_at",
        "time_entries",
        ["origin", "created_at"],
    )

    # time_entries.correction_of — partial index (PG) for the
    # "exclude corrections from adoption metric" filter. SQLite cannot
    # express partial indexes via the inspector-based helper; fall back
    # to a plain index (still small — majority of rows are NULL).
    if dialect == "postgresql":
        # Partial index: only rows where correction_of IS NOT NULL.
        # Use raw SQL to emit the WHERE clause since create_index does
        # not accept a postgresql_where on the generic op helper across
        # all Alembic versions uniformly.
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_time_entries_correction_of "
            "ON time_entries (correction_of) WHERE correction_of IS NOT NULL"
        )
    else:
        create_index_if_not_exists(
            "idx_time_entries_correction_of",
            "time_entries",
            ["correction_of"],
        )

    # orders.punzierung_verified_at — "which orders are verified" lookup
    # on the QC dashboard. Partial on PG (verified rows are the minority);
    # plain index on SQLite.
    if dialect == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_punzierung_verified_at "
            "ON orders (punzierung_verified_at) "
            "WHERE punzierung_verified_at IS NOT NULL"
        )
    else:
        create_index_if_not_exists(
            "idx_orders_punzierung_verified_at",
            "orders",
            ["punzierung_verified_at"],
        )

    # users.is_test_user — partial on PG (TRUE is the minority). Used by
    # every metric query (Lena §1).
    if dialect == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_is_test_user "
            "ON users (is_test_user) WHERE is_test_user = TRUE"
        )
    else:
        create_index_if_not_exists(
            "idx_users_is_test_user",
            "users",
            ["is_test_user"],
        )

    # retention_class indexes — future retention engine will SELECT by
    # retention_class across each table.
    create_index_if_not_exists(
        "idx_orders_retention_class",
        "orders",
        ["retention_class"],
    )
    create_index_if_not_exists(
        "idx_material_usage_retention_class",
        "material_usage",
        ["retention_class"],
    )
    create_index_if_not_exists(
        "idx_time_entries_retention_class",
        "time_entries",
        ["retention_class"],
    )


# ---------------------------------------------------------------------------
# downgrade() — reversible. Drops indexes first, then columns.
# ---------------------------------------------------------------------------


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Indexes (drop before columns so FK / NOT NULL don't trip).
    drop_index_if_exists("idx_time_entries_retention_class", "time_entries")
    drop_index_if_exists("idx_material_usage_retention_class", "material_usage")
    drop_index_if_exists("idx_orders_retention_class", "orders")

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_users_is_test_user")
        op.execute("DROP INDEX IF EXISTS idx_orders_punzierung_verified_at")
        op.execute("DROP INDEX IF EXISTS idx_time_entries_correction_of")
    else:
        drop_index_if_exists("idx_users_is_test_user", "users")
        drop_index_if_exists("idx_orders_punzierung_verified_at", "orders")
        drop_index_if_exists("idx_time_entries_correction_of", "time_entries")

    drop_index_if_exists("idx_time_entries_origin_created_at", "time_entries")

    # users.is_test_user
    drop_column_if_exists("users", "is_test_user")

    # time_entries — reverse order of addition.
    drop_column_if_exists("time_entries", "retention_class")
    drop_column_if_exists("time_entries", "correction_of")
    drop_column_if_exists("time_entries", "origin")

    # material_usage — reverse order.
    drop_column_if_exists("material_usage", "user_id")
    drop_column_if_exists("material_usage", "retention_class")
    drop_column_if_exists("material_usage", "override_reason_category")
    drop_column_if_exists("material_usage", "override_reason")
    drop_column_if_exists("material_usage", "alloy_override")

    # orders — reverse order.
    drop_column_if_exists("orders", "retention_class")
    drop_column_if_exists("orders", "punzierung_verified_marks")
    drop_column_if_exists("orders", "punzierung_verified_by")
    drop_column_if_exists("orders", "punzierung_verified_at")
