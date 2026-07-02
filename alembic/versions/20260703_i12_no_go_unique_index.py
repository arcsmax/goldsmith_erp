"""I12 — DB-level unique index closing the customer-no-go duplicate TOCTOU.

Fix item **I12** (github issue #12). ``NoGoService.add_no_go`` (see
``services/no_go_service.py``) checks for an equivalent no-go (same
``customer_id`` + ``category`` + casefolded ``value``) BEFORE entering its
``transactional(db)`` block — deliberately: business rejections must never
hit the transaction error logger, which logs ``str(exc)`` at ERROR (see the
SECURITY docstrings on ``DuplicateNoGoError`` and that logger). That
ordering is binding and out of scope here.

Without a DB constraint, that app-side check was never concurrency-safe:
two requests racing between the read and the insert can both pass it and
both land a duplicate row. This migration adds the missing backstop — a
functional (expression) UNIQUE index on
``(customer_id, category, lower(value))`` — so a raced second insert now
fails at the DB with ``IntegrityError`` instead of silently succeeding.
The service-layer half of this fix (catching that ``IntegrityError`` inside
the transactional block and re-raising the generic ``DuplicateNoGoError``,
so the raw value never reaches the transaction logger) lives in
``services/no_go_service.py``.

Why raw ``op.execute`` instead of the ``migration_helpers`` wrappers
---------------------------------------------------------------------
``create_index_if_not_exists`` (``goldsmith_erp/db/migration_helpers.py``)
only accepts plain column-name strings — it forwards straight to
``op.create_index(name, table, [...columns], **kwargs)``, which has no way
to express ``lower(value)``. Both SQLite (3.9+, expression indexes) and
PostgreSQL support functional unique indexes natively, so this migration
emits guarded raw DDL for *both* dialects (unlike the partial-index guards
elsewhere in this repo, e.g. ``20260419_slice_2_security_floor_and_audit_
columns.py``, which only need the PG branch — there the SQLite fallback is
a *plain* index via the helper. Here there is no non-expression fallback
that would still enforce the invariant, so both branches use the same raw
SQL). ``CREATE UNIQUE INDEX IF NOT EXISTS`` makes the DDL itself idempotent
against re-runs and against ``v1_initial``'s ``create_all()`` fresh-DB path
(mirrors ``CustomerNoGo.__table_args__`` in ``db/models.py``, which declares
the identical named index so ``Base.metadata.create_all()`` — used by the
unit-test DB — produces the same constraint shape).

Pre-existing duplicates
------------------------
The app-side check is already casefolded, so in the ordinary product flow
no case-variant duplicates should exist. But this migration must not
explode on a DB that somehow has some anyway (direct DB writes, restored
dev/staging data, a future backfill bug) — ``_dedupe_no_gos`` runs first,
deleting every row but the oldest (by ``created_at``, ties broken by the
lower ``id``) per ``(customer_id, category, lower(value))`` key, so the
index creation below is guaranteed to succeed.

Downgrade drops the index. It does **not** attempt to resurrect any rows
the upgrade's dedup step removed — that data loss is a one-way door, same
as any other destructive dedup migration in this repo.

Revision ID: 20260703_i12_no_go_unique_idx
Revises: 20260703_i15_allergies_enc
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260703_i12_no_go_unique_idx"
down_revision: Union[str, None] = "20260703_i15_allergies_enc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_customer_no_gos_customer_category_value_ci"


def _dedupe_no_gos(bind: sa.engine.Connection) -> None:
    """Delete case-insensitive duplicate no-gos, keeping the oldest row.

    Groups by ``(customer_id, category, value.lower())`` — the exact key
    the unique index below enforces. "Oldest" is ``created_at`` ascending,
    ``id`` ascending as a deterministic tiebreaker, so the first no-go a
    user actually recorded survives. Pure Python-level grouping (like the
    backfill loop in ``20260703_i15_encrypt_allergies.py``) keeps this
    dialect-portable across SQLite and PostgreSQL.
    """
    no_gos_t = sa.table(
        "customer_no_gos",
        sa.column("id", sa.Integer),
        sa.column("customer_id", sa.Integer),
        sa.column("category", sa.String),
        sa.column("value", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    rows = bind.execute(
        sa.select(
            no_gos_t.c.id,
            no_gos_t.c.customer_id,
            no_gos_t.c.category,
            no_gos_t.c.value,
            no_gos_t.c.created_at,
        )
    ).fetchall()

    kept_ids: dict[tuple, int] = {}
    duplicate_ids: list[int] = []
    # Sort so the first row seen per key is the oldest. Compare `created_at
    # is None` first so rows with a NULL timestamp (shouldn't happen — the
    # column is NOT NULL — but the migration must not blow up if one
    # somehow sneaks in) never get directly compared against a datetime.
    for row in sorted(rows, key=lambda r: (r.created_at is None, r.created_at, r.id)):
        key = (row.customer_id, row.category, (row.value or "").lower())
        if key in kept_ids:
            duplicate_ids.append(row.id)
        else:
            kept_ids[key] = row.id

    if duplicate_ids:
        bind.execute(sa.delete(no_gos_t).where(no_gos_t.c.id.in_(duplicate_ids)))


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Dedupe first — the index creation below fails outright on any
    # remaining (customer_id, category, lower(value)) collision. ─────────
    _dedupe_no_gos(bind)

    # ── 2. Functional unique index — the DB-level TOCTOU backstop. ───────
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX_NAME} "
        "ON customer_no_gos (customer_id, category, lower(value))"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")
