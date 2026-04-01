"""Add goldsmith intake fields and expand OrderStatusEnum

Revision ID: 5e6f7a8b9c0d
Revises: 4d5e6f7a8b9c
Create Date: 2026-04-01

Adds the Goldsmith Intake Pflichtfelder columns to the `orders` table and
expands the `orderstatusenum` PostgreSQL enum type with the full goldsmith
production pipeline stages.

New enum values added to orderstatusenum:
  draft               -- Entwurf, not yet confirmed by customer
  confirmed           -- Bestaetigt, all Pflichtfelder checked
  waiting_for_fitting -- Wartet auf Anprobe
  fitting_done        -- Anprobe abgeschlossen
  ready_for_setting   -- Bereit fuer Steinbesatz / Fassung
  quality_check       -- Endkontrolle (Punzierung, Masscheck)

New columns added to orders:
  alloy               VARCHAR(20)  -- Legierung: '585', '750', 'Ag925', etc.
  ring_size_mm        FLOAT        -- Per-order Ringmass in mm (innerer Umfang)
  surface_finish      VARCHAR(50)  -- 'Hochglanz', 'Matt', 'Gebuerstet', etc.
  fitting_date        TIMESTAMP    -- Anprobe-Datum
  has_scrap_gold      BOOLEAN      -- Altgold vorhanden?
  special_instructions TEXT        -- Sonderwuensche des Kunden
  is_deleted          BOOLEAN      -- Soft-delete flag
  deleted_at          TIMESTAMP    -- Soft-delete timestamp

All columns are nullable (or have safe defaults) for backward compatibility.
The enum expansion uses IF NOT EXISTS guards so the migration is idempotent
with respect to partial earlier runs.

Rollback strategy:
  downgrade() drops the eight columns and the alloy index.
  Removing enum values from a live PostgreSQL enum requires recreating the
  type, which is destructive; downgrade therefore leaves the enum values
  in place (safe — unused values cause no errors).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '5e6f7a8b9c0d'
down_revision: Union[str, None] = '4d5e6f7a8b9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Expand orderstatusenum with goldsmith production pipeline stages
    #    PostgreSQL requires each ADD VALUE to be a separate statement.
    #    IF NOT EXISTS guards prevent errors on repeated runs.
    # ------------------------------------------------------------------
    op.execute("ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS 'draft'")
    op.execute("ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS 'confirmed'")
    op.execute("ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS 'waiting_for_fitting'")
    op.execute("ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS 'fitting_done'")
    op.execute("ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS 'ready_for_setting'")
    op.execute("ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS 'quality_check'")

    # ------------------------------------------------------------------
    # 2. Goldsmith Intake Pflichtfelder
    # ------------------------------------------------------------------

    # Legierung — required before order confirmation
    op.add_column(
        'orders',
        sa.Column('alloy', sa.String(20), nullable=True),
    )
    op.create_index('ix_orders_alloy', 'orders', ['alloy'])

    # Ringmass — required when order_type = 'ring'
    op.add_column(
        'orders',
        sa.Column('ring_size_mm', sa.Float(), nullable=True),
    )

    # Oberflaechenbearbeitung — Hochglanz, Matt, Gebuerstet, Gehaemmert, etc.
    op.add_column(
        'orders',
        sa.Column('surface_finish', sa.String(50), nullable=True),
    )

    # Anprobe-Datum — scheduled fitting appointment
    op.add_column(
        'orders',
        sa.Column('fitting_date', sa.DateTime(), nullable=True),
    )

    # Altgold vorhanden — triggers the Altgold-Verrechnung workflow
    op.add_column(
        'orders',
        sa.Column('has_scrap_gold', sa.Boolean(), nullable=False, server_default='false'),
    )

    # Sonderwuensche des Kunden
    op.add_column(
        'orders',
        sa.Column('special_instructions', sa.Text(), nullable=True),
    )

    # ------------------------------------------------------------------
    # 3. Soft delete support
    # ------------------------------------------------------------------
    op.add_column(
        'orders',
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('ix_orders_is_deleted', 'orders', ['is_deleted'])

    op.add_column(
        'orders',
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    # Drop soft-delete columns
    op.drop_index('ix_orders_is_deleted', table_name='orders')
    op.drop_column('orders', 'deleted_at')
    op.drop_column('orders', 'is_deleted')

    # Drop goldsmith intake fields
    op.drop_column('orders', 'special_instructions')
    op.drop_column('orders', 'has_scrap_gold')
    op.drop_column('orders', 'fitting_date')
    op.drop_column('orders', 'surface_finish')
    op.drop_column('orders', 'ring_size_mm')
    op.drop_index('ix_orders_alloy', table_name='orders')
    op.drop_column('orders', 'alloy')

    # NOTE: PostgreSQL does not support removing enum values via ALTER TYPE.
    # The values 'draft', 'confirmed', 'waiting_for_fitting', 'fitting_done',
    # 'ready_for_setting', and 'quality_check' remain in the enum type.
    # They are unused after downgrade and will cause no runtime errors.
