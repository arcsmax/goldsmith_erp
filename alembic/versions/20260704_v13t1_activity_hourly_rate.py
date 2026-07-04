"""V1.3 Estimator Task 1 — Activity.hourly_rate (per-activity labor rate).

Adds a nullable per-activity hourly rate (EUR/hour) so labor cost can be
computed per activity instead of a single shop-wide rate (product decision,
2026-07-04: per-activity rates, not one shop rate). NULL means "use the shop
default" — CostCalculationService falls back to settings.DEFAULT_HOURLY_RATE
(currently 75 EUR/h) when an activity's rate is unset. Additive column only,
no data backfill.

Idempotency
-----------
``activities`` is created via ``Base.metadata.create_all()`` in
``v1_initial`` (it is not in that migration's ``POST_V1_TABLES`` exclusion
list), so once ``Activity.hourly_rate`` exists on the ORM, fresh DBs already
have the column before this migration runs. ``add_column_if_not_exists``
makes the upgrade a no-op there and only adds the column on legacy DBs that
pre-date this change — mirrors the guard added in
20260527_d1_activity_is_billable.py.

Revision ID: 20260704_v13t1_hourly_rate
Revises: 20260703_v12a_cust_updates
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260704_v13t1_hourly_rate"
down_revision: Union[str, None] = "20260703_v12a_cust_updates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
    )

    add_column_if_not_exists(
        "activities",
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
    )

    drop_column_if_exists("activities", "hourly_rate")
