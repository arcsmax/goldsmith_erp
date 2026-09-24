"""BE-12 (W1-17) — at most one running timer per user.

Partial unique index ``uq_time_entries_one_running`` on
``time_entries(user_id) WHERE end_time IS NULL``. Created with both the
``postgresql_where`` and ``sqlite_where`` dialect arguments so production
(PostgreSQL) and the SQLite test DB enforce the same rule. The ORM declares
the same index (``TimeEntry.__table_args__``), so on a fresh DB
``v1_initial``'s ``create_all()`` already created it and this step no-ops.

Pre-flight: if any user already has more than one open entry the index
cannot be built. The migration then stops with the affected counts instead
of silently closing entries (MASTER-FIX-PLAN W1-17 stop condition): an
operator must decide which entry to close (usually the older one, with
``end_time`` set to the newer entry's ``start_time``).

Revision ID: 20260925_w117_one_running
Revises: 20260925_gdpr01_consents
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260925_w117_one_running"
down_revision: Union[str, None] = "20260925_gdpr01_consents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_time_entries_one_running"
_OPEN = "end_time IS NULL"


def _users_with_several_open_entries() -> list[tuple[int, int]]:
    rows = op.get_bind().execute(
        sa.text(
            "SELECT user_id, COUNT(*) FROM time_entries "
            f"WHERE {_OPEN} GROUP BY user_id HAVING COUNT(*) > 1"
        )
    )
    return [(int(r[0]), int(r[1])) for r in rows]


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_index_if_not_exists,
        index_exists,
        table_exists,
    )

    if not table_exists("time_entries") or index_exists("time_entries", INDEX_NAME):
        return

    duplicates = _users_with_several_open_entries()
    if duplicates:
        detail = ", ".join(f"user_id={u}: {n} offen" for u, n in duplicates)
        raise RuntimeError(
            f"{INDEX_NAME}: {len(duplicates)} Benutzer haben mehrere laufende "
            f"Zeiterfassungen ({detail}). Bitte vor der Migration die aeltere "
            "Zeiterfassung je Benutzer stoppen (end_time setzen)."
        )

    create_index_if_not_exists(
        INDEX_NAME,
        "time_entries",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text(_OPEN),
        sqlite_where=sa.text(_OPEN),
    )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import drop_index_if_exists  # noqa: PLC0415

    drop_index_if_exists(INDEX_NAME, "time_entries")
