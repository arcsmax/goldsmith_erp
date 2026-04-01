"""add_quote_tables

Adds the quotes and quote_line_items tables for the Kostenvoranschlag feature.

Revision ID: f3a8b2c1d9e0
Revises: e1f3a2b4c5d6
Create Date: 2026-03-31 10:00:00.000000

Rollback strategy:
  downgrade() drops both tables atomically with CASCADE.
  No data migration required — tables are new.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "f3a8b2c1d9e0"
down_revision = "e1f3a2b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── quotes ────────────────────────────────────────────────────────────────
    op.create_table(
        "quotes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quote_number", sa.String(length=20), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "sent",
                "approved",
                "rejected",
                "expired",
                "converted",
                name="quotestatus",
            ),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("valid_until", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("converted_at", sa.DateTime(), nullable=True),
        sa.Column("subtotal", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("tax_rate", sa.Float(), nullable=False, server_default="19.0"),
        sa.Column("tax_amount", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("customer_signature_data", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quotes_id"), "quotes", ["id"], unique=False)
    op.create_index(op.f("ix_quotes_quote_number"), "quotes", ["quote_number"], unique=True)
    op.create_index(op.f("ix_quotes_customer_id"), "quotes", ["customer_id"], unique=False)
    op.create_index(op.f("ix_quotes_order_id"), "quotes", ["order_id"], unique=False)
    op.create_index(op.f("ix_quotes_status"), "quotes", ["status"], unique=False)
    op.create_index(op.f("ix_quotes_valid_until"), "quotes", ["valid_until"], unique=False)

    # ── quote_line_items ──────────────────────────────────────────────────────
    op.create_table(
        "quote_line_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quote_id", sa.Integer(), nullable=False),
        sa.Column(
            "line_type",
            sa.Enum("material", "labor", "gemstone", "other", name="quotelinetype"),
            nullable=False,
            server_default="other",
        ),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("total", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["quote_id"], ["quotes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quote_line_items_id"), "quote_line_items", ["id"], unique=False)
    op.create_index(op.f("ix_quote_line_items_quote_id"), "quote_line_items", ["quote_id"], unique=False)


def downgrade() -> None:
    # Drop in reverse dependency order — line items first, then quotes
    op.drop_index(op.f("ix_quote_line_items_quote_id"), table_name="quote_line_items")
    op.drop_index(op.f("ix_quote_line_items_id"), table_name="quote_line_items")
    op.drop_table("quote_line_items")

    op.drop_index(op.f("ix_quotes_valid_until"), table_name="quotes")
    op.drop_index(op.f("ix_quotes_status"), table_name="quotes")
    op.drop_index(op.f("ix_quotes_order_id"), table_name="quotes")
    op.drop_index(op.f("ix_quotes_customer_id"), table_name="quotes")
    op.drop_index(op.f("ix_quotes_quote_number"), table_name="quotes")
    op.drop_index(op.f("ix_quotes_id"), table_name="quotes")
    op.drop_table("quotes")

    # Drop the PostgreSQL enum types created above
    sa.Enum(name="quotestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="quotelinetype").drop(op.get_bind(), checkfirst=True)
