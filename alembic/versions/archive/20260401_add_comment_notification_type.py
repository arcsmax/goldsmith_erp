"""Add 'comment' value to notificationtypeenum

Revision ID: 6f7a8b9c0d1e
Revises: 5e6f7a8b9c0d
Create Date: 2026-04-01

Extends the ``notificationtypeenum`` PostgreSQL enum type with the value
``comment`` to support the Digital Post-it notification feature.

When a goldsmith writes a comment on an order the system now fires an
in-app notification to every active ADMIN and GOLDSMITH user who is NOT
the comment author (office <-> workshop cross-notification).

Rollback strategy:
  PostgreSQL does not support ``ALTER TYPE … DROP VALUE``, so downgrade()
  is a no-op.  The enum value ``comment`` remains in the database but is
  harmless when unused.  If a full rollback is required, recreate the enum
  type from scratch — see the note in the ARCHITECTURE_REVIEW.md on enum
  management.
"""

from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------

revision = "6f7a8b9c0d1e"
down_revision = "5e6f7a8b9c0d"
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
        "ALTER TYPE notificationtypeenum ADD VALUE IF NOT EXISTS 'comment'"
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # PostgreSQL does not support ALTER TYPE … DROP VALUE.
    # The 'comment' enum value is left in place; it causes no harm
    # when the corresponding application code is not deployed.
    pass
