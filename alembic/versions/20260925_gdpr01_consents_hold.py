"""GDPR-01/02/11 — customer_consents table + customers.retention_hold_until.

- ``customer_consents`` (GDPR-02 / GDPR-11): per-purpose consent record,
  the Art. 7 Abs. 1 DSGVO proof. Allergies (Art. 9 health data) may only be
  stored while a ``health_data`` consent is active. ``purpose`` / ``method``
  are plain strings (validated by the Pydantic enums in
  ``models/consent.py``) so adding a purpose never needs ``ALTER TYPE``.
  ``note`` is ``EncryptedString`` on the ORM, i.e. TEXT here.
- ``customers.retention_hold_until`` (GDPR-01): legal-hold marker set on
  Art. 17 erasure when the customer has records §147 AO / §14b UStG /
  §8 Abs. 4 GwG require us to keep. Those records are no longer scrubbed.

Idempotency: both objects are declared on the ORM, so on a fresh DB
``v1_initial``'s ``Base.metadata.create_all()`` creates them before this
migration runs; every step below is guarded and no-ops there. Works on
SQLite (tests) and PostgreSQL.

Revision ID: 20260925_gdpr01_consents
Revises: 20260610_e1_gdpr_audit_nofk
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op  # noqa: F401  (helpers wrap it)

# revision identifiers, used by Alembic.
revision: str = "20260925_gdpr01_consents"
down_revision: Union[str, None] = "20260610_e1_gdpr_audit_nofk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        create_index_if_not_exists,
        create_table_if_not_exists,
    )

    create_table_if_not_exists(
        "customer_consents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("wording_version", sa.String(32), nullable=True),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column(
            "recorded_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "revoked_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    # Index names match what the ORM's ``index=True`` produces, so a DB built
    # by create_all() and one built by this migration are identical.
    create_index_if_not_exists("ix_customer_consents_id", "customer_consents", ["id"])
    create_index_if_not_exists(
        "ix_customer_consents_customer_id", "customer_consents", ["customer_id"]
    )
    create_index_if_not_exists(
        "ix_customer_consents_purpose", "customer_consents", ["purpose"]
    )

    add_column_if_not_exists(
        "customers", sa.Column("retention_hold_until", sa.DateTime(), nullable=True)
    )
    create_index_if_not_exists(
        "ix_customers_retention_hold_until", "customers", ["retention_hold_until"]
    )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        drop_index_if_exists,
        drop_table_if_exists,
    )

    # Downgrading drops consent proof — the operator must export it first
    # (GET /customers/{id}/export includes consents).
    drop_index_if_exists("ix_customers_retention_hold_until", "customers")
    drop_column_if_exists("customers", "retention_hold_until")
    drop_index_if_exists("ix_customer_consents_purpose", "customer_consents")
    drop_index_if_exists("ix_customer_consents_customer_id", "customer_consents")
    drop_index_if_exists("ix_customer_consents_id", "customer_consents")
    drop_table_if_exists("customer_consents")
