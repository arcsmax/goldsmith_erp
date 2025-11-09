"""add time tracking tables

Revision ID: a35005826b5d
Revises: 0d98b940d896
Create Date: 2025-11-09 08:02:45.894330

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a35005826b5d'
down_revision: Union[str, None] = '0d98b940d896'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create activities table
    op.create_table(
        'activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('icon', sa.String(length=10), nullable=True),
        sa.Column('color', sa.String(length=7), nullable=True),
        sa.Column('usage_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('average_duration_minutes', sa.Float(), nullable=True),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('is_custom', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activities_category'), 'activities', ['category'], unique=False)
    op.create_index(op.f('ix_activities_usage_count'), 'activities', ['usage_count'], unique=False)

    # Create time_entries table
    op.create_table(
        'time_entries',
        sa.Column('id', sa.String(length=36), nullable=False),  # UUID as string
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('activity_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('location', sa.String(length=50), nullable=True),
        sa.Column('complexity_rating', sa.Integer(), nullable=True),
        sa.Column('quality_rating', sa.Integer(), nullable=True),
        sa.Column('rework_required', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('extra_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_time_entries_activity_id'), 'time_entries', ['activity_id'], unique=False)
    op.create_index(op.f('ix_time_entries_order_id'), 'time_entries', ['order_id'], unique=False)
    op.create_index(op.f('ix_time_entries_start_time'), 'time_entries', ['start_time'], unique=False)
    op.create_index(op.f('ix_time_entries_user_id'), 'time_entries', ['user_id'], unique=False)

    # Create interruptions table
    op.create_table(
        'interruptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('time_entry_id', sa.String(length=36), nullable=False),
        sa.Column('reason', sa.String(length=100), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['time_entry_id'], ['time_entries.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interruptions_time_entry_id'), 'interruptions', ['time_entry_id'], unique=False)

    # Create location_history table
    op.create_table(
        'location_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('location', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('changed_by', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_location_history_order_id'), 'location_history', ['order_id'], unique=False)
    op.create_index(op.f('ix_location_history_timestamp'), 'location_history', ['timestamp'], unique=False)

    # Create order_photos table
    op.create_table(
        'order_photos',
        sa.Column('id', sa.String(length=36), nullable=False),  # UUID as string
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('time_entry_id', sa.String(length=36), nullable=True),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('taken_by', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['taken_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['time_entry_id'], ['time_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_photos_order_id'), 'order_photos', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_photos_timestamp'), 'order_photos', ['timestamp'], unique=False)

    # Add current_location column to orders table
    op.add_column('orders', sa.Column('current_location', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop current_location from orders
    op.drop_column('orders', 'current_location')

    # Drop tables in reverse order
    op.drop_index(op.f('ix_order_photos_timestamp'), table_name='order_photos')
    op.drop_index(op.f('ix_order_photos_order_id'), table_name='order_photos')
    op.drop_table('order_photos')

    op.drop_index(op.f('ix_location_history_timestamp'), table_name='location_history')
    op.drop_index(op.f('ix_location_history_order_id'), table_name='location_history')
    op.drop_table('location_history')

    op.drop_index(op.f('ix_interruptions_time_entry_id'), table_name='interruptions')
    op.drop_table('interruptions')

    op.drop_index(op.f('ix_time_entries_user_id'), table_name='time_entries')
    op.drop_index(op.f('ix_time_entries_start_time'), table_name='time_entries')
    op.drop_index(op.f('ix_time_entries_order_id'), table_name='time_entries')
    op.drop_index(op.f('ix_time_entries_activity_id'), table_name='time_entries')
    op.drop_table('time_entries')

    op.drop_index(op.f('ix_activities_usage_count'), table_name='activities')
    op.drop_index(op.f('ix_activities_category'), table_name='activities')
    op.drop_table('activities')
