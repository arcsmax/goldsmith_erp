"""add estimator_metadata JSONB to quote_line_items (V1.3 Phase 3)

Revision ID: 20260705_v13t5_quote_line_item_estimator_metadata
Revises: 20260704_v13t4_est_accuracy
Create Date: 2026-07-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260705_v13t5_quote_line_item_estimator_metadata"
down_revision: Union[str, None] = "20260704_v13t4_est_accuracy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quote_line_items",
        sa.Column("estimator_metadata", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quote_line_items", "estimator_metadata")
