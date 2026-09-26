"""W8: configurable workshop locations (Standorte).

Creates ``workshop_locations`` (id, name unique, kind, is_active,
sort_order, created_at), seeds it with the distinct, trimmed location
strings already in use (``time_entries.location``,
``orders.current_location``, ``location_history.location``; deduplicated
case-insensitively) and adds nullable ``location_id`` FKs to
``time_entries`` and ``orders``, backfilled by name. The legacy text
columns stay for one release; the services write both.

Downgrade drops the FKs and the table. The text columns were never
touched, so no location information is lost.

Revision ID: 20260925_w8_workshop_locations
Revises: 20260925_w7_care_text
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260925_w8_workshop_locations"
down_revision: Union[str, None] = "20260925_w7_care_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "workshop_locations"
NAME_MAX = 50
# (table, text column) pairs whose values seed the new table.
SOURCES = (
    ("time_entries", "location"),
    ("orders", "current_location"),
    ("location_history", "location"),
)
# (table, text column) pairs that get a location_id FK, backfilled by name.
FK_TARGETS = (("time_entries", "location"), ("orders", "current_location"))
KIND_HINTS = (
    ("bench", ("werkbank", "bench", "workbench")),
    ("safe", ("tresor", "safe", "vault")),
    ("showroom", ("ausstellung", "showroom", "laden", "vitrine")),
    ("external", ("extern", "external", "lieferant", "giesserei")),
)


def guess_kind(name: str) -> str:
    """Best-effort kind for a legacy free-text location."""
    lowered = name.lower()
    for kind, hints in KIND_HINTS:
        if any(hint in lowered for hint in hints):
            return kind
    return "other"


def _fk_name(table: str) -> str:
    return f"fk_{table}_location_id"


def _ix_name(table: str) -> str:
    return f"ix_{table}_location_id"


def _collect_existing_strings(conn: sa.engine.Connection) -> list[str]:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        column_exists,
        table_exists,
    )

    seen: dict[str, str] = {}
    for table, column in SOURCES:
        if not (table_exists(table) and column_exists(table, column)):
            continue
        rows = conn.execute(
            sa.text(
                f"SELECT DISTINCT {column} FROM {table} "  # noqa: S608 - constants
                f"WHERE {column} IS NOT NULL ORDER BY {column}"
            )
        ).scalars()
        for raw in rows:
            name = str(raw).strip()[:NAME_MAX].strip()
            if name and name.lower() not in seen:
                seen[name.lower()] = name
    return list(seen.values())


def _seed(conn: sa.engine.Connection) -> None:
    existing = {
        str(n).lower()
        for n in conn.execute(sa.text(f"SELECT name FROM {TABLE}")).scalars()
    }
    names = [n for n in _collect_existing_strings(conn) if n.lower() not in existing]
    start = len(existing)
    for offset, name in enumerate(names):
        conn.execute(
            sa.text(
                f"INSERT INTO {TABLE} (name, kind, is_active, sort_order, created_at)"
                " VALUES (:name, :kind, :active, :sort, CURRENT_TIMESTAMP)"
            ),
            {
                "name": name,
                "kind": guess_kind(name),
                "active": True,
                "sort": (start + offset) * 10,
            },
        )


def _backfill(conn: sa.engine.Connection, table: str, column: str) -> None:
    conn.execute(
        sa.text(
            f"UPDATE {table} SET location_id = ("  # noqa: S608 - constants
            f" SELECT w.id FROM {TABLE} w"
            f" WHERE lower(w.name) = lower(trim({table}.{column})))"
            f" WHERE location_id IS NULL AND {column} IS NOT NULL"
        )
    )


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        create_fk_if_not_exists,
        create_index_if_not_exists,
        create_table_if_not_exists,
        table_exists,
    )

    create_table_if_not_exists(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(NAME_MAX), nullable=False),
        sa.Column(
            "kind", sa.String(20), nullable=False, server_default=sa.text("'other'")
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_workshop_locations_name"),
        sa.CheckConstraint(
            "kind IN ('bench', 'safe', 'showroom', 'external', 'other')",
            name="ck_workshop_locations_kind",
        ),
    )
    create_index_if_not_exists("ix_workshop_locations_id", TABLE, ["id"])

    conn = op.get_bind()
    _seed(conn)

    for table, column in FK_TARGETS:
        if not table_exists(table):
            continue
        add_column_if_not_exists(
            table, sa.Column("location_id", sa.Integer(), nullable=True)
        )
        create_index_if_not_exists(_ix_name(table), table, ["location_id"])
        create_fk_if_not_exists(
            _fk_name(table),
            table,
            TABLE,
            ["location_id"],
            ["id"],
            ondelete="SET NULL",
        )
        _backfill(conn, table, column)


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        drop_constraint_if_exists,
        drop_index_if_exists,
        drop_table_if_exists,
        table_exists,
    )

    for table, _column in FK_TARGETS:
        if not table_exists(table):
            continue
        drop_constraint_if_exists(_fk_name(table), table, type_="foreignkey")
        drop_index_if_exists(_ix_name(table), table)
        drop_column_if_exists(table, "location_id")
    drop_index_if_exists("ix_workshop_locations_id", TABLE)
    drop_table_if_exists(TABLE)
