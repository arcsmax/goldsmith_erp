"""C1 — Encrypt Customer PII columns + add ``email_hash`` blind-index.

Fix item **C1** (docs/fix-plan/2026-04-23/C1-pii-encryption.md) — brings the
``customers`` table in line with CLAUDE.md "Data Privacy Rules (CRITICAL)":

  > Names, addresses, phone numbers, email → MUST be encrypted at rest
  > (EncryptedString type)

The migration:

1. Adds the ``email_hash`` column (``VARCHAR(64) NULL`` first, so the
   backfill loop has somewhere to write before the NOT NULL constraint
   latches).
2. Iterates every row in ``customers``, computes
   ``hmac_blind_index(email)`` on the plaintext, and stores the hex
   digest in ``email_hash``. Detects duplicate emails (would collide on
   the new unique constraint) and aborts with a clear message.
3. Drops the old ``UNIQUE (email)`` constraint (ciphertext can't be
   unique-indexed usefully — Fernet is non-deterministic).
4. Drops the per-column indexes on ``first_name``, ``last_name``,
   ``company_name`` (ciphertext indexes don't help any query path).
5. Migrates every PII column's stored values from plaintext to Fernet
   ciphertext (Python-level backfill — safe here because the system is
   **pre-production / dev-only**; see the decision log entry for
   2026-04-24).
6. Alters the column types from ``VARCHAR(N)`` to ``TEXT`` so Fernet
   tokens (always longer than the original plaintext) fit without
   truncation. ``EncryptedString`` in the ORM maps to TEXT.
7. Adds the unique index on ``email_hash`` and makes the column NOT
   NULL.

Downgrade reverses every step (decrypts values, drops ``email_hash``,
restores the old column types and indexes, restores the unique constraint
on ``email``).

Encryption key assumption
-------------------------
The migration reads ``settings.ENCRYPTION_KEY`` via the same
``EncryptionService`` singleton the application uses. If the key is
unset, the backfill loop falls back to writing plaintext — matching the
``EncryptedString`` dev-mode pass-through and the existing
``_encrypt_pii`` / ``_decrypt_pii`` helpers. In that case the
resulting column type is still ``TEXT`` and the migration is
trivially reversible; it just stores plaintext in a TEXT column until
``ENCRYPTION_KEY`` is configured and a re-encryption job runs.

Revision ID: 20260424_c1_pii_enc
Revises: 20260420_h9_restrict
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260424_c1_pii_enc"
down_revision: Union[str, None] = "20260420_h9_restrict"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Columns being migrated from VARCHAR(N) to TEXT (with Fernet ciphertext
# content). Each tuple is (column_name, old_length, nullable).
_PII_COLUMNS: list[tuple[str, int, bool]] = [
    ("first_name", 100, False),
    ("last_name", 100, False),
    ("company_name", 200, True),
    ("email", 255, False),
    ("phone", 50, True),
    ("mobile", 50, True),
    ("street", 200, True),
    ("city", 100, True),
    ("postal_code", 20, True),
]

# Per-column indexes on the legacy plaintext columns. These become
# useless once the column holds non-deterministic ciphertext, so they're
# dropped in upgrade / recreated in downgrade.
_LEGACY_PLAINTEXT_INDEXES: list[tuple[str, str]] = [
    ("ix_customers_first_name", "first_name"),
    ("ix_customers_last_name", "last_name"),
    ("ix_customers_company_name", "company_name"),
    ("ix_customers_email", "email"),
]


def _encrypt_value(value: str | None) -> str | None:
    """Encrypt a plaintext string with the running ``EncryptionService``.

    Returns ``None`` for ``None`` / empty input. Falls back to returning
    the plaintext unchanged when ``ENCRYPTION_KEY`` is not configured
    (dev fallback — matches ``EncryptedString.process_bind_param``).
    """
    if value is None or value == "":
        return value
    from goldsmith_erp.core.config import settings  # noqa: PLC0415
    if not settings.ENCRYPTION_KEY:
        return value
    from goldsmith_erp.core.encryption import (  # noqa: PLC0415
        get_encryption_service,
    )
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


def _blind_index(value: str) -> str:
    from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: PLC0415
    return hmac_blind_index(value)


def upgrade() -> None:
    """Apply the C1 migration: encrypt PII + add email_hash.

    Idempotency notes
    -----------------
    ``v1_initial`` uses ``Base.metadata.create_all()`` — a fresh DB
    already has ``email_hash`` (because the ORM now declares it). This
    migration skips the add-column step in that case and only runs the
    backfill + constraint-tightening work. For a pre-v1-with-plaintext
    DB the add-column runs and the full upgrade fires end-to-end. Both
    paths converge on the same schema.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── 1. Add email_hash column (nullable for backfill) ──────────────
    # Idempotent: fresh DBs built from the ORM (via create_all) already
    # have the column.
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        column_exists,
        index_exists,
    )
    if not column_exists("customers", "email_hash"):
        op.add_column(
            "customers",
            sa.Column("email_hash", sa.String(64), nullable=True),
        )

    # ── 2. Backfill email_hash + encrypt all PII columns in one sweep ─
    # Read every (id, <pii columns>) tuple, compute updated values in
    # Python, write them back. On a pre-production dataset this is O(N)
    # where N is trivially small; fine for dev-only scope.
    customers_t = sa.table(
        "customers",
        sa.column("id", sa.Integer),
        sa.column("email", sa.Text),
        sa.column("email_hash", sa.String(64)),
        *[sa.column(name, sa.Text) for name, _, _ in _PII_COLUMNS],
    )

    # Collect all existing rows.
    select_cols = [customers_t.c.id] + [
        customers_t.c[name] for name, _, _ in _PII_COLUMNS
    ]
    rows = bind.execute(sa.select(*select_cols)).fetchall()

    # Duplicate-email guard: the new unique constraint on email_hash
    # would fail on duplicates. Fail loudly here with a descriptive
    # message so the operator can deduplicate seed data first.
    seen_emails: dict[str, int] = {}
    for row in rows:
        row_map = dict(zip([c.name for c in select_cols], row))
        email = row_map.get("email")
        if email is None:
            continue
        # Always normalise the same way ``hmac_blind_index`` does.
        normalised = email.strip().lower()
        if normalised in seen_emails:
            raise RuntimeError(
                f"C1 migration aborted: duplicate customer email "
                f"{normalised!r} on rows id={seen_emails[normalised]} and "
                f"id={row_map['id']}. Deduplicate before re-running."
            )
        seen_emails[normalised] = row_map["id"]

    # Now apply the transform per row.
    for row in rows:
        row_map = dict(zip([c.name for c in select_cols], row))
        row_id = row_map["id"]
        updates: dict[str, str | None] = {}

        # Encrypt every PII column (idempotency: a value that's already
        # a Fernet token decrypts clean, then re-encrypts to a fresh
        # token — acceptable on the dev-only dataset).
        for col_name, _, _ in _PII_COLUMNS:
            plaintext = row_map.get(col_name)
            if plaintext is None:
                continue
            # Decrypt first in case of a retried / partial run.
            plain = _decrypt_value(plaintext)
            updates[col_name] = _encrypt_value(plain)

        # Compute the blind-index tag on the DECRYPTED email.
        email_plain = _decrypt_value(row_map.get("email"))
        if email_plain:
            updates["email_hash"] = _blind_index(email_plain)

        if updates:
            bind.execute(
                sa.update(customers_t)
                .where(customers_t.c.id == row_id)
                .values(**updates)
            )

    # ── 3. Drop legacy plaintext indexes (ciphertext is not searchable) ─
    for index_name, _col in _LEGACY_PLAINTEXT_INDEXES:
        if index_exists("customers", index_name):
            op.drop_index(index_name, table_name="customers")

    # ── 4. Drop the old unique constraint on email ────────────────────
    # The constraint name varies by dialect / ORM defaults. Try the
    # conventional names in order; skip if none is found.
    if dialect == "postgresql":
        # SQLAlchemy default for a column-level `unique=True`:
        # ``customers_email_key``.
        op.execute(
            "ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_email_key"
        )
    # SQLite: unique constraints declared inline on a column are part of
    # the table schema and can only be removed via batch-table rebuild.
    # For dev-only SQLite, ``Base.metadata.create_all`` on a fresh DB
    # already produces the new schema — we don't need to ALTER here.

    # ── 5. Change column types from VARCHAR(N) → TEXT ─────────────────
    # TEXT holds variable-length ciphertext without a size ceiling.
    # SQLite doesn't enforce VARCHAR lengths so the ALTER is a no-op
    # there; PG performs the rewrite.
    if dialect == "postgresql":
        for col_name, _old_len, nullable in _PII_COLUMNS:
            op.alter_column(
                "customers",
                col_name,
                type_=sa.Text(),
                existing_nullable=nullable,
                existing_type=sa.String(_old_len),
                postgresql_using=f"{col_name}::text",
            )

    # ── 6. Unique index + NOT NULL on email_hash ──────────────────────
    if not index_exists("customers", "ix_customers_email_hash"):
        op.create_index(
            "ix_customers_email_hash",
            "customers",
            ["email_hash"],
            unique=True,
        )
    # Only tighten NOT NULL once every row is populated. Safe to
    # re-apply on a fresh DB (create_all already declared NOT NULL).
    op.alter_column(
        "customers",
        "email_hash",
        nullable=False,
        existing_type=sa.String(64),
    )


def downgrade() -> None:
    """Reverse the C1 migration.

    Undoes every upgrade step in opposite order so the schema returns to
    the pre-C1 shape with plaintext PII columns and the original
    ``UNIQUE (email)`` constraint. Only safe on a dev-mode deployment
    (matches the upgrade's scope).
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── 6. Drop NOT NULL + unique index on email_hash ────────────────
    op.alter_column(
        "customers",
        "email_hash",
        nullable=True,
        existing_type=sa.String(64),
    )
    from goldsmith_erp.db.migration_helpers import index_exists  # noqa: PLC0415
    if index_exists("customers", "ix_customers_email_hash"):
        op.drop_index("ix_customers_email_hash", table_name="customers")

    # ── 5. Decrypt every PII column back to plaintext BEFORE altering type ──
    customers_t = sa.table(
        "customers",
        sa.column("id", sa.Integer),
        *[sa.column(name, sa.Text) for name, _, _ in _PII_COLUMNS],
    )
    select_cols = [customers_t.c.id] + [
        customers_t.c[name] for name, _, _ in _PII_COLUMNS
    ]
    rows = bind.execute(sa.select(*select_cols)).fetchall()
    for row in rows:
        row_map = dict(zip([c.name for c in select_cols], row))
        row_id = row_map["id"]
        updates: dict[str, str | None] = {}
        for col_name, _old_len, _ in _PII_COLUMNS:
            v = row_map.get(col_name)
            if v is None:
                continue
            updates[col_name] = _decrypt_value(v)
        if updates:
            bind.execute(
                sa.update(customers_t)
                .where(customers_t.c.id == row_id)
                .values(**updates)
            )

    # ── 4. Alter column types TEXT → VARCHAR(N) ──────────────────────
    if dialect == "postgresql":
        for col_name, old_len, nullable in _PII_COLUMNS:
            op.alter_column(
                "customers",
                col_name,
                type_=sa.String(old_len),
                existing_nullable=nullable,
                existing_type=sa.Text(),
                postgresql_using=f"{col_name}::varchar({old_len})",
            )

    # ── 3. Restore the UNIQUE (email) constraint ─────────────────────
    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE customers ADD CONSTRAINT customers_email_key UNIQUE (email)"
        )

    # ── 2. Recreate the legacy per-column indexes ────────────────────
    for index_name, col in _LEGACY_PLAINTEXT_INDEXES:
        # ix_customers_email is the UNIQUE-backing index — skip in PG
        # (the UNIQUE constraint already creates one). For SQLite we
        # rebuild it explicitly.
        if index_name == "ix_customers_email" and dialect == "postgresql":
            continue
        if not index_exists("customers", index_name):
            op.create_index(
                index_name,
                "customers",
                [col],
                unique=(index_name == "ix_customers_email"),
            )

    # ── 1. Drop email_hash column last (after its values are no longer
    #      used anywhere). ─────────────────────────────────────────────
    op.drop_column("customers", "email_hash")
