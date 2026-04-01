"""Add order_handoffs table and handoff/HANDOFF enum values

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2026-03-31

Creates the ``order_handoffs`` table for the Stabuebergabe (handoff protocol).

A handoff represents the formal moment a goldsmith finishes their part of an
order and passes it to the next craftsperson.  The receiving goldsmith must
explicitly accept or decline before the order changes hands in the system.

Schema changes:
  - New table: order_handoffs
      id, order_id, from_user_id, to_user_id, handoff_type, status,
      notes, response_notes, created_at, responded_at

  - New enum: handofftypeenum
      pass_to_next, request_review, return_for_rework, mark_complete

  - New enum: handoffstatusenum
      pending, accepted, declined

  - Altered enum: notificationtypeenum — adds the value ``handoff``

Indexes:
  - ix_order_handoffs_order_id
  - ix_order_handoffs_from_user_id
  - ix_order_handoffs_to_user_id
  - ix_order_handoffs_status
  - ix_order_handoffs_handoff_type
  - ix_order_handoffs_created_at
"""

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------

revision = "4d5e6f7a8b9c"
down_revision = "3c4d5e6f7a8b"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Enum type definitions
# ---------------------------------------------------------------------------

handoff_type_enum = sa.Enum(
    "pass_to_next",
    "request_review",
    "return_for_rework",
    "mark_complete",
    name="handofftypeenum",
)

handoff_status_enum = sa.Enum(
    "pending",
    "accepted",
    "declined",
    name="handoffstatusenum",
)


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # Create new enum types
    handoff_type_enum.create(op.get_bind(), checkfirst=True)
    handoff_status_enum.create(op.get_bind(), checkfirst=True)

    # Add 'handoff' value to existing notificationtypeenum.
    # PostgreSQL requires ALTER TYPE … ADD VALUE outside of a transaction block.
    # Alembic runs each migration in a transaction by default, so we use
    # execute_if to guard against duplicate adds on re-runs.
    op.execute(
        "ALTER TYPE notificationtypeenum ADD VALUE IF NOT EXISTS 'handoff'"
    )

    # Create order_handoffs table
    op.create_table(
        "order_handoffs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "handoff_type",
            sa.Enum(
                "pass_to_next",
                "request_review",
                "return_for_rework",
                "mark_complete",
                name="handofftypeenum",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "accepted",
                "declined",
                name="handoffstatusenum",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("response_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes
    op.create_index("ix_order_handoffs_order_id", "order_handoffs", ["order_id"])
    op.create_index("ix_order_handoffs_from_user_id", "order_handoffs", ["from_user_id"])
    op.create_index("ix_order_handoffs_to_user_id", "order_handoffs", ["to_user_id"])
    op.create_index("ix_order_handoffs_status", "order_handoffs", ["status"])
    op.create_index("ix_order_handoffs_handoff_type", "order_handoffs", ["handoff_type"])
    op.create_index("ix_order_handoffs_created_at", "order_handoffs", ["created_at"])


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Remove indexes
    op.drop_index("ix_order_handoffs_created_at", table_name="order_handoffs")
    op.drop_index("ix_order_handoffs_handoff_type", table_name="order_handoffs")
    op.drop_index("ix_order_handoffs_status", table_name="order_handoffs")
    op.drop_index("ix_order_handoffs_to_user_id", table_name="order_handoffs")
    op.drop_index("ix_order_handoffs_from_user_id", table_name="order_handoffs")
    op.drop_index("ix_order_handoffs_order_id", table_name="order_handoffs")

    # Drop table
    op.drop_table("order_handoffs")

    # Drop enum types
    # Note: 'handoff' added to notificationtypeenum cannot be safely removed
    # via ALTER TYPE … DROP VALUE in PostgreSQL (not supported).
    # The enum value remains but is harmless if unused.
    handoff_status_enum.drop(op.get_bind(), checkfirst=True)
    handoff_type_enum.drop(op.get_bind(), checkfirst=True)
