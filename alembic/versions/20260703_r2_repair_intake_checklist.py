"""R2 — add ``repair_jobs.intake_checklist`` JSON column.

Part of the V1.1 repair photo-intake checklist feature (Task 2, follows R1's
real photo upload). Stores a JSON array of checklist items — shape
documented in ``goldsmith_erp.models.repair.IntakeChecklistItem`` (not
enforced by the DB): ``{"key": str, "label": str,
"status": "open"|"photo"|"na", "photo_id": int|None, "na_reason": str|None}``.

Nullable: existing rows (and any repair created before this ships) simply
have no checklist. The service layer only seeds a value for repairs created
AFTER this migration + the corresponding ``RepairService.create_repair``
change land — no backfill is attempted here, matching this repo's
precedent for additive nullable JSON columns (e.g. ``style_profile`` in
20260702_v11a_consultation_tables.py, which this migration's
``add_column_if_not_exists`` call mirrors exactly).

Idempotency
-----------
``add_column_if_not_exists`` is a no-op if the column already exists — safe
on a fresh ``v1_initial`` DB (``create_all()`` already includes the column
since it's declared on the ``RepairJob`` model) and safe to re-run against
an already-migrated DB.

Revision ID: 20260703_r2_intake_checklist
Revises: 20260703_r1_repair_photo_cleanup
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260703_r2_intake_checklist"
down_revision: Union[str, None] = "20260703_r1_repair_photo_cleanup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        table_exists,
    )

    if not table_exists("repair_jobs"):
        return

    add_column_if_not_exists(
        "repair_jobs", sa.Column("intake_checklist", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
    )

    drop_column_if_exists("repair_jobs", "intake_checklist")
