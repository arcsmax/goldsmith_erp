"""add deletion_scheduled_at to customers for GDPR Art. 17

Revision ID: 20260331_gdpr_deletion
Revises: 20260331_add_order_handoffs_table
Create Date: 2026-03-31

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260331_gdpr_deletion"
down_revision = "4d5e6f7a8b9c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add deletion_scheduled_at column to customers table.

    This column stores the date after which a customer record will be
    permanently hard-deleted by the gdpr-cleanup.sh cron job, in
    compliance with GDPR Art. 17 (right to erasure) and the 30-day
    grace period policy.
    """
    op.add_column(
        "customers",
        sa.Column("deletion_scheduled_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_customers_deletion_scheduled_at",
        "customers",
        ["deletion_scheduled_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove deletion_scheduled_at column from customers table."""
    op.drop_index("ix_customers_deletion_scheduled_at", table_name="customers")
    op.drop_column("customers", "deletion_scheduled_at")
