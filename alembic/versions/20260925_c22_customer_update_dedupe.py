"""C2.2 — DB backstop for the automated customer-mail dedupe.

Adds ``customer_updates.dedupe_key`` (nullable; set only by
``services/automated_customer_email.py``) and the partial unique index
``uq_customer_updates_dedupe_key`` on ``(dedupe_key)`` WHERE
``dedupe_key IS NOT NULL AND status <> 'send_failed'``: at most one live
(draft or sent) automated row per key, so two concurrent monitor ticks
cannot both email the customer. Failed sends are excluded so the next day's
retry can insert a new row; staff-written Kundeninfo has no key.

Existing rows keep ``dedupe_key = NULL`` (no backfill): the application
check in ``_already_handled`` still covers them, and a NULL key is outside
the index.

Idempotent; ``postgresql_where`` + ``sqlite_where`` so production and the
SQLite test DB enforce the same rule. On a fresh DB ``v1_initial``'s
``create_all()`` already created both objects.

Revision ID: 20260925_c22_cu_dedupe
Revises: 20260925_w110_invoice_snap
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op  # noqa: F401  (helpers wrap it)

# revision identifiers, used by Alembic.
revision: str = "20260925_c22_cu_dedupe"
down_revision: Union[str, None] = "20260925_w110_invoice_snap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_customer_updates_dedupe_key"
_LIVE_KEYED = "dedupe_key IS NOT NULL AND status <> 'send_failed'"


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        create_index_if_not_exists,
        table_exists,
    )

    if not table_exists("customer_updates"):
        return
    add_column_if_not_exists(
        "customer_updates", sa.Column("dedupe_key", sa.String(200), nullable=True)
    )
    create_index_if_not_exists(
        INDEX_NAME,
        "customer_updates",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text(_LIVE_KEYED),
        sqlite_where=sa.text(_LIVE_KEYED),
    )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        drop_index_if_exists,
    )

    drop_index_if_exists(INDEX_NAME, "customer_updates")
    drop_column_if_exists("customer_updates", "dedupe_key")
