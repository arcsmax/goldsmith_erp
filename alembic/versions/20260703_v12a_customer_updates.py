"""V1.2a — CustomerUpdate + CostChangeRequest tables, COST_ALERT notification
type.

Part of the V1.2 customer-updates & §649 BGB cost-approval feature (Task 1).
Adds two new tables:

- ``cost_change_requests`` — §649 BGB change-order style approval record
  (created first: ``customer_updates.cost_change_request_id`` FKs into it).
- ``customer_updates`` — Kundeninfo sent to a customer (progress, cost
  change, ready-for-pickup, custom), attaches to EITHER an order or a
  repair job.

Idempotency
-----------
Both tables are already declared on the ORM (``db/models.py``), so on a
fresh DB ``v1_initial``'s ``Base.metadata.create_all()`` creates them before
this migration runs — ``create_table_if_not_exists`` is a no-op there and
only creates the tables on legacy DBs that pre-date this change (mirrors
20260702_v11a_consultation_tables.py).

Revision ID: 20260703_v12a_cust_updates
Revises: 20260703_r2_intake_checklist
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260703_v12a_cust_updates"
down_revision: Union[str, None] = "20260703_r2_intake_checklist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_table_if_not_exists,
    )

    # Created first — customer_updates.cost_change_request_id FKs into it.
    # Column `index=True` flags mirror db/models.CostChangeRequest exactly —
    # on a fresh DB create_all() already produces these indexes, but a
    # legacy-DB catch-up run executes THIS raw DDL, so it must match.
    create_table_if_not_exists(
        "cost_change_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, index=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "quote_id",
            sa.Integer(),
            sa.ForeignKey("quotes.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("original_amount", sa.Float(), nullable=False),
        sa.Column("new_amount", sa.Float(), nullable=False),
        sa.Column("delta_percent", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("line_items", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
            index=True,
        ),
        sa.Column("response_method", sa.String(20), nullable=True),
        sa.Column("response_evidence", sa.Text(), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column(
            "recorded_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Same index-parity note as above — mirrors db/models.CustomerUpdate.
    create_table_if_not_exists(
        "customer_updates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, index=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "repair_job_id",
            sa.Integer(),
            sa.ForeignKey("repair_jobs.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("photo_ids", sa.JSON(), nullable=True),
        sa.Column(
            "cost_change_request_id",
            sa.Integer(),
            sa.ForeignKey("cost_change_requests.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
            index=True,
        ),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column(
            "sent_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("delivery_method", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # PostgreSQL stores NotificationTypeEnum as a native enum; SQLite as strings.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE notificationtypeenum ADD VALUE IF NOT EXISTS 'cost_alert'"
        )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import drop_table_if_exists  # noqa: PLC0415

    # customer_updates FKs into cost_change_requests — drop it first.
    drop_table_if_exists("customer_updates")
    drop_table_if_exists("cost_change_requests")
    # Postgres enum values cannot be removed; leaving 'cost_alert' is harmless.
