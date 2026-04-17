"""add audit, gdpr, order items, status history, customer soft-delete, indexes

New tables: customer_audit_logs, gdpr_requests, order_items, order_status_history
New columns on customers: is_deleted, deleted_at, deleted_by, deletion_reason
New enum value: BIRTHDAY_REMINDER on NotificationTypeEnum
Composite indexes for common query patterns
UniqueConstraint on notification_preferences (user_id, notification_type)

DESIGN NOTE (2026-04-17)
========================
The parent migration (`v1_initial`) uses `Base.metadata.create_all()`, which
means fresh databases ALREADY contain every table / column / index / constraint
declared in the ORM — including the ones this migration was written to add.
Running `op.add_column` / `op.create_table` unconditionally against such a
fresh DB fails on SQLite (`duplicate column name`) and on PostgreSQL
(`DuplicateColumn` / `DuplicateTable`).

This migration therefore uses idempotent wrappers from `alembic.helpers` that
introspect the live bind before emitting DDL. The net effect:
  - Fresh DB (v1_initial just ran, ORM is authoritative):      all ops skipped.
  - Legacy DB (upgraded from a v1_initial that pre-dated these
    ORM additions):                                             ops performed.

Either path ends with an identical, consistent schema. This preserves
`Base.metadata.create_all()` as the canonical source of truth for fresh DBs
while keeping this migration useful for older deployments.

Revision ID: 20260406_review
Revises: v1_initial
Create Date: 2026-04-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

from goldsmith_erp.db.migration_helpers import (
    add_column_if_not_exists,
    create_fk_if_not_exists,
    create_index_if_not_exists,
    create_table_if_not_exists,
    create_unique_constraint_if_not_exists,
    drop_column_if_exists,
    drop_constraint_if_exists,
    drop_index_if_exists,
    drop_table_if_exists,
)

# revision identifiers, used by Alembic.
revision: str = "20260406_review"
down_revision: Union[str, None] = "v1_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Customer soft-delete columns
    # ------------------------------------------------------------------
    add_column_if_not_exists(
        "customers",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    )
    add_column_if_not_exists(
        "customers",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    add_column_if_not_exists(
        "customers",
        sa.Column("deleted_by", sa.Integer(), nullable=True),
    )
    create_fk_if_not_exists(
        "fk_customers_deleted_by_users",
        "customers",
        "users",
        ["deleted_by"],
        ["id"],
    )
    add_column_if_not_exists(
        "customers",
        sa.Column("deletion_reason", sa.String(500), nullable=True),
    )
    create_index_if_not_exists("ix_customers_is_deleted", "customers", ["is_deleted"])

    # ------------------------------------------------------------------
    # 2. CustomerAuditLog table
    # ------------------------------------------------------------------
    create_table_if_not_exists(
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
    create_table_if_not_exists(
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
    create_table_if_not_exists(
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
    create_table_if_not_exists(
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
    create_index_if_not_exists("ix_time_entries_end_time", "time_entries", ["end_time"])
    create_index_if_not_exists(
        "ix_notifications_user_read", "notifications", ["user_id", "is_read"]
    )
    create_index_if_not_exists(
        "ix_orders_customer_deleted", "orders", ["customer_id", "is_deleted"]
    )

    # ------------------------------------------------------------------
    # 7. UniqueConstraint on notification_preferences
    # ------------------------------------------------------------------
    create_unique_constraint_if_not_exists(
        "uq_notification_pref",
        "notification_preferences",
        ["user_id", "notification_type"],
    )

    # ------------------------------------------------------------------
    # 8. BIRTHDAY_REMINDER enum value on NotificationTypeEnum
    #    (PostgreSQL requires ALTER TYPE ... ADD VALUE; IF NOT EXISTS is
    #     safe to run even if the value is already present. SQLite stores
    #     enums as strings so this is a no-op there.)
    # ------------------------------------------------------------------
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE notificationtypeenum ADD VALUE IF NOT EXISTS 'birthday_reminder'"
        )


def downgrade() -> None:
    # NOTE: PostgreSQL does not support removing a value from an enum type.
    # The BIRTHDAY_REMINDER enum value will remain after downgrade.
    # To fully remove it, you would need to recreate the enum type.

    # 7. Drop unique constraint
    drop_constraint_if_exists(
        "uq_notification_pref", "notification_preferences", type_="unique"
    )

    # 6. Drop composite indexes
    drop_index_if_exists("ix_orders_customer_deleted", "orders")
    drop_index_if_exists("ix_notifications_user_read", "notifications")
    drop_index_if_exists("ix_time_entries_end_time", "time_entries")

    # 5. Drop order_status_history
    drop_table_if_exists("order_status_history")

    # 4. Drop order_items
    drop_table_if_exists("order_items")

    # 3. Drop gdpr_requests
    drop_table_if_exists("gdpr_requests")

    # 2. Drop customer_audit_logs
    drop_table_if_exists("customer_audit_logs")

    # 1. Drop customer soft-delete columns (reverse order of creation)
    drop_index_if_exists("ix_customers_is_deleted", "customers")
    drop_constraint_if_exists(
        "fk_customers_deleted_by_users", "customers", type_="foreignkey"
    )
    drop_column_if_exists("customers", "deletion_reason")
    drop_column_if_exists("customers", "deleted_by")
    drop_column_if_exists("customers", "deleted_at")
    drop_column_if_exists("customers", "is_deleted")
