"""V1 initial schema — all tables

Consolidates 25 previous migration files into a single clean initial migration.
Old files have been moved to alembic/versions/archive/ for reference.

Revision ID: v1_initial
Revises: (none)
Create Date: 2026-04-01
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v1_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create pre-V1.1 tables from the current ORM model definitions.

    Calls Base.metadata.create_all() with a filter that EXCLUDES any
    table introduced by the V1.1 (or later) wave — those tables are
    owned by their own migrations (20260418_qr_core, 20260419_security_floor,
    etc.) and must be created by those migrations (e.g. scan_logs requires
    PostgreSQL RANGE partitioning that the ORM cannot express).

    Fix applied 2026-04-17 after smoke-test caught duplicate-table errors
    on fresh DBs: previously create_all() ran over the full Base.metadata
    and produced scan_logs/barcode_aliases/label_templates unpartitioned,
    then Slice 1 migration failed trying to recreate them.
    """
    from goldsmith_erp.db.models import Base  # noqa: PLC0415

    # Tables introduced AFTER v1_initial — owned by later migrations.
    # Keep this list synced with migrations 20260417_anonymize_user onward
    # that use op.create_table / raw DDL for new tables.
    POST_V1_TABLES = frozenset(
        {
            # Slice 1 (Migration 1) — QR/barcode core
            "barcode_aliases",
            "scan_logs",
            "label_templates",
        }
    )

    bind = op.get_bind()
    subset = [
        t
        for t in Base.metadata.sorted_tables
        if t.name not in POST_V1_TABLES
    ]
    Base.metadata.create_all(bind=bind, tables=subset)


def downgrade() -> None:
    """Drop all tables and associated types."""
    from goldsmith_erp.db.models import Base  # noqa: PLC0415

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
