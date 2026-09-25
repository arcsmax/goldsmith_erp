"""W2-16 (DOM-21, decision D-16): ID capture on Altgold purchases.

Adds optional identification fields to ``scrap_gold`` (the Ankaufsbuch
record). The service requires them before SIGNED when the purchase value is
above ``SCRAP_GOLD_ID_THRESHOLD_EUR`` (default 2,000 EUR; the legal basis,
§10 Abs. 6a GwG, is still to be confirmed by the Steuerberater).

* ``id_document_type`` String(30): personalausweis / reisepass /
  aufenthaltstitel / sonstiges. Not personal on its own, stored plain.
* ``id_document_number`` Text, EncryptedString in the ORM (PII).
* ``id_issuing_authority`` Text, EncryptedString in the ORM (PII).
* ``id_checked_by`` FK users.id ON DELETE SET NULL, ``id_checked_at``.

The encrypted columns are TEXT because Fernet ciphertext has no fixed
length (same as the customer PII columns). SQLite (tests) cannot add a FK to
an existing table, so there ``id_checked_by`` is added without the
constraint (``create_all`` declares it inline on a fresh DB).

Downgrade drops the five columns (lossy: captured ID data is deleted, which
is also what an erasure of these fields would require).

Revision ID: 20260925_w216_altgold_id
Revises: 20260925_w214_interrupt_resume
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260925_w216_altgold_id"
down_revision: Union[str, None] = "20260925_w214_interrupt_resume"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "scrap_gold"
CHECKED_BY_FK = "fk_scrap_gold_id_checked_by_users"
_COLUMNS = (
    "id_document_type",
    "id_document_number",
    "id_issuing_authority",
    "id_checked_by",
    "id_checked_at",
)


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        create_fk_if_not_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    add_column_if_not_exists(
        TABLE, sa.Column("id_document_type", sa.String(30), nullable=True)
    )
    add_column_if_not_exists(
        TABLE, sa.Column("id_document_number", sa.Text(), nullable=True)
    )
    add_column_if_not_exists(
        TABLE, sa.Column("id_issuing_authority", sa.Text(), nullable=True)
    )
    add_column_if_not_exists(
        TABLE, sa.Column("id_checked_by", sa.Integer(), nullable=True)
    )
    add_column_if_not_exists(
        TABLE, sa.Column("id_checked_at", sa.DateTime(), nullable=True)
    )
    create_fk_if_not_exists(
        CHECKED_BY_FK,
        TABLE,
        "users",
        ["id_checked_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        drop_constraint_if_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    if op.get_bind().dialect.name != "sqlite":
        drop_constraint_if_exists(CHECKED_BY_FK, TABLE, type_="foreignkey")
    for column in _COLUMNS:
        drop_column_if_exists(TABLE, column)
