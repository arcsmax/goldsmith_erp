"""add_order_cost_calculation_and_gemstones

Revision ID: 9f56bec9bf1d
Revises: 74ac93690ff6
Create Date: 2025-11-09 09:59:49.206034

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f56bec9bf1d'
down_revision: Union[str, None] = '74ac93690ff6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add weight and cost calculation fields to orders table
    op.add_column('orders', sa.Column('estimated_weight_g', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('actual_weight_g', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('scrap_percentage', sa.Float(), nullable=True, server_default='5.0'))

    # Add cost calculation fields
    op.add_column('orders', sa.Column('material_cost_calculated', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('material_cost_override', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('labor_hours', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('hourly_rate', sa.Float(), nullable=True, server_default='75.00'))
    op.add_column('orders', sa.Column('labor_cost', sa.Float(), nullable=True))

    # Add pricing fields
    op.add_column('orders', sa.Column('profit_margin_percent', sa.Float(), nullable=True, server_default='40.0'))
    op.add_column('orders', sa.Column('vat_rate', sa.Float(), nullable=True, server_default='19.0'))
    op.add_column('orders', sa.Column('calculated_price', sa.Float(), nullable=True))

    # Create gemstones table
    op.create_table(
        'gemstones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('carat', sa.Float(), nullable=True),
        sa.Column('quality', sa.String(length=20), nullable=True),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('cut', sa.String(length=50), nullable=True),
        sa.Column('shape', sa.String(length=50), nullable=True),
        sa.Column('cost', sa.Float(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('total_cost', sa.Float(), nullable=True),
        sa.Column('setting_type', sa.String(length=100), nullable=True),
        sa.Column('certificate_number', sa.String(length=100), nullable=True),
        sa.Column('certificate_authority', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gemstones_id'), 'gemstones', ['id'], unique=False)
    op.create_index(op.f('ix_gemstones_order_id'), 'gemstones', ['order_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop gemstones table
    op.drop_index(op.f('ix_gemstones_order_id'), table_name='gemstones')
    op.drop_index(op.f('ix_gemstones_id'), table_name='gemstones')
    op.drop_table('gemstones')

    # Remove pricing fields
    op.drop_column('orders', 'calculated_price')
    op.drop_column('orders', 'vat_rate')
    op.drop_column('orders', 'profit_margin_percent')

    # Remove cost calculation fields
    op.drop_column('orders', 'labor_cost')
    op.drop_column('orders', 'hourly_rate')
    op.drop_column('orders', 'labor_hours')
    op.drop_column('orders', 'material_cost_override')
    op.drop_column('orders', 'material_cost_calculated')

    # Remove weight fields
    op.drop_column('orders', 'scrap_percentage')
    op.drop_column('orders', 'actual_weight_g')
    op.drop_column('orders', 'estimated_weight_g')
