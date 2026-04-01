"""Add ML fields to orders table for duration prediction pipeline

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-03-31

Adds five columns to the `orders` table that are required as features for the
ML duration-prediction model (XGBoost) and data quality monitoring:

  order_type      VARCHAR(50)  -- ring, chain, pendant, earrings, bracelet, etc.
  finish_type     VARCHAR(50)  -- high_polish, matte, brushed, hammered, oxidized, mixed
  complexity_rating  INTEGER  -- 1-5 stars (set at intake by the goldsmith)
  actual_hours    FLOAT        -- auto-calculated from time entries on completion
  completed_at    TIMESTAMP    -- set when order status transitions to COMPLETED/DELIVERED

All columns are nullable so the migration is backwards-compatible with existing rows.
An index on order_type supports the data quality GROUP-BY queries.

Rollback strategy:
  downgrade() drops the five columns and the order_type index in reverse order.
  This is safe because the columns are nullable and carry no FK constraints.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '2b3c4d5e6f7a'
down_revision: Union[str, None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ML feature: type of jewelry piece (ring, chain, pendant, …)
    op.add_column(
        'orders',
        sa.Column('order_type', sa.String(50), nullable=True),
    )
    op.create_index('ix_orders_order_type', 'orders', ['order_type'])

    # ML feature: surface finish type — correlates with polishing Arbeitszeit
    op.add_column(
        'orders',
        sa.Column('finish_type', sa.String(50), nullable=True),
    )

    # ML feature: overall complexity rating set at order intake (1-5)
    op.add_column(
        'orders',
        sa.Column('complexity_rating', sa.Integer(), nullable=True),
    )

    # ML target: net actual hours from time entries, auto-set on completion
    op.add_column(
        'orders',
        sa.Column('actual_hours', sa.Float(), nullable=True),
    )

    # ML metadata: exact timestamp when order reached COMPLETED or DELIVERED
    op.add_column(
        'orders',
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('orders', 'completed_at')
    op.drop_column('orders', 'actual_hours')
    op.drop_column('orders', 'complexity_rating')
    op.drop_column('orders', 'finish_type')
    op.drop_index('ix_orders_order_type', table_name='orders')
    op.drop_column('orders', 'order_type')
