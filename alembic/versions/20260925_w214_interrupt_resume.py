"""W2-14 (BE-19): interruptions get an end, so they can reduce time.

Adds ``interruptions.resumed_at`` (nullable). A scan interruption is written
with ``duration_minutes = 0`` when it starts; the next scan on the running
timer (activity change, next interruption, switch or stop) closes it: it sets
``resumed_at`` and the measured ``duration_minutes``. Every consumer that
nets interruptions out of ``time_entries.duration_minutes``
(``MLDataService.auto_calculate_actual_hours``, the labor corpus, the ML
feature builder) then subtracts real minutes instead of the 0 sentinel.

``time_entries.duration_minutes`` keeps its meaning (gross wall-clock
minutes); no data is rewritten. Existing interruptions stay "closed with
the duration they were given" (``resumed_at`` NULL, duration as stored).

Downgrade drops the column (lossy: the resume timestamps are gone; the
measured durations stay in ``duration_minutes``).

Revision ID: 20260925_w214_interrupt_resume
Revises: 20260925_w206_gemstone_intake
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260925_w214_interrupt_resume"
down_revision: Union[str, None] = "20260925_w206_gemstone_intake"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "interruptions"
COLUMN = "resumed_at"


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    add_column_if_not_exists(TABLE, sa.Column(COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    drop_column_if_exists(TABLE, COLUMN)
