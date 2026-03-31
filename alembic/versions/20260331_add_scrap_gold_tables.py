"""Add scrap_gold and scrap_gold_items tables

Revision ID: 8b4c3d2e5f6a
Revises: 7a3f2b1c4d5e
Create Date: 2026-03-31
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '8b4c3d2e5f6a'
down_revision: Union[str, None] = '7a3f2b1c4d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Scrap Gold Status enum
    scrap_gold_status = sa.Enum('received', 'calculated', 'signed', 'credited', name='scrapgoldstatus')
    scrap_gold_status.create(op.get_bind(), checkfirst=True)

    # Alloy Type enum
    alloy_type = sa.Enum(
        '999', '900', '750', '585', '375', '333',
        'ag999', 'ag925', 'ag800', 'pt950',
        name='alloytype'
    )
    alloy_type.create(op.get_bind(), checkfirst=True)

    # Scrap Gold table
    op.create_table(
        'scrap_gold',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('status', scrap_gold_status, server_default='received', nullable=False),
        sa.Column('total_fine_gold_g', sa.Float(), server_default='0.0'),
        sa.Column('total_value_eur', sa.Float(), server_default='0.0'),
        sa.Column('gold_price_per_g', sa.Float(), nullable=True),
        sa.Column('price_source', sa.String(50), server_default='fixed_rate'),
        sa.Column('signature_data', sa.Text(), nullable=True),
        sa.Column('signed_at', sa.DateTime(), nullable=True),
        sa.Column('receipt_pdf_path', sa.String(500), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_scrap_gold_id', 'scrap_gold', ['id'])
    op.create_index('ix_scrap_gold_order_id', 'scrap_gold', ['order_id'])
    op.create_index('ix_scrap_gold_customer_id', 'scrap_gold', ['customer_id'])

    # Scrap Gold Items table
    op.create_table(
        'scrap_gold_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scrap_gold_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(200), nullable=False),
        sa.Column('alloy', alloy_type, nullable=False),
        sa.Column('weight_g', sa.Float(), nullable=False),
        sa.Column('fine_content_g', sa.Float(), nullable=False),
        sa.Column('photo_path', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['scrap_gold_id'], ['scrap_gold.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_scrap_gold_items_id', 'scrap_gold_items', ['id'])
    op.create_index('ix_scrap_gold_items_scrap_gold_id', 'scrap_gold_items', ['scrap_gold_id'])


def downgrade() -> None:
    op.drop_index('ix_scrap_gold_items_scrap_gold_id', table_name='scrap_gold_items')
    op.drop_index('ix_scrap_gold_items_id', table_name='scrap_gold_items')
    op.drop_table('scrap_gold_items')

    op.drop_index('ix_scrap_gold_customer_id', table_name='scrap_gold')
    op.drop_index('ix_scrap_gold_order_id', table_name='scrap_gold')
    op.drop_index('ix_scrap_gold_id', table_name='scrap_gold')
    op.drop_table('scrap_gold')

    sa.Enum(name='alloytype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='scrapgoldstatus').drop(op.get_bind(), checkfirst=True)
