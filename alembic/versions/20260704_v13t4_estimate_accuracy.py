"""V1.3 Estimator Task 4 — EstimateAccuracy table (learning-loop calibration).

Adds ``estimate_accuracy``: one row per completed order that had a prior
STORED estimate, recording estimated-vs-actual hours + labor total so
``EstimateAccuracyService.calibration()`` can compute a rolling MAPE and
per-order-type bias. Estimate storage itself (where a prior estimate lives
on an order/quote) is V1.3 Task 5's job — this table is estimate-source-
agnostic and additive only; nothing here depends on Task 5 landing first.

``order_id`` uses ``ondelete="RESTRICT"`` — accuracy rows are Art. 30
calibration evidence tied to one specific completed order, matching the
``cost_change_requests.order_id`` / ``invoices.order_id`` financial-
retention precedent (a hard delete of the order must not silently orphan
this record).

Idempotency
-----------
The table is already declared on the ORM (``db/models.py``), so a fresh DB's
``v1_initial`` ``Base.metadata.create_all()`` creates it before this
migration runs — ``create_table_if_not_exists`` is a no-op there and only
creates the table on legacy DBs that pre-date this change (mirrors
20260703_v12a_customer_updates.py / 20260702_v11a_consultation_tables.py).

Revision ID: 20260704_v13t4_est_accuracy
Revises: 20260704_v13t1_hourly_rate
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260704_v13t4_est_accuracy"
down_revision: Union[str, None] = "20260704_v13t1_hourly_rate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_table_if_not_exists,
    )

    # Column shape mirrors db/models.EstimateAccuracy exactly (index=True
    # flags included) so a legacy-DB catch-up run via this raw DDL produces
    # the same shape create_all() already produces on a fresh DB.
    create_table_if_not_exists(
        "estimate_accuracy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, index=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("estimated_hours", sa.Float(), nullable=False),
        sa.Column("actual_hours", sa.Float(), nullable=False),
        sa.Column("estimated_total", sa.Float(), nullable=False),
        sa.Column("actual_total", sa.Float(), nullable=False),
        sa.Column("estimator_version", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import drop_table_if_exists  # noqa: PLC0415

    drop_table_if_exists("estimate_accuracy")
