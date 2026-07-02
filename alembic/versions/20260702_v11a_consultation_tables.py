"""V1.1a — Consultation & intake tables (consultations, consultation_photos,
customer_no_gos), Customer.style_profile, notification enum value."""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260702_v11a_consultation"
down_revision: Union[str, None] = "20260527_d1_activity_billable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        create_table_if_not_exists,
    )

    create_table_if_not_exists(
        "consultations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "conducted_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "calendar_event_id",
            sa.Integer(),
            sa.ForeignKey("calendar_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("occasion", sa.String(30), nullable=False, server_default="other"),
        sa.Column("occasion_date", sa.Date(), nullable=True),
        sa.Column("budget_min", sa.Float(), nullable=True),
        sa.Column("budget_max", sa.Float(), nullable=True),
        sa.Column("piece_type", sa.String(30), nullable=True),
        sa.Column("wishes", sa.Text(), nullable=True),
        sa.Column("materials_discussed", sa.JSON(), nullable=True),
        sa.Column("source_material", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "converted_quote_id",
            sa.Integer(),
            sa.ForeignKey("quotes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "converted_order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("follow_up_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    create_table_if_not_exists(
        "consultation_photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "consultation_id",
            sa.Integer(),
            sa.ForeignKey("consultations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("kind", sa.String(20), nullable=False, server_default="sketch"),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column(
            "taken_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    create_table_if_not_exists(
        "customer_no_gos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("value", sa.String(200), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "source_consultation_id",
            sa.Integer(),
            sa.ForeignKey("consultations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    add_column_if_not_exists(
        "customers", sa.Column("style_profile", sa.JSON(), nullable=True)
    )

    # PostgreSQL stores NotificationTypeEnum as a native enum; SQLite as strings.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE notificationtypeenum ADD VALUE IF NOT EXISTS 'consultation_followup'"
        )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        drop_table_if_exists,
    )

    drop_column_if_exists("customers", "style_profile")
    drop_table_if_exists("consultation_photos")
    drop_table_if_exists("customer_no_gos")
    drop_table_if_exists("consultations")
    # Postgres enum values cannot be removed; leaving 'consultation_followup' is harmless.
