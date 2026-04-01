"""Add 'birthday_reminder' value to notificationtypeenum

Revision ID: 7g8h9i0j1k2l
Revises: 6f7a8b9c0d1e
Create Date: 2026-04-01

Extends the ``notificationtypeenum`` PostgreSQL enum type with the value
``birthday_reminder`` to support the automated birthday marketing reminder
feature.

When the system monitor detects that a customer's birthday is tomorrow it
creates an in-app notification for ADMIN users prompting them to send a
gift voucher.

Rollback strategy:
  PostgreSQL does not support ``ALTER TYPE ... DROP VALUE``, so downgrade()
  is a no-op. The enum value ``birthday_reminder`` remains in the database
  but is harmless when unused. A full rollback requires recreating the enum
  type from scratch — see ARCHITECTURE_REVIEW.md on enum management.
"""

from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------

revision = "7g8h9i0j1k2l"
down_revision = "6f7a8b9c0d1e"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ADD VALUE is idempotent via IF NOT EXISTS.
    # PostgreSQL requires this statement to run outside a transaction block;
    # Alembic handles that automatically for DDL executed via op.execute().
    op.execute(
        "ALTER TYPE notificationtypeenum ADD VALUE IF NOT EXISTS 'birthday_reminder'"
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # PostgreSQL does not support ALTER TYPE ... DROP VALUE.
    # The 'birthday_reminder' enum value is left in place; it causes no harm
    # when the corresponding application code is not deployed.
    pass
