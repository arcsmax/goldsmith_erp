"""add_metal_type_to_orders

Revision ID: 495e8f5a25fb
Revises: d2d180a82769
Create Date: 2025-11-09 22:39:25.348542

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '495e8f5a25fb'
down_revision: Union[str, None] = 'd2d180a82769'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add metal inventory integration fields to orders table:
    - metal_type: Which metal type to use for this order
    - costing_method_used: Which costing method was used (FIFO/LIFO/AVERAGE/SPECIFIC)
    - specific_metal_purchase_id: For SPECIFIC method, which batch was used
    """

    # Add metal_type column (nullable for backwards compatibility)
    op.add_column('orders', sa.Column('metal_type', sa.Enum(
        'GOLD_24K', 'GOLD_22K', 'GOLD_18K', 'GOLD_14K', 'GOLD_9K',
        'SILVER_999', 'SILVER_925', 'SILVER_800',
        'PLATINUM_950', 'PLATINUM_900', 'PALLADIUM',
        'WHITE_GOLD_18K', 'WHITE_GOLD_14K',
        'ROSE_GOLD_18K', 'ROSE_GOLD_14K',
        name='metaltype', create_type=False  # Use existing enum from previous migration
    ), nullable=True))

    # Add costing_method_used column
    op.add_column('orders', sa.Column('costing_method_used', sa.Enum(
        'FIFO', 'LIFO', 'AVERAGE', 'SPECIFIC',
        name='costingmethod', create_type=False  # Use existing enum
    ), nullable=True, server_default='FIFO'))

    # Add specific_metal_purchase_id column (foreign key to metal_purchases)
    op.add_column('orders', sa.Column('specific_metal_purchase_id', sa.Integer(), nullable=True))

    # Create foreign key constraint
    op.create_foreign_key(
        'fk_orders_specific_metal_purchase',
        'orders', 'metal_purchases',
        ['specific_metal_purchase_id'], ['id'],
        ondelete='SET NULL'  # If purchase is deleted, set to NULL (shouldn't happen due to RESTRICT on metal_purchases)
    )

    # Create index on metal_type for filtering
    op.create_index(op.f('ix_orders_metal_type'), 'orders', ['metal_type'])


def downgrade() -> None:
    """Remove metal inventory integration fields from orders."""
    op.drop_index(op.f('ix_orders_metal_type'), table_name='orders')
    op.drop_constraint('fk_orders_specific_metal_purchase', 'orders', type_='foreignkey')
    op.drop_column('orders', 'specific_metal_purchase_id')
    op.drop_column('orders', 'costing_method_used')
    op.drop_column('orders', 'metal_type')
