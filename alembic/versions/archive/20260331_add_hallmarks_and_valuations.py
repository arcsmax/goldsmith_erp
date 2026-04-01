"""Add hallmarking and valuation certificate tables (Punzierung + Wertgutachten)

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-03-31

Creates two tables:
  - order_hallmarks: tracks Punzierung (hallmarking) lifecycle per order
    with enum types for hallmark type (fineness, maker's mark, assay office,
    common control, date letter) and status (pending, submitted, approved,
    rejected, stamped).
  - valuation_certificates: Wertgutachten (insurance valuation certificates)
    with certificate number WG-YYYY-NNNN, appraised value, validity period
    (2 years), and goldsmith credentials.

Both are purely additive migrations — no existing tables are modified.

Domain notes (Thomas, Goldschmiedemeister):
  - Hallmarks: German Edelmetallgesetz requires Feingehaltsstempel on pieces
    above threshold weights.  The PENDING->SUBMITTED->APPROVED->STAMPED
    workflow mirrors the physical submission process to a Pruefstelle like
    Pforzheim or Schwaebisch Gmuend.
  - Valuation certificates: insurance-required documents stating replacement
    value (Wiederbeschaffungswert).  Valid 2 years per standard DE policy.
    appraised_value is financial data — access restricted to GOLDSMITH/ADMIN.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Enum type definitions — must match db/models.py exactly ──────────────────

_hallmark_type = sa.Enum(
    "fineness_mark",
    "makers_mark",
    "assay_office",
    "common_control",
    "date_letter",
    name="hallmarktype",
)

_hallmark_status = sa.Enum(
    "pending",
    "submitted",
    "approved",
    "rejected",
    "stamped",
    name="hallmarkstatus",
)


def upgrade() -> None:
    """Create order_hallmarks and valuation_certificates tables."""

    # -----------------------------------------------------------------------
    # 1. Create PostgreSQL enum types
    # -----------------------------------------------------------------------
    _hallmark_type.create(op.get_bind(), checkfirst=True)
    _hallmark_status.create(op.get_bind(), checkfirst=True)

    # -----------------------------------------------------------------------
    # 2. Create order_hallmarks table
    # -----------------------------------------------------------------------
    op.create_table(
        "order_hallmarks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hallmark_type", _hallmark_type, nullable=False),
        sa.Column(
            "status",
            _hallmark_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("assay_office", sa.String(length=100), nullable=True),
        sa.Column("certificate_number", sa.String(length=100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("stamped_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("certificate_number", name="uq_order_hallmarks_cert_number"),
    )

    # Indexes for order_hallmarks
    op.create_index("ix_order_hallmarks_id", "order_hallmarks", ["id"], unique=False)
    op.create_index(
        "ix_order_hallmarks_order_id", "order_hallmarks", ["order_id"], unique=False
    )
    op.create_index(
        "ix_order_hallmarks_hallmark_type",
        "order_hallmarks",
        ["hallmark_type"],
        unique=False,
    )
    op.create_index(
        "ix_order_hallmarks_status", "order_hallmarks", ["status"], unique=False
    )
    op.create_index(
        "ix_order_hallmarks_certificate_number",
        "order_hallmarks",
        ["certificate_number"],
        unique=True,
    )
    op.create_index(
        "ix_order_hallmarks_created_at",
        "order_hallmarks",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_order_hallmarks_created_by",
        "order_hallmarks",
        ["created_by"],
        unique=False,
    )

    # -----------------------------------------------------------------------
    # 3. Create valuation_certificates table
    # -----------------------------------------------------------------------
    op.create_table(
        "valuation_certificates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "certificate_number",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Item description
        sa.Column("item_description", sa.Text(), nullable=False),
        # Metal details
        sa.Column("metal_type", sa.String(length=100), nullable=True),
        sa.Column("metal_weight_g", sa.Float(), nullable=True),
        sa.Column("metal_purity", sa.String(length=20), nullable=True),
        # Gemstone summary
        sa.Column("gemstones_description", sa.Text(), nullable=True),
        # Appraised value (financial data — restricted access)
        sa.Column("appraised_value", sa.Float(), nullable=False),
        # Validity
        sa.Column(
            "valuation_date",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_until", sa.DateTime(), nullable=False),
        # Goldsmith credentials
        sa.Column("goldsmith_name", sa.String(length=200), nullable=False),
        sa.Column("goldsmith_qualification", sa.String(length=200), nullable=True),
        # Generated PDF path
        sa.Column("pdf_path", sa.String(length=500), nullable=True),
        # Audit timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "certificate_number", name="uq_valuation_certificates_cert_number"
        ),
    )

    # Indexes for valuation_certificates
    op.create_index(
        "ix_valuation_certificates_id", "valuation_certificates", ["id"], unique=False
    )
    op.create_index(
        "ix_valuation_certificates_certificate_number",
        "valuation_certificates",
        ["certificate_number"],
        unique=True,
    )
    op.create_index(
        "ix_valuation_certificates_order_id",
        "valuation_certificates",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        "ix_valuation_certificates_customer_id",
        "valuation_certificates",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        "ix_valuation_certificates_created_by",
        "valuation_certificates",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_valuation_certificates_valuation_date",
        "valuation_certificates",
        ["valuation_date"],
        unique=False,
    )
    op.create_index(
        "ix_valuation_certificates_valid_until",
        "valuation_certificates",
        ["valid_until"],
        unique=False,
    )
    op.create_index(
        "ix_valuation_certificates_created_at",
        "valuation_certificates",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop valuation_certificates and order_hallmarks tables."""

    # Drop valuation_certificates indexes
    op.drop_index("ix_valuation_certificates_created_at", table_name="valuation_certificates")
    op.drop_index("ix_valuation_certificates_valid_until", table_name="valuation_certificates")
    op.drop_index("ix_valuation_certificates_valuation_date", table_name="valuation_certificates")
    op.drop_index("ix_valuation_certificates_created_by", table_name="valuation_certificates")
    op.drop_index("ix_valuation_certificates_customer_id", table_name="valuation_certificates")
    op.drop_index("ix_valuation_certificates_order_id", table_name="valuation_certificates")
    op.drop_index(
        "ix_valuation_certificates_certificate_number", table_name="valuation_certificates"
    )
    op.drop_index("ix_valuation_certificates_id", table_name="valuation_certificates")
    op.drop_table("valuation_certificates")

    # Drop order_hallmarks indexes
    op.drop_index("ix_order_hallmarks_created_by", table_name="order_hallmarks")
    op.drop_index("ix_order_hallmarks_created_at", table_name="order_hallmarks")
    op.drop_index("ix_order_hallmarks_certificate_number", table_name="order_hallmarks")
    op.drop_index("ix_order_hallmarks_status", table_name="order_hallmarks")
    op.drop_index("ix_order_hallmarks_hallmark_type", table_name="order_hallmarks")
    op.drop_index("ix_order_hallmarks_order_id", table_name="order_hallmarks")
    op.drop_index("ix_order_hallmarks_id", table_name="order_hallmarks")
    op.drop_table("order_hallmarks")

    # Drop enum types
    _hallmark_status.drop(op.get_bind(), checkfirst=True)
    _hallmark_type.drop(op.get_bind(), checkfirst=True)
