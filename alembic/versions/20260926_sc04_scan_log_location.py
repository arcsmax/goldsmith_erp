"""SC-04 follow-up: indexed location_id column on scan_logs.

Commit 2877229 ("scan location from the W8 workshop locations (SC-04,
partial)") resolved a scan's ``location_id`` against ``workshop_locations``
server-side but only ever stored the result inside ``scan_logs.context``
(JSON) — its own message says so: "No scan_logs migration (JSON context)".
That means the configured Standort of a scan could not be indexed or
queried as a column, only pulled out of JSON per-row in Python
(``scan_history_service._ctx_int``).

This migration promotes it to a real column, following the exact pattern
``20260925_w8_workshop_locations`` used for ``time_entries.location_id`` /
``orders.location_id``:

  * ``scan_logs.location_id INTEGER NULL``
  * ``ix_scan_logs_location_id`` — a plain index (also a partitioned index
    on PostgreSQL: propagates to every existing partition and to future
    ones attached to ``scan_logs``, same as ``idx_scan_user_date`` /
    ``idx_scan_entity`` from the Slice 1 migration).
  * ``fk_scan_logs_location_id_workshop_locations`` — ``ON DELETE SET
    NULL`` (deactivating/deleting a Standort must never lose a scan or
    block a delete), matching the FK's ``ondelete`` on the ORM model.
  * Backfill of existing rows from ``context->>'location_id'``
    (PostgreSQL JSONB) / ``json_extract(context, '$.location_id')``
    (SQLite JSON-as-text), for the rows already written since 2877229.

``scan_logs`` is RANGE-partitioned by ``scanned_at`` on PostgreSQL
(``20260418_qr_core``). Adding a column and creating an index on a
partitioned *parent* table are both ordinary, PG-11+-native operations —
PostgreSQL propagates ``ADD COLUMN`` (with a constant/NULL default) and
``CREATE INDEX`` to every existing partition and to future ones, no
per-partition DDL is required here, unlike the parent migration's manual
per-partition ``CREATE TABLE ... PARTITION OF``. The composite PK
``(id, scanned_at)`` and the partitioning itself are untouched.

Downgrade drops the FK, the index, then the column. No data is destroyed:
the JSON copy in ``context`` is untouched by either direction, so a
downgrade never loses the "where" a scan happened — only the indexed/
queryable column goes away.

Revision ID: 20260926_sc04_scan_log_location
Revises: 20260925_w8_workshop_locations
Create Date: 2026-09-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260926_sc04_scan_log_location"
down_revision: Union[str, None] = "20260925_w8_workshop_locations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "scan_logs"
COLUMN = "location_id"
FK_NAME = "fk_scan_logs_location_id_workshop_locations"
IX_NAME = "ix_scan_logs_location_id"


def _backfill(bind: sa.engine.Connection) -> None:
    """Copy ``context.location_id`` into the new column for existing rows.

    Only rows written since commit 2877229 carry it, and only when the id
    was resolvable (``scanner_service._resolve_scan_location`` drops
    unknown/deactivated ids back to ``None`` before the row is built) — so
    every value in ``context`` is already a plain positive integer. The
    numeric guard is defence-in-depth against any row written outside
    that path.
    """
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(f"""
                UPDATE {TABLE}
                SET {COLUMN} = (context ->> 'location_id')::integer
                WHERE {COLUMN} IS NULL
                  AND context IS NOT NULL
                  AND context ? 'location_id'
                  AND context ->> 'location_id' ~ '^[0-9]+$'
                """))  # noqa: S608 - constants only, no user input
    else:
        bind.execute(sa.text(f"""
                UPDATE {TABLE}
                SET {COLUMN} = CAST(
                    json_extract(context, '$.location_id') AS INTEGER
                )
                WHERE {COLUMN} IS NULL
                  AND context IS NOT NULL
                  AND json_extract(context, '$.location_id') IS NOT NULL
                """))  # noqa: S608 - constants only, no user input


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        create_fk_if_not_exists,
        create_index_if_not_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return

    add_column_if_not_exists(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=True))
    create_index_if_not_exists(IX_NAME, TABLE, [COLUMN])
    create_fk_if_not_exists(
        FK_NAME,
        TABLE,
        "workshop_locations",
        [COLUMN],
        ["id"],
        ondelete="SET NULL",
    )

    _backfill(op.get_bind())


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        drop_constraint_if_exists,
        drop_index_if_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return

    drop_constraint_if_exists(FK_NAME, TABLE, type_="foreignkey")
    drop_index_if_exists(IX_NAME, TABLE)
    drop_column_if_exists(TABLE, COLUMN)
