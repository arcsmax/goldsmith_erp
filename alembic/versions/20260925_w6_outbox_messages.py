"""W6 outbox (ARCH-04 / ARCH-05): durable ``outbox_messages`` table.

Customer mails are written here in the same transaction as the business
change and sent by the worker process (``python -m goldsmith_erp.worker``),
see docs/technical/architecture/ADR-2026-09-25-outbox.md.

* ``status`` is a plain String(20) with a CHECK constraint (pending / sent /
  failed / dead) instead of a PG enum, so adding a state later needs no
  ``ALTER TYPE``.
* ``dedupe_key`` is UNIQUE and nullable (NULLs never collide).
* ``(status, next_attempt_at)`` index serves the worker's due-rows query.

Downgrade drops the table (lossy: undelivered messages are lost; drain the
queue first).

Idempotency: ``outbox_messages`` is declared on the ORM (``OutboxMessage`` in
``db/models.py``), so on a fresh DB ``v1_initial``'s ``Base.metadata.create_all()``
already creates the table (and its indexes/constraints) before this migration
runs — ``POST_V1_TABLES`` in ``20260401_v1_initial_schema.py`` only excludes
the Slice-1 partitioned tables, not every table added since. Every step below
is guarded via the ``*_if_not_exists`` helpers and no-ops there, matching the
pattern used by the other 2026-09-25 migrations (e.g. gdpr01, w207). Works on
SQLite (tests) and PostgreSQL.

Revision ID: 20260925_w6_outbox
Revises: 20260925_w216_altgold_id
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op  # noqa: F401  (helpers wrap it)

revision: str = "20260925_w6_outbox"
down_revision: Union[str, None] = "20260925_w216_altgold_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_index_if_not_exists,
        create_table_if_not_exists,
    )

    # The UNIQUE constraint is declared inline (not via a separate
    # create_unique_constraint_if_not_exists ALTER) so the standalone-table
    # path (table doesn't exist yet — legacy DB, or the SQLite unit test that
    # runs this migration in isolation) gets it in the same DDL statement.
    # create_unique_constraint_if_not_exists() would silently no-op on
    # SQLite (it can't ALTER in a named constraint), which is only safe when
    # create_all() already declared it inline — i.e. exactly the case where
    # create_table_if_not_exists() below is a no-op anyway.
    create_table_if_not_exists(
        "outbox_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'dead')",
            name="ck_outbox_messages_status",
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_outbox_messages_dedupe_key"),
    )
    # Index names match what the ORM's ``index=True`` produces, so a DB built
    # by create_all() and one built by this migration are identical.
    create_index_if_not_exists("ix_outbox_messages_id", "outbox_messages", ["id"])
    create_index_if_not_exists(
        "ix_outbox_messages_status_next_attempt",
        "outbox_messages",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_index_if_exists,
        drop_table_if_exists,
    )

    drop_index_if_exists("ix_outbox_messages_status_next_attempt", "outbox_messages")
    drop_index_if_exists("ix_outbox_messages_id", "outbox_messages")
    drop_table_if_exists("outbox_messages")
