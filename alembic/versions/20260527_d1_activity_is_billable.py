"""D1 — Add Activity.is_billable with sensible category defaults.

Adds a per-activity billable flag used by GET /time-tracking/summary to
compute billable_hours. New column defaults to true (server_default) so
existing rows backfill non-destructively; a follow-up UPDATE applies the
sensible workshop default — administration and waiting activities are
non-billable, fabrication stays billable.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260527_d1_activity_billable"
down_revision: Union[str, None] = "20260424_c3_val_enc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # On fresh DBs the v1_initial migration creates `activities` via
    # `Base.metadata.create_all` over the live ORM, which already includes
    # `is_billable` once this column exists in db/models.Activity. Guard the
    # add against that "leak" so the upgrade is idempotent (matches the
    # `column_exists` pattern used by 20260424_c1_pii_enc for email_hash).
    # Legacy DBs lacking the column still get it added here.
    from goldsmith_erp.db.migration_helpers import column_exists  # noqa: PLC0415

    if not column_exists("activities", "is_billable"):
        op.add_column(
            "activities",
            sa.Column(
                "is_billable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
    # Sensible defaults: overhead categories are non-billable.
    op.execute(
        "UPDATE activities SET is_billable = false "
        "WHERE category IN ('administration', 'waiting')"
    )


def downgrade() -> None:
    op.drop_column("activities", "is_billable")
