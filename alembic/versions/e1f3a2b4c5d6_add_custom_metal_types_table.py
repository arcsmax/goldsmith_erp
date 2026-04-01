"""add_custom_metal_types_table

Revision ID: e1f3a2b4c5d6
Revises: d2d180a82769
Create Date: 2026-03-31 10:00:00.000000

Adds the custom_metal_types table so that goldsmith admins can define
workshop-specific alloys (e.g. "Rotgold 333", supplier alloys) beyond
the 15 hardcoded MetalType enum values.

Rollback strategy:
    downgrade() drops the table entirely.  This is safe because no other
    table has a FK dependency on custom_metal_types — the metal_type column
    on metal_purchases uses the MetalType SQLAlchemy enum (built-ins only).
    Any custom-type entries are lost on downgrade; the user is expected to
    re-enter them after an upgrade retry.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f3a2b4c5d6'
down_revision: Union[str, None] = 'd2d180a82769'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create custom_metal_types table."""
    op.create_table(
        'custom_metal_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('fine_content_ratio', sa.Float(), nullable=False),
        sa.Column('base_metal', sa.String(length=20), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_custom_metal_types_id', 'custom_metal_types', ['id'], unique=False)
    op.create_index('ix_custom_metal_types_code', 'custom_metal_types', ['code'], unique=True)
    op.create_index('ix_custom_metal_types_is_active', 'custom_metal_types', ['is_active'], unique=False)


def downgrade() -> None:
    """Drop custom_metal_types table."""
    op.drop_index('ix_custom_metal_types_is_active', table_name='custom_metal_types')
    op.drop_index('ix_custom_metal_types_code', table_name='custom_metal_types')
    op.drop_index('ix_custom_metal_types_id', table_name='custom_metal_types')
    op.drop_table('custom_metal_types')
