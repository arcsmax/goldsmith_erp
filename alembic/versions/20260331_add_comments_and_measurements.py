"""Add order_comments table and customer measurement fields

Revision ID: 7a3f2b1c4d5e
Revises: 495e8f5a25fb
Create Date: 2026-03-31
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '7a3f2b1c4d5e'
down_revision: Union[str, None] = '495e8f5a25fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Order Comments (Digitale Post-its)
    op.create_table(
        'order_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_order_comments_id', 'order_comments', ['id'])
    op.create_index('ix_order_comments_order_id', 'order_comments', ['order_id'])
    op.create_index('ix_order_comments_user_id', 'order_comments', ['user_id'])
    op.create_index('ix_order_comments_created_at', 'order_comments', ['created_at'])

    # Customer Measurement Library (Mass-Bibliothek)
    op.add_column('customers', sa.Column('ring_size', sa.Float(), nullable=True))
    op.add_column('customers', sa.Column('chain_length_cm', sa.Float(), nullable=True))
    op.add_column('customers', sa.Column('bracelet_length_cm', sa.Float(), nullable=True))
    op.add_column('customers', sa.Column('allergies', sa.String(500), nullable=True))
    op.add_column('customers', sa.Column('preferences', sa.JSON(), nullable=True))
    op.add_column('customers', sa.Column('birthday', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('customers', 'birthday')
    op.drop_column('customers', 'preferences')
    op.drop_column('customers', 'allergies')
    op.drop_column('customers', 'bracelet_length_cm')
    op.drop_column('customers', 'chain_length_cm')
    op.drop_column('customers', 'ring_size')

    op.drop_index('ix_order_comments_created_at', table_name='order_comments')
    op.drop_index('ix_order_comments_user_id', table_name='order_comments')
    op.drop_index('ix_order_comments_order_id', table_name='order_comments')
    op.drop_index('ix_order_comments_id', table_name='order_comments')
    op.drop_table('order_comments')
