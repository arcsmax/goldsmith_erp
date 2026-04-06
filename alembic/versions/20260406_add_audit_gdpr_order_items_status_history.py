"""add audit, gdpr, order items, status history, customer soft-delete, indexes

New tables: customer_audit_logs, gdpr_requests, order_items, order_status_history
New columns on customers: is_deleted, deleted_at, deleted_by, deletion_reason
New enum value: BIRTHDAY_REMINDER on NotificationTypeEnum
Composite indexes for common query patterns
UniqueConstraint on notification_preferences (user_id, notification_type)

NOTE: The parent migration (v1_initial) uses Base.metadata.create_all(), which
means fresh databases will already have these tables/columns.  This migration
is for databases that were created before these models were added to models.py.
If running against a freshly-created DB you may need to stamp this revision:
    alembic stamp 20260406_review

Revision ID: 20260406_review
Revises: v1_initial
Create Date: 2026-04-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision: str = "20260406_review"
down_revision: Union[str, None] = "v1_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Customer soft-delete columns
    # ------------------------------------------------------------------
    op.add_column(
        "customers",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "customers",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("deleted_by", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_customers_deleted_by_users",
        "customers",
        "users",
        ["deleted_by"],
        ["id"],
    )
    op.add_column(
        "customers",
        sa.Column("deletion_reason", sa.String(500), nullable=True),
    )
    op.create_index("ix_customers_is_deleted", "customers", ["is_deleted"])

    # ------------------------------------------------------------------
    # 2. CustomerAuditLog table
    # ------------------------------------------------------------------
    op.create_table(
        "customer_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("user_role", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("details", JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 3. GDPRRequest table
    # ------------------------------------------------------------------
    op.create_table(
        "gdpr_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("request_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "requested_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # ------------------------------------------------------------------
    # 4. OrderItem table
    # ------------------------------------------------------------------
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Float(), nullable=True),
        sa.Column(
            "material_id",
            sa.Integer(),
            sa.ForeignKey("materials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # ------------------------------------------------------------------
    # 5. OrderStatusHistory table
    # ------------------------------------------------------------------
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("from_status", sa.String(50), nullable=True),
        sa.Column("to_status", sa.String(50), nullable=False),
        sa.Column(
            "changed_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
    )

    # ------------------------------------------------------------------
    # 6. Performance indexes for common query patterns
    # ------------------------------------------------------------------
    op.create_index("ix_time_entries_end_time", "time_entries", ["end_time"])
    op.create_index(
        "ix_notifications_user_read", "notifications", ["user_id", "is_read"]
    )
    op.create_index(
        "ix_orders_customer_deleted", "orders", ["customer_id", "is_deleted"]
    )

    # ------------------------------------------------------------------
    # 7. UniqueConstraint on notification_preferences
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_notification_pref",
        "notification_preferences",
        ["user_id", "notification_type"],
    )

    # ------------------------------------------------------------------
    # 8. BIRTHDAY_REMINDER enum value on NotificationTypeEnum
    #    (PostgreSQL requires ALTER TYPE ... ADD VALUE; IF NOT EXISTS is
    #     safe to run even if the value is already present.)
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TYPE notificationtypeenum ADD VALUE IF NOT EXISTS 'birthday_reminder'"
    )


def downgrade() -> None:
    # NOTE: PostgreSQL does not support removing a value from an enum type.
    # The BIRTHDAY_REMINDER enum value will remain after downgrade.
    # To fully remove it, you would need to recreate the enum type.

    # 7. Drop unique constraint
    op.drop_constraint("uq_notification_pref", "notification_preferences", type_="unique")

    # 6. Drop composite indexes
    op.drop_index("ix_orders_customer_deleted", table_name="orders")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_index("ix_time_entries_end_time", table_name="time_entries")

    # 5. Drop order_status_history
    op.drop_table("order_status_history")

    # 4. Drop order_items
    op.drop_table("order_items")

    # 3. Drop gdpr_requests
    op.drop_table("gdpr_requests")

    # 2. Drop customer_audit_logs
    op.drop_table("customer_audit_logs")

    # 1. Drop customer soft-delete columns (reverse order of creation)
    op.drop_index("ix_customers_is_deleted", table_name="customers")
    op.drop_constraint("fk_customers_deleted_by_users", "customers", type_="foreignkey")
    op.drop_column("customers", "deletion_reason")
    op.drop_column("customers", "deleted_by")
    op.drop_column("customers", "deleted_at")
    op.drop_column("customers", "is_deleted")
