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
    """Create all tables from the current ORM model definitions.

    Calls Base.metadata.create_all() via the synchronous connection that
    Alembic's env.py already provides.  All enum types are created
    implicitly by SQLAlchemy when the tables that use them are created.
    """
    # Import inside the function to ensure models are registered with Base
    # at the time this migration runs, not at import time.
    from goldsmith_erp.db.models import Base  # noqa: PLC0415

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop all tables and associated types."""
    from goldsmith_erp.db.models import Base  # noqa: PLC0415

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
