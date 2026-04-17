"""
Alembic migration helpers — dialect-aware schema introspection utilities.

DESIGN NOTE (2026-04-17)
========================
The V1 initial migration (`v1_initial`) uses `Base.metadata.create_all()` —
it consolidates 25 legacy migration files into a single ORM-driven bootstrap.
That means: **fresh databases already contain every table/column/index/constraint
that the ORM currently defines**, including things added by later migrations
(e.g. `customers.is_deleted`, `users.is_deleted`, `customer_audit_logs` table).

Consequence: migrations after `v1_initial` that `op.add_column` / `op.create_table`
for objects already in the ORM will fail on fresh DBs with duplicate-column /
already-exists errors on BOTH SQLite (`sqlite3.OperationalError: duplicate column
name`) and PostgreSQL (`DuplicateColumn` / `DuplicateTable`).

To support BOTH fresh-DB (`alembic upgrade head` against empty DB) AND legacy-DB
(upgrading an old deployment that pre-dates those ORM additions) in a single
code path, these helpers make migration ops idempotent by introspecting the
live bind before emitting DDL.

Use in migrations instead of raw `op.add_column` / `op.create_index` etc:

    from goldsmith_erp.db.migration_helpers import (
        add_column_if_not_exists,
        create_index_if_not_exists,
        create_table_if_not_exists,
        create_fk_if_not_exists,
        create_unique_constraint_if_not_exists,
    )

(This module lives under `src/goldsmith_erp/db/` rather than `alembic/` because
the top-level name `alembic` resolves to the installed Alembic package at
import time — a sibling file `alembic/helpers.py` is not importable as
`alembic.helpers`. `alembic/env.py` puts `src/` on `sys.path`, so every
migration can import from `goldsmith_erp.*` freely.)

These are deliberately written with `sa.inspect(bind)` rather than raw SQL so
they work identically on SQLite (tests) and PostgreSQL (production).
"""
from __future__ import annotations

from typing import Any, Sequence

import sqlalchemy as sa
from alembic import op


def _inspector():
    """Return a SQLAlchemy Inspector bound to the active Alembic connection."""
    return sa.inspect(op.get_bind())


def column_exists(table: str, column: str) -> bool:
    """True if `column` exists on `table` in the live database."""
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    return any(col["name"] == column for col in insp.get_columns(table))


def table_exists(table: str) -> bool:
    """True if `table` exists in the live database."""
    return table in _inspector().get_table_names()


def index_exists(table: str, index_name: str) -> bool:
    """True if a named index exists on `table`."""
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    return any(ix["name"] == index_name for ix in insp.get_indexes(table))


def unique_constraint_exists(table: str, constraint_name: str) -> bool:
    """True if a named UNIQUE constraint exists on `table`."""
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    # get_unique_constraints may not exist on all dialects; guard defensively.
    try:
        ucs = insp.get_unique_constraints(table)
    except NotImplementedError:
        return False
    return any(uc["name"] == constraint_name for uc in ucs)


def foreign_key_exists(table: str, constraint_name: str) -> bool:
    """True if a named FK constraint exists on `table`."""
    insp = _inspector()
    if table not in insp.get_table_names():
        return False
    try:
        fks = insp.get_foreign_keys(table)
    except NotImplementedError:
        return False
    return any(fk.get("name") == constraint_name for fk in fks)


# ---------------------------------------------------------------------------
# Idempotent op wrappers
# ---------------------------------------------------------------------------

def add_column_if_not_exists(table: str, column: sa.Column) -> None:
    """`op.add_column(table, column)` unless the column already exists."""
    if not column_exists(table, column.name):
        op.add_column(table, column)


def create_table_if_not_exists(table: str, *columns: Any, **kwargs: Any) -> None:
    """`op.create_table(table, *columns, **kwargs)` unless the table already exists."""
    if not table_exists(table):
        op.create_table(table, *columns, **kwargs)


def create_index_if_not_exists(
    index_name: str,
    table: str,
    columns: Sequence[str],
    **kwargs: Any,
) -> None:
    """`op.create_index(...)` unless the index already exists on `table`."""
    if not index_exists(table, index_name):
        op.create_index(index_name, table, list(columns), **kwargs)


def create_fk_if_not_exists(
    constraint_name: str,
    source_table: str,
    referent_table: str,
    local_cols: Sequence[str],
    remote_cols: Sequence[str],
    **kwargs: Any,
) -> None:
    """`op.create_foreign_key(...)` unless the FK already exists on the source table.

    Note: SQLite cannot add FKs to an existing table via ALTER (requires batch mode
    with table recreation). On SQLite this is silently skipped if the column was
    declared with the FK inline — which is what `Base.metadata.create_all` does.
    """
    if foreign_key_exists(source_table, constraint_name):
        return
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite: ALTER TABLE cannot add FK constraints post-hoc. On a fresh DB
        # created via create_all(), the FK is already declared inline and the
        # inspector doesn't always expose its name — so we skip silently to
        # keep the migration idempotent. For true legacy SQLite upgrades the
        # caller must use batch_alter_table explicitly.
        return
    op.create_foreign_key(
        constraint_name, source_table, referent_table,
        list(local_cols), list(remote_cols), **kwargs,
    )


def create_unique_constraint_if_not_exists(
    constraint_name: str,
    table: str,
    columns: Sequence[str],
    **kwargs: Any,
) -> None:
    """`op.create_unique_constraint(...)` unless the constraint already exists."""
    if unique_constraint_exists(table, constraint_name):
        return
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite cannot add named constraints via plain ALTER either. Same
        # reasoning as create_fk_if_not_exists — create_all already emits the
        # constraint inline for fresh DBs.
        return
    op.create_unique_constraint(constraint_name, table, list(columns), **kwargs)


def drop_column_if_exists(table: str, column: str) -> None:
    """`op.drop_column(table, column)` only when the column is actually there."""
    if column_exists(table, column):
        op.drop_column(table, column)


def drop_index_if_exists(index_name: str, table: str) -> None:
    """`op.drop_index(index_name, table_name=table)` only when present."""
    if index_exists(table, index_name):
        op.drop_index(index_name, table_name=table)


def drop_table_if_exists(table: str) -> None:
    """`op.drop_table(table)` only when the table exists."""
    if table_exists(table):
        op.drop_table(table)


def drop_constraint_if_exists(
    constraint_name: str,
    table: str,
    type_: str = "foreignkey",
) -> None:
    """`op.drop_constraint(...)` only when the constraint exists.

    `type_` follows Alembic's conventions: "foreignkey", "unique", "check", "primary".
    """
    if type_ == "foreignkey" and not foreign_key_exists(table, constraint_name):
        return
    if type_ == "unique" and not unique_constraint_exists(table, constraint_name):
        return
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite cannot drop named constraints via ALTER; skip.
        return
    op.drop_constraint(constraint_name, table, type_=type_)
