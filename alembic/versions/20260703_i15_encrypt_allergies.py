"""I15 — Encrypt ``Customer.allergies`` at rest.

Fix item **I15** (github issue #15) — brings ``customers.allergies`` in line
with the C1 pattern already applied to the other ``Customer`` PII columns
(``20260424_c1_customer_pii_encryption.py``, see ``db/types.py``). CLAUDE.md
"Data Privacy Rules (CRITICAL)" treats allergy data as health-adjacent and
requires encryption at rest even though it isn't traditional "names, address,
phone, email" PII.

The migration mirrors C1's shape, scoped to one column:

1. Migrates every existing row's ``allergies`` value from plaintext to
   Fernet ciphertext (Python-level backfill — same dev/pre-production
   scope note as C1; see that migration's docstring for the encryption-key
   fallback behaviour).
2. Alters the column type from ``VARCHAR(500)`` to ``TEXT`` (PostgreSQL
   only — SQLite doesn't enforce VARCHAR length so the ALTER is a no-op
   there) so Fernet tokens fit without truncation. ``EncryptedString`` in
   the ORM maps to TEXT.

Unlike ``email``, ``allergies`` is never searched by equality or used in a
UNIQUE constraint (see ``services/no_go_service.py`` — the only reads are
plain attribute access), so this migration does not need a blind-index
companion column.

Length semantics
-----------------
The product-level 500-char limit on allergy freetext (``_ALLERGIES_MAX_LENGTH``
in ``services/no_go_service.py``, ``max_length=500`` in the Pydantic schema)
governs PLAINTEXT input length and is unaffected by this migration — it stays
500. The storage column itself becomes unbounded ``TEXT`` because ciphertext
is longer than plaintext, exactly as C1 did for ``email`` / ``street`` / etc.

Idempotency
-----------
``v1_initial`` (``Base.metadata.create_all()``) already declares ``allergies``
as ``EncryptedString`` (TEXT) on a fresh DB — this migration's backfill loop
and column-type ALTER both no-op safely there (no VARCHAR(500) to find,
already TEXT). On a pre-I15 DB with plaintext ``VARCHAR(500)`` data, the full
upgrade fires end-to-end. Both paths converge on the same schema.

Downgrade decrypts values back to plaintext and restores ``VARCHAR(500)``
(PostgreSQL only — see C1's downgrade for the same SQLite carve-out).

Revision ID: 20260703_i15_allergies_enc
Revises: 20260702_v11a_consultation
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260703_i15_allergies_enc"
down_revision: Union[str, None] = "20260702_v11a_consultation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_LENGTH = 500


def _encrypt_value(value: str | None) -> str | None:
    """Encrypt a plaintext string with the running ``EncryptionService``.

    Returns ``None`` for ``None`` / empty input. Falls back to returning the
    plaintext unchanged when ``ENCRYPTION_KEY`` is not configured (dev
    fallback — matches ``EncryptedString.process_bind_param``). Mirrors the
    C1 migration's ``_encrypt_value`` helper.
    """
    if value is None or value == "":
        return value
    from goldsmith_erp.core.config import settings  # noqa: PLC0415

    if not settings.ENCRYPTION_KEY:
        return value
    from goldsmith_erp.core.encryption import get_encryption_service  # noqa: PLC0415

    return get_encryption_service().encrypt(value)


def _decrypt_value(value: str | None) -> str | None:
    """Inverse of ``_encrypt_value``, tolerant of legacy plaintext."""
    if value is None or value == "":
        return value
    from goldsmith_erp.core.config import settings  # noqa: PLC0415

    if not settings.ENCRYPTION_KEY:
        return value
    from goldsmith_erp.core.encryption import (  # noqa: PLC0415
        EncryptionError,
        get_encryption_service,
    )

    try:
        return get_encryption_service().decrypt(value)
    except EncryptionError:
        # Already plaintext — leave as-is.
        return value


def upgrade() -> None:
    """Apply the I15 migration: encrypt ``allergies`` at rest.

    Idempotency notes
    ------------------
    See module docstring — a fresh DB built via ``create_all`` already has
    ``allergies`` as TEXT/EncryptedString; the backfill loop and column-type
    ALTER below are both safe no-ops in that case.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── 1. Backfill: encrypt every existing plaintext value ───────────
    customers_t = sa.table(
        "customers",
        sa.column("id", sa.Integer),
        sa.column("allergies", sa.Text),
    )
    rows = bind.execute(sa.select(customers_t.c.id, customers_t.c.allergies)).fetchall()

    for row_id, allergies in rows:
        if allergies is None:
            continue
        # Decrypt first in case of a retried / partial run (idempotency,
        # same reasoning as C1's PII backfill loop).
        plain = _decrypt_value(allergies)
        new_value = _encrypt_value(plain)
        if new_value != allergies:
            bind.execute(
                sa.update(customers_t)
                .where(customers_t.c.id == row_id)
                .values(allergies=new_value)
            )

    # ── 2. Alter column type VARCHAR(500) → TEXT ───────────────────────
    # SQLite doesn't enforce VARCHAR lengths so the ALTER is a no-op there;
    # PG performs the rewrite. Matches C1's dialect guard.
    if dialect == "postgresql":
        op.alter_column(
            "customers",
            "allergies",
            type_=sa.Text(),
            existing_nullable=True,
            existing_type=sa.String(_OLD_LENGTH),
            postgresql_using="allergies::text",
        )


def downgrade() -> None:
    """Reverse the I15 migration: decrypt ``allergies`` back to plaintext
    and restore ``VARCHAR(500)`` (PostgreSQL only — see C1's downgrade for
    the same SQLite carve-out: SQLite unique/typed constraints declared
    inline can only be changed via batch-table rebuild, and a fresh SQLite
    DB from ``create_all`` already reflects the current ORM schema).
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── 2. Decrypt every value BEFORE narrowing the column type ────────
    customers_t = sa.table(
        "customers",
        sa.column("id", sa.Integer),
        sa.column("allergies", sa.Text),
    )
    rows = bind.execute(sa.select(customers_t.c.id, customers_t.c.allergies)).fetchall()

    for row_id, allergies in rows:
        if allergies is None:
            continue
        plain = _decrypt_value(allergies)
        if plain != allergies:
            bind.execute(
                sa.update(customers_t)
                .where(customers_t.c.id == row_id)
                .values(allergies=plain)
            )

    # ── 1. Alter column type TEXT → VARCHAR(500) ────────────────────────
    if dialect == "postgresql":
        op.alter_column(
            "customers",
            "allergies",
            type_=sa.String(_OLD_LENGTH),
            existing_nullable=True,
            existing_type=sa.Text(),
            postgresql_using=f"allergies::varchar({_OLD_LENGTH})",
        )
