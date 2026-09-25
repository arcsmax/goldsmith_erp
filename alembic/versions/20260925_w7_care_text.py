"""W7 followup: workshop-editable care/next-steps text (Pflegehinweise).

Adds ``workshop_settings.care_text`` (nullable Text). ADMIN edits it on the
Werkstatt-Stammdaten panel; it is used by the handover PDF's "Pflegehinweise"
section and the status report's "next steps" paragraph, both falling back
to a built-in default text when it is empty. Not §14 UStG seller data, so
it does not participate in the invoice snapshot.

Downgrade drops the column (lossy: the custom text is deleted, same as an
edit that clears it back to empty).

Revision ID: 20260925_w7_care_text
Revises: 20260925_arch5_jobs
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260925_w7_care_text"
down_revision: Union[str, None] = "20260925_arch5_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "workshop_settings"
COLUMN = "care_text"


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    add_column_if_not_exists(TABLE, sa.Column(COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    drop_column_if_exists(TABLE, COLUMN)
