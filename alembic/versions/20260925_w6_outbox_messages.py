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

Revision ID: 20260925_w6_outbox
Revises: 20260925_w216_altgold_id
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_w6_outbox"
down_revision: Union[str, None] = "20260925_w216_altgold_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
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
    op.create_index("ix_outbox_messages_id", "outbox_messages", ["id"])
    op.create_index(
        "ix_outbox_messages_status_next_attempt",
        "outbox_messages",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_status_next_attempt", "outbox_messages")
    op.drop_index("ix_outbox_messages_id", "outbox_messages")
    op.drop_table("outbox_messages")
