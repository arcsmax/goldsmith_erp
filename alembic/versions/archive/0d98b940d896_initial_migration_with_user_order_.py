"""Initial migration with User, Order, Material models

Revision ID: 0d98b940d896
Revises:
Create Date: 2025-11-09 06:18:22.517023

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d98b940d896'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create OrderStatusEnum
    order_status_enum = sa.Enum('NEW', 'IN_PROGRESS', 'COMPLETED', 'DELIVERED',
                                 name='orderstatusenum', create_type=True)

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=True),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # Create materials table
    op.create_table(
        'materials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('unit_price', sa.Float(), nullable=True),
        sa.Column('stock', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_materials_id'), 'materials', ['id'], unique=False)
    op.create_index(op.f('ix_materials_name'), 'materials', ['name'], unique=False)

    # Create orders table
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('status', order_status_enum, nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_id'), 'orders', ['id'], unique=False)

    # Create order_materials junction table
    op.create_table(
        'order_materials',
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('material_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['material_id'], ['materials.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.PrimaryKeyConstraint('order_id', 'material_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop tables in reverse order
    op.drop_table('order_materials')
    op.drop_index(op.f('ix_orders_id'), table_name='orders')
    op.drop_table('orders')
    op.drop_index(op.f('ix_materials_name'), table_name='materials')
    op.drop_index(op.f('ix_materials_id'), table_name='materials')
    op.drop_table('materials')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

    # Drop the enum type
    sa.Enum(name='orderstatusenum').drop(op.get_bind(), checkfirst=True)
