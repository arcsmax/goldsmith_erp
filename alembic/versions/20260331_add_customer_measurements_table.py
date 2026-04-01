"""Add customer_measurements table (Massbibliothek)

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-03-31

Adds a dedicated customer_measurements table replacing the single-value
ring_size / chain_length_cm / bracelet_length_cm columns on the customers
table.  The new table supports:
  - Multiple measurement types per customer (ring sizes per finger/hand,
    chain lengths, wrist/neck/ankle circumferences)
  - Per-hand, per-finger granularity for rings
  - Goldsmith provenance: who measured, when
  - Free-text fitting notes ("Knöchel etwas breiter")

German EU ring sizes (Ringmassstab): inner circumference in mm, range 38-80.
Practical customer range: 48-70.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums first (PostgreSQL requires explicit enum creation)
    measurement_type_enum = sa.Enum(
        "ring_size",
        "chain_length",
        "wrist_circumference",
        "finger_circumference",
        "neck_circumference",
        "ankle_circumference",
        name="measurementtype",
    )
    hand_side_enum = sa.Enum("left", "right", name="handside")
    finger_position_enum = sa.Enum(
        "thumb", "index", "middle", "ring", "pinky", name="fingerposition"
    )
    measurement_type_enum.create(op.get_bind(), checkfirst=True)
    hand_side_enum.create(op.get_bind(), checkfirst=True)
    finger_position_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "customer_measurements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("measured_by", sa.Integer(), nullable=True),
        sa.Column(
            "measurement_type",
            sa.Enum(
                "ring_size",
                "chain_length",
                "wrist_circumference",
                "finger_circumference",
                "neck_circumference",
                "ankle_circumference",
                name="measurementtype",
            ),
            nullable=False,
        ),
        # The numeric value — mm for ring sizes, cm for lengths
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        # Ring-specific anatomy fields
        sa.Column(
            "hand",
            sa.Enum("left", "right", name="handside"),
            nullable=True,
        ),
        sa.Column(
            "finger",
            sa.Enum("thumb", "index", "middle", "ring", "pinky", name="fingerposition"),
            nullable=True,
        ),
        # Goldsmith fitting notes
        sa.Column("notes", sa.Text(), nullable=True),
        # When the physical measurement was taken
        sa.Column("measured_at", sa.DateTime(), nullable=False),
        # Audit timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # Constraints
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["measured_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes for common query patterns
    op.create_index(
        "ix_customer_measurements_id",
        "customer_measurements",
        ["id"],
    )
    op.create_index(
        "ix_customer_measurements_customer_id",
        "customer_measurements",
        ["customer_id"],
    )
    op.create_index(
        "ix_customer_measurements_measurement_type",
        "customer_measurements",
        ["measurement_type"],
    )
    op.create_index(
        "ix_customer_measurements_measured_at",
        "customer_measurements",
        ["measured_at"],
    )
    # Composite index for the ring-size quick lookup
    # (customer_id, type, hand, finger) -> most recent row
    op.create_index(
        "ix_customer_measurements_ring_lookup",
        "customer_measurements",
        ["customer_id", "measurement_type", "hand", "finger"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_measurements_ring_lookup",
        table_name="customer_measurements",
    )
    op.drop_index(
        "ix_customer_measurements_measured_at",
        table_name="customer_measurements",
    )
    op.drop_index(
        "ix_customer_measurements_measurement_type",
        table_name="customer_measurements",
    )
    op.drop_index(
        "ix_customer_measurements_customer_id",
        table_name="customer_measurements",
    )
    op.drop_index(
        "ix_customer_measurements_id",
        table_name="customer_measurements",
    )
    op.drop_table("customer_measurements")

    # Drop enums (PostgreSQL only)
    op.execute("DROP TYPE IF EXISTS fingerposition")
    op.execute("DROP TYPE IF EXISTS handside")
    op.execute("DROP TYPE IF EXISTS measurementtype")
