"""Add notifications and notification_preferences tables

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-03-31

Creates two tables for the in-app notification system:

  notifications
    - Per-user persisted notifications (deadline warnings, pickup ready,
      low stock alerts, fitting reminders, order status changes, system msgs).
    - Scoped by user_id FK to users; also carries optional FKs to orders and
      customers for contextual deep-links in the frontend.
    - is_read + read_at support the unread-count badge and read receipts.
    - Real-time delivery is handled externally via Redis pub/sub; this table
      is the durable store for history and page-refresh recovery.

  notification_preferences
    - Per-user opt-in flags and advance_days settings for deadline warnings.
    - Enables future per-user configuration without schema changes.

Rollback strategy:
  downgrade() drops both tables and their supporting SA enum types in the
  correct dependency order.  Both tables are new — no existing data is at risk.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enum types (PostgreSQL native) ------------------------------------
    notification_type_enum = sa.Enum(
        "deadline_warning",
        "pickup_ready",
        "low_stock",
        "fitting_reminder",
        "order_status",
        "system",
        name="notificationtypeenum",
    )
    notification_severity_enum = sa.Enum(
        "info",
        "warning",
        "urgent",
        name="notificationseverityenum",
    )
    notification_type_enum.create(op.get_bind(), checkfirst=True)
    notification_severity_enum.create(op.get_bind(), checkfirst=True)

    # --- notifications table -----------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "notification_type",
            sa.Enum(
                "deadline_warning",
                "pickup_ready",
                "low_stock",
                "fitting_reminder",
                "order_status",
                "system",
                name="notificationtypeenum",
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum("info", "warning", "urgent", name="notificationseverityenum"),
            nullable=False,
            server_default="info",
        ),
        sa.Column("related_order_id", sa.Integer(), nullable=True),
        sa.Column("related_customer_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Primary key
        sa.PrimaryKeyConstraint("id"),
        # Foreign keys
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["related_order_id"], ["orders.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["related_customer_id"], ["customers.id"], ondelete="SET NULL"
        ),
    )
    # Indexes on the most-queried columns
    op.create_index("ix_notifications_id", "notifications", ["id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index(
        "ix_notifications_notification_type",
        "notifications",
        ["notification_type"],
    )
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index(
        "ix_notifications_related_order_id",
        "notifications",
        ["related_order_id"],
    )
    op.create_index(
        "ix_notifications_related_customer_id",
        "notifications",
        ["related_customer_id"],
    )

    # --- notification_preferences table ------------------------------------
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "notification_type",
            sa.Enum(
                "deadline_warning",
                "pickup_ready",
                "low_stock",
                "fitting_reminder",
                "order_status",
                "system",
                name="notificationtypeenum",
            ),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("advance_days", sa.Integer(), nullable=False, server_default="3"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_notification_preferences_id", "notification_preferences", ["id"]
    )
    op.create_index(
        "ix_notification_preferences_user_id",
        "notification_preferences",
        ["user_id"],
    )


def downgrade() -> None:
    # Drop tables first (FK dependencies), then enum types
    op.drop_index(
        "ix_notification_preferences_user_id",
        table_name="notification_preferences",
    )
    op.drop_index(
        "ix_notification_preferences_id",
        table_name="notification_preferences",
    )
    op.drop_table("notification_preferences")

    op.drop_index(
        "ix_notifications_related_customer_id", table_name="notifications"
    )
    op.drop_index(
        "ix_notifications_related_order_id", table_name="notifications"
    )
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index(
        "ix_notifications_notification_type", table_name="notifications"
    )
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_id", table_name="notifications")
    op.drop_table("notifications")

    # Drop enum types last
    sa.Enum(name="notificationseverityenum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notificationtypeenum").drop(op.get_bind(), checkfirst=True)
