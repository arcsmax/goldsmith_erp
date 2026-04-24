"""C3 — Encrypt ``ValuationCertificate.appraised_value`` + add HMAC blind-index.

Fix item **C3** (docs/fix-plan/2026-04-23/C3-valuation-encryption.md) — brings
the ``valuation_certificates`` table in line with CLAUDE.md "Data Privacy
Rules (CRITICAL)":

  > Insurance Valuations: Valuation data MUST be encrypted at rest

The migration:

1. Adds ``appraised_value_hmac`` (``VARCHAR(64) NULL`` first, so the
   backfill loop has somewhere to write before the NOT NULL constraint
   latches).
2. Adds a transient ``appraised_value_encrypted`` TEXT column to hold the
   Fernet ciphertext. Needed because you can't ``ALTER COLUMN ... USING``
   a ``Float`` directly into a Fernet token — the cipher input is a
   string. We encrypt the numeric value into this side column, then swap
   names at the end.
3. Iterates every row in ``valuation_certificates``, reads the plaintext
   ``Float`` appraised_value, formats it as a fixed 2-decimal string
   (``f"{value:.2f}"`` — money precision), encrypts via the
   ``EncryptionService`` singleton, writes ciphertext into
   ``appraised_value_encrypted`` and the HMAC of the same normalised
   string into ``appraised_value_hmac``.
4. Drops the old plaintext ``appraised_value`` Float column.
5. Renames ``appraised_value_encrypted`` → ``appraised_value`` so the ORM
   attribute name is unchanged for callers.
6. Tightens both new columns to ``NOT NULL`` and indexes the HMAC column
   (matches the ORM's ``index=True`` on ``appraised_value_hmac``).

Downgrade reverses every step: decrypt ciphertext into a Float column,
drop the hash + rename, restore the original plaintext schema.

Encryption key assumption
-------------------------
Reads ``settings.ENCRYPTION_KEY`` via the same ``EncryptionService``
singleton the application uses. If the key is unset (dev-only), the
backfill falls back to storing the plaintext numeric string — matches
the ``EncryptedString`` dev-mode pass-through. The resulting column type
is still ``TEXT`` and the migration is trivially reversible; it just
stores plaintext until ``ENCRYPTION_KEY`` is configured and a
re-encryption job runs. Dev-only scope, consistent with C1.

Revision ID: 20260424_c3_val_enc
Revises: 20260424_c1_pii_enc
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260424_c3_val_enc"
down_revision: Union[str, None] = "20260424_c1_pii_enc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers — mirror the C1 migration's private encrypt/decrypt wrappers so
# dev-mode (no ENCRYPTION_KEY) degrades to plaintext pass-through without
# raising. Keeps the migration self-contained and idempotent.
# ---------------------------------------------------------------------------


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


def _normalised_2dp(value: float) -> str:
    """Format a numeric value as a fixed-2-decimal string for HMAC/cipher input.

    Every write path — ORM setter, event hook, this migration — uses the
    same normalisation so the hash invariant is preserved across
    round-trips. See ``ValuationCertificate.appraised_value.setter`` for
    the ORM-side companion.
    """
    from decimal import Decimal  # noqa: PLC0415
    return f"{Decimal(str(value)):.2f}"


def upgrade() -> None:
    """Apply the C3 migration: encrypt appraised_value + add hmac column.

    Idempotency notes
    -----------------
    ``v1_initial`` uses ``Base.metadata.create_all()`` — a fresh DB built
    from the current ORM already has ``appraised_value`` as ``TEXT``
    (the ``EncryptedString`` column) AND has ``appraised_value_hmac``.
    This migration detects that case via ``column_exists`` /
    ``get_columns`` introspection and skips the DDL that would otherwise
    raise ``DuplicateColumn`` on PG. For a pre-C3 DB where the column is
    still ``Float`` and the hash column is absent, the full upgrade
    fires end-to-end. Both paths converge on the same schema.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        column_exists,
        index_exists,
    )

    # Introspect the live column type — a fresh create_all()-built DB
    # already has appraised_value as TEXT and we can skip the whole
    # reshape. We only run when the column is still Float/Double.
    insp = sa.inspect(bind)
    existing_cols = {c["name"]: c for c in insp.get_columns("valuation_certificates")}
    av_col = existing_cols.get("appraised_value")
    av_is_plaintext_numeric = False
    if av_col is not None:
        col_type_str = str(av_col["type"]).upper()
        # Match float/double/real — anything we need to migrate away from.
        if any(t in col_type_str for t in ("FLOAT", "DOUBLE", "REAL", "NUMERIC")):
            av_is_plaintext_numeric = True

    # ── 1. Add appraised_value_hmac column (nullable for backfill) ────
    # Idempotent: fresh DBs built from the ORM (via create_all) already
    # have the column.
    if not column_exists("valuation_certificates", "appraised_value_hmac"):
        op.add_column(
            "valuation_certificates",
            sa.Column("appraised_value_hmac", sa.String(64), nullable=True),
        )

    # Only run the plaintext→ciphertext reshape when the live column is
    # still numeric. On a fresh ORM-built DB this block is a no-op.
    if av_is_plaintext_numeric:
        # ── 2. Add transient appraised_value_encrypted TEXT column ────
        if not column_exists("valuation_certificates", "appraised_value_encrypted"):
            op.add_column(
                "valuation_certificates",
                sa.Column("appraised_value_encrypted", sa.Text(), nullable=True),
            )

        # ── 3. Backfill: encrypt each row's Float → TEXT, compute HMAC ──
        # Read every (id, appraised_value) tuple, compute ciphertext +
        # hash in Python, write back. On a pre-production dataset this
        # is O(N) where N is trivially small; fine for dev-only scope.
        certs_t = sa.table(
            "valuation_certificates",
            sa.column("id", sa.Integer),
            sa.column("appraised_value", sa.Float),
            sa.column("appraised_value_encrypted", sa.Text),
            sa.column("appraised_value_hmac", sa.String(64)),
        )
        rows = bind.execute(
            sa.select(certs_t.c.id, certs_t.c.appraised_value)
        ).fetchall()

        for row in rows:
            row_id, plain_value = row
            if plain_value is None:
                # Shouldn't happen (old column was NOT NULL) but be safe.
                continue
            normalised = _normalised_2dp(plain_value)
            bind.execute(
                sa.update(certs_t)
                .where(certs_t.c.id == row_id)
                .values(
                    appraised_value_encrypted=_encrypt_value(normalised),
                    appraised_value_hmac=_blind_index(normalised),
                )
            )

        # ── 4. Drop the old plaintext Float column ────────────────────
        op.drop_column("valuation_certificates", "appraised_value")

        # ── 5. Rename the encrypted column back to the canonical name ──
        op.alter_column(
            "valuation_certificates",
            "appraised_value_encrypted",
            new_column_name="appraised_value",
        )

        # ── 6a. NOT NULL on the new ciphertext column ─────────────────
        op.alter_column(
            "valuation_certificates",
            "appraised_value",
            nullable=False,
            existing_type=sa.Text(),
        )

    # ── 6b. NOT NULL on appraised_value_hmac + create index ──────────
    # Safe to re-apply on a fresh DB (create_all already declared
    # NOT NULL and the index); the alter_column is a no-op if the
    # column is already NOT NULL, and index_exists guards the index.
    op.alter_column(
        "valuation_certificates",
        "appraised_value_hmac",
        nullable=False,
        existing_type=sa.String(64),
    )
    if not index_exists(
        "valuation_certificates", "ix_valuation_certificates_appraised_value_hmac"
    ):
        op.create_index(
            "ix_valuation_certificates_appraised_value_hmac",
            "valuation_certificates",
            ["appraised_value_hmac"],
            unique=False,
        )

    _ = dialect  # silence unused-name warning if we later drop the branch above


def downgrade() -> None:
    """Reverse the C3 migration.

    Undoes every upgrade step in opposite order: drop the HMAC column
    and its index, decrypt the ciphertext into a transient Float column,
    drop the ciphertext column, rename the Float column back.

    Only safe on a dev-mode deployment (matches the upgrade's scope).
    """
    bind = op.get_bind()
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        column_exists,
        index_exists,
    )

    # ── 6b. Drop index + NOT NULL on appraised_value_hmac ────────────
    if index_exists(
        "valuation_certificates", "ix_valuation_certificates_appraised_value_hmac"
    ):
        op.drop_index(
            "ix_valuation_certificates_appraised_value_hmac",
            table_name="valuation_certificates",
        )
    op.alter_column(
        "valuation_certificates",
        "appraised_value_hmac",
        nullable=True,
        existing_type=sa.String(64),
    )

    # ── 5→2. Decrypt ciphertext column into a transient Float column ──
    # Only run if the current schema has the encrypted (TEXT) column; a
    # partial downgrade (or a very old DB) might already have the
    # plaintext Float column in place.
    insp = sa.inspect(bind)
    existing_cols = {c["name"]: c for c in insp.get_columns("valuation_certificates")}
    av_col = existing_cols.get("appraised_value")
    av_is_ciphertext_text = False
    if av_col is not None:
        col_type_str = str(av_col["type"]).upper()
        if "TEXT" in col_type_str or "VARCHAR" in col_type_str:
            av_is_ciphertext_text = True

    if av_is_ciphertext_text:
        # Add a transient plaintext_float column (nullable), backfill
        # decrypted values, drop the ciphertext column, rename the
        # transient column back to appraised_value.
        if not column_exists(
            "valuation_certificates", "appraised_value_plaintext"
        ):
            op.add_column(
                "valuation_certificates",
                sa.Column("appraised_value_plaintext", sa.Float(), nullable=True),
            )

        certs_t = sa.table(
            "valuation_certificates",
            sa.column("id", sa.Integer),
            sa.column("appraised_value", sa.Text),
            sa.column("appraised_value_plaintext", sa.Float),
        )
        rows = bind.execute(
            sa.select(certs_t.c.id, certs_t.c.appraised_value)
        ).fetchall()
        for row in rows:
            row_id, cipher = row
            if cipher is None:
                continue
            plain_str = _decrypt_value(cipher)
            try:
                plain_float = float(plain_str) if plain_str is not None else None
            except (TypeError, ValueError):
                plain_float = None
            bind.execute(
                sa.update(certs_t)
                .where(certs_t.c.id == row_id)
                .values(appraised_value_plaintext=plain_float)
            )

        op.drop_column("valuation_certificates", "appraised_value")
        op.alter_column(
            "valuation_certificates",
            "appraised_value_plaintext",
            new_column_name="appraised_value",
        )
        op.alter_column(
            "valuation_certificates",
            "appraised_value",
            nullable=False,
            existing_type=sa.Float(),
        )

    # ── 1. Drop appraised_value_hmac column last (after its values are
    #      no longer used anywhere). ──────────────────────────────────
    op.drop_column("valuation_certificates", "appraised_value_hmac")
