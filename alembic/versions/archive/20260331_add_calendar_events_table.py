"""Add calendar_events table for workshop planning/scheduling

Revision ID: 9c5d4e3f2a1b
Revises: 8b4c3d2e5f6a
Create Date: 2026-03-31

Creates the calendar_events table with:
  - CalendarEventType enum (order_deadline, workshop_task, appointment, reminder)
  - Time range columns (start_datetime, end_datetime, all_day)
  - Optional FK to orders (SET NULL on delete — events survive order deletion)
  - Mandatory FK to users (CASCADE on delete — events removed with user)
  - UI helper columns (color, recurrence)
  - Audit timestamps (created_at, updated_at)

Rollback strategy:
  downgrade() drops the table and the enum type cleanly.
  No existing data is affected; this is a purely additive migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '9c5d4e3f2a1b'
down_revision: Union[str, None] = '8b4c3d2e5f6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum values must match CalendarEventType in db/models.py exactly.
_calendar_event_type = sa.Enum(
    'order_deadline',
    'workshop_task',
    'appointment',
    'reminder',
    name='calendareventtype',
)


def upgrade() -> None:
    # Create the enum type first (PostgreSQL requires an explicit CREATE TYPE)
    _calendar_event_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'calendar_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'event_type',
            _calendar_event_type,
            nullable=False,
        ),
        sa.Column('start_datetime', sa.DateTime(), nullable=False),
        sa.Column('end_datetime', sa.DateTime(), nullable=True),
        sa.Column('all_day', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=True),
        sa.Column('recurrence', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        # Primary key
        sa.PrimaryKeyConstraint('id'),
        # Foreign keys
        sa.ForeignKeyConstraint(
            ['order_id'],
            ['orders.id'],
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            ondelete='CASCADE',
        ),
    )

    # Indexes for common query patterns
    op.create_index('ix_calendar_events_id', 'calendar_events', ['id'], unique=False)
    op.create_index('ix_calendar_events_start_datetime', 'calendar_events', ['start_datetime'], unique=False)
    op.create_index('ix_calendar_events_event_type', 'calendar_events', ['event_type'], unique=False)
    op.create_index('ix_calendar_events_order_id', 'calendar_events', ['order_id'], unique=False)
    op.create_index('ix_calendar_events_user_id', 'calendar_events', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_calendar_events_user_id', table_name='calendar_events')
    op.drop_index('ix_calendar_events_order_id', table_name='calendar_events')
    op.drop_index('ix_calendar_events_event_type', table_name='calendar_events')
    op.drop_index('ix_calendar_events_start_datetime', table_name='calendar_events')
    op.drop_index('ix_calendar_events_id', table_name='calendar_events')
    op.drop_table('calendar_events')

    _calendar_event_type.drop(op.get_bind(), checkfirst=True)
