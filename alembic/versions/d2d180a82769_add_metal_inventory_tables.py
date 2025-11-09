"""add_metal_inventory_tables

Revision ID: d2d180a82769
Revises: 9f56bec9bf1d
Create Date: 2025-11-09 21:41:55.482797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2d180a82769'
down_revision: Union[str, None] = '9f56bec9bf1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add metal inventory management tables:
    - metal_purchases: Track metal batches purchased by goldsmith
    - material_usage: Link orders to specific metal batches consumed
    - inventory_adjustments: Audit trail for manual inventory changes
    """

    # Create metal_purchases table
    op.create_table(
        'metal_purchases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date_purchased', sa.DateTime(), nullable=False),
        sa.Column('metal_type', sa.Enum(
            'GOLD_24K', 'GOLD_22K', 'GOLD_18K', 'GOLD_14K', 'GOLD_9K',
            'SILVER_999', 'SILVER_925', 'SILVER_800',
            'PLATINUM_950', 'PLATINUM_900', 'PALLADIUM',
            'WHITE_GOLD_18K', 'WHITE_GOLD_14K',
            'ROSE_GOLD_18K', 'ROSE_GOLD_14K',
            name='metaltype'
        ), nullable=False),
        sa.Column('weight_g', sa.Float(), nullable=False),
        sa.Column('remaining_weight_g', sa.Float(), nullable=False),
        sa.Column('price_total', sa.Float(), nullable=False),
        sa.Column('price_per_gram', sa.Float(), nullable=False),
        sa.Column('supplier', sa.String(length=200), nullable=True),
        sa.Column('invoice_number', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('lot_number', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_metal_purchases_id'), 'metal_purchases', ['id'])
    op.create_index(op.f('ix_metal_purchases_date_purchased'), 'metal_purchases', ['date_purchased'])
    op.create_index(op.f('ix_metal_purchases_metal_type'), 'metal_purchases', ['metal_type'])

    # Create material_usage table
    op.create_table(
        'material_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('metal_purchase_id', sa.Integer(), nullable=False),
        sa.Column('weight_used_g', sa.Float(), nullable=False),
        sa.Column('cost_at_time', sa.Float(), nullable=False),
        sa.Column('price_per_gram_at_time', sa.Float(), nullable=False),
        sa.Column('costing_method', sa.Enum(
            'FIFO', 'LIFO', 'AVERAGE', 'SPECIFIC',
            name='costingmethod'
        ), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['metal_purchase_id'], ['metal_purchases.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_material_usage_id'), 'material_usage', ['id'])
    op.create_index(op.f('ix_material_usage_order_id'), 'material_usage', ['order_id'])
    op.create_index(op.f('ix_material_usage_metal_purchase_id'), 'material_usage', ['metal_purchase_id'])
    op.create_index(op.f('ix_material_usage_used_at'), 'material_usage', ['used_at'])

    # Create inventory_adjustments table
    op.create_table(
        'inventory_adjustments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('metal_purchase_id', sa.Integer(), nullable=False),
        sa.Column('adjustment_type', sa.String(length=50), nullable=False),
        sa.Column('weight_change_g', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('adjusted_by_user_id', sa.Integer(), nullable=False),
        sa.Column('adjusted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['adjusted_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['metal_purchase_id'], ['metal_purchases.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inventory_adjustments_id'), 'inventory_adjustments', ['id'])
    op.create_index(op.f('ix_inventory_adjustments_metal_purchase_id'), 'inventory_adjustments', ['metal_purchase_id'])
    op.create_index(op.f('ix_inventory_adjustments_adjusted_at'), 'inventory_adjustments', ['adjusted_at'])


def downgrade() -> None:
    """Remove metal inventory management tables."""
    op.drop_index(op.f('ix_inventory_adjustments_adjusted_at'), table_name='inventory_adjustments')
    op.drop_index(op.f('ix_inventory_adjustments_metal_purchase_id'), table_name='inventory_adjustments')
    op.drop_index(op.f('ix_inventory_adjustments_id'), table_name='inventory_adjustments')
    op.drop_table('inventory_adjustments')

    op.drop_index(op.f('ix_material_usage_used_at'), table_name='material_usage')
    op.drop_index(op.f('ix_material_usage_metal_purchase_id'), table_name='material_usage')
    op.drop_index(op.f('ix_material_usage_order_id'), table_name='material_usage')
    op.drop_index(op.f('ix_material_usage_id'), table_name='material_usage')
    op.drop_table('material_usage')

    op.drop_index(op.f('ix_metal_purchases_metal_type'), table_name='metal_purchases')
    op.drop_index(op.f('ix_metal_purchases_date_purchased'), table_name='metal_purchases')
    op.drop_index(op.f('ix_metal_purchases_id'), table_name='metal_purchases')
    op.drop_table('metal_purchases')

    op.execute('DROP TYPE IF EXISTS costingmethod')
    op.execute('DROP TYPE IF EXISTS metaltype')
