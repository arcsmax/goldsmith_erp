"""Add catalog fields to materials table

Revision ID: 1a2b3c4d5e6f
Revises: 5e6f7a8b9c0d
Create Date: 2026-04-01

Adds four new columns to the ``materials`` table:
  image_url   VARCHAR(500)   nullable  -- path/URL to the material image
  supplier    VARCHAR(200)   nullable  -- supplier / Lieferant name
  webshop_url VARCHAR(500)   nullable  -- direct reorder link to supplier webshop
  min_stock   FLOAT          NOT NULL  -- per-material low-stock threshold (default 10.0)

Rollback strategy:
  downgrade() drops the four columns; no data is written by this migration
  so rollback is safe at any point.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "1a2b3c4d5e6f"
down_revision = "5e6f7a8b9c0d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "materials",
        sa.Column("image_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "materials",
        sa.Column("supplier", sa.String(200), nullable=True),
    )
    op.add_column(
        "materials",
        sa.Column("webshop_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "materials",
        sa.Column(
            "min_stock",
            sa.Float(),
            nullable=False,
            server_default="10.0",
        ),
    )


def downgrade() -> None:
    op.drop_column("materials", "min_stock")
    op.drop_column("materials", "webshop_url")
    op.drop_column("materials", "supplier")
    op.drop_column("materials", "image_url")
