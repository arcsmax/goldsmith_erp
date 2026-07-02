"""I12 — DB-level unique index closing the customer-no-go duplicate TOCTOU.

Fix item **I12** (github issue #12), REWRITTEN for the follow-up ECC-review
fix wave (encrypt ``CustomerNoGo.value``/``note`` + HMAC blind-index unique
constraint). This migration never shipped past this branch — it is rewritten
IN PLACE rather than superseded by a new revision; ``revision``/
``down_revision`` below are unchanged so the alembic chain is untouched.

Why rewrite instead of amend-on-top
------------------------------------
The original version of this migration added a *functional* unique index on
``(customer_id, category, lower(value))``. Two problems surfaced in review,
both fatal to that approach:

1. **It blocks encryption.** ``CustomerNoGo.value`` is health-adjacent PII
   (allergies) and must be encrypted at rest (CLAUDE.md "Data Privacy
   Rules") — but once ``value`` holds non-deterministic Fernet ciphertext,
   ``lower(value)`` at the SQL level is meaningless (ciphertext has no
   stable case-folded form; the same plaintext produces different
   ciphertext on every write).
2. **SQL ``lower()`` and Python ``casefold()`` disagree.** The app-side
   duplicate pre-check in ``NoGoService.add_no_go`` normalises via Python's
   ``str.casefold()`` (full Unicode case folding — e.g. German ``ß`` →
   ``ss``). SQL ``lower()`` does not perform that expansion. Empirically:
   ``'Straße'`` and ``'STRASSE'`` collide under the app-side check but did
   NOT collide under this migration's original ``lower(value)`` index — the
   exact case the DB-level backstop exists to catch.

The fix: ``value``/``note`` are now ``EncryptedString`` (see
``db/types.py`` + ``db/models.py`` ``CustomerNoGo``), and duplicate
detection moves entirely to a new ``value_hash`` column — an HMAC-SHA-256
blind-index tag (``core.encryption.no_go_value_blind_index``) computed over
``"<category>:<value.strip().casefold()>"``. Casefold is now the ONE
normalisation semantics used everywhere: the app-side pre-check, the model's
before_insert/before_update hooks, and this migration's backfill all call
the same helper. The unique index moves to plain (non-expression)
``(customer_id, value_hash)``.

Migration steps (upgrade)
--------------------------
(a) Add ``value_hash`` nullable (backfill target).
(b) Widen ``value`` from ``VARCHAR(200)`` to ``TEXT`` (PostgreSQL only —
    SQLite doesn't enforce VARCHAR length) BEFORE writing any ciphertext —
    deliberately reordered vs. the C1/I15 precedents (which widen AFTER
    the encrypt-backfill write). Fernet's base64 expansion means a 200-char
    plaintext value can encrypt to well over 200 chars; writing that into
    a still-``VARCHAR(200)`` column would raise "value too long" on
    PostgreSQL. ``note`` needs no ALTER — it was already ``TEXT``.
(c) Single backfill sweep per row (mirrors the C1 "backfill + encrypt in
    one pass" shape, see ``20260424_c1_customer_pii_encryption.py``):
    decrypt-tolerant read of the current ``value``/``note`` (idempotent —
    a value that's already ciphertext round-trips through decrypt/
    re-encrypt unchanged), compute ``value_hash`` from the DECRYPTED
    value + category, re-encrypt both columns, write all three back.
(d) Dedupe rows sharing ``(customer_id, value_hash)``, keeping the oldest
    (by ``created_at``, ``id`` tiebreak) — same shape as the original
    ``_dedupe_no_gos``, re-keyed to ``value_hash`` instead of
    ``(customer_id, category, lower(value))``.
(e) Drop the old functional index if present (a pre-rewrite DB may have
    run the original version of this migration already).
(f) Create the new plain unique index on ``(customer_id, value_hash)``.
(g) Set ``value_hash`` NOT NULL.

Idempotency
-----------
``v1_initial`` (``Base.metadata.create_all()``) already declares ``value``/
``note`` as ``EncryptedString`` and ``value_hash`` as the ORM now defines
it — a fresh unit-test DB has no rows, so the backfill/dedupe loops no-op
and every guarded DDL step (``add_column_if_not_exists`` /
``create_index_if_not_exists`` / the PG-only ``alter_column``, itself a
harmless no-op on an already-``TEXT`` column) converges on the same schema
either way, exactly like C1/I15.

Downgrade
---------
Drops the new index, decrypts ``value``/``note`` back to plaintext,
restores ``value`` to ``VARCHAR(200)`` (PostgreSQL only), and drops
``value_hash``. Does not attempt to resurrect the original functional
index (there is no reason to — nothing downstream depends on it) nor any
rows a dedupe step removed, matching the original migration's downgrade
scope (destructive dedup is a one-way door, same as every other dedup
migration in this repo).

Revision ID: 20260703_i12_no_go_unique_idx
Revises: 20260703_i15_allergies_enc
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260703_i12_no_go_unique_idx"
down_revision: Union[str, None] = "20260703_i15_allergies_enc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_INDEX_NAME = "uq_customer_no_gos_customer_category_value_ci"
_NEW_INDEX_NAME = "uq_customer_no_gos_customer_value_hash"
_OLD_VALUE_LENGTH = 200


# ---------------------------------------------------------------------------
# Encryption / blind-index helpers — mirror the C1 / I15 migrations'
# self-contained ``_encrypt_value`` / ``_decrypt_value`` pattern (local
# imports of ``core.encryption`` so this file has no service-layer
# dependency and stays runnable standalone by alembic).
# ---------------------------------------------------------------------------


def _encrypt_value(value: str | None) -> str | None:
    """Encrypt a plaintext string with the running ``EncryptionService``.

    Returns ``None``/``""`` unchanged. Falls back to plaintext when
    ``ENCRYPTION_KEY`` is unset (dev fallback — matches
    ``EncryptedString.process_bind_param``).
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


def _no_go_value_hash(category: str | None, value: str) -> str:
    """Blind-index tag for (category, value) — reuses the app's HMAC helper.

    ``category`` is already the enum's raw ``.value`` string as stored in
    the DB column (SAEnum with ``values_callable`` — see ``db/models.py``
    ``SAEnum`` wrapper); never ``None`` in practice (the column is
    ``NOT NULL``), the guard is defensive only.
    """
    from goldsmith_erp.core.encryption import no_go_value_blind_index  # noqa: PLC0415

    return no_go_value_blind_index(category or "", value)


def _backfill_no_gos(bind: sa.engine.Connection) -> None:
    """Encrypt ``value``/``note`` in place and compute ``value_hash``.

    One pass per row: decrypt-tolerant read (idempotent against a retried
    / partial run), compute the hash off the DECRYPTED value, re-encrypt,
    write all three columns back in a single UPDATE. Must run AFTER the
    ``value`` column has already been widened to ``TEXT`` — see the module
    docstring's ordering rationale.
    """
    no_gos_t = sa.table(
        "customer_no_gos",
        sa.column("id", sa.Integer),
        sa.column("category", sa.String),
        sa.column("value", sa.Text),
        sa.column("note", sa.Text),
        sa.column("value_hash", sa.String),
    )
    rows = bind.execute(
        sa.select(
            no_gos_t.c.id,
            no_gos_t.c.category,
            no_gos_t.c.value,
            no_gos_t.c.note,
        )
    ).fetchall()

    for row in rows:
        if row.value is None:
            # value is NOT NULL at the DB level; defensive only.
            continue
        plain_value = _decrypt_value(row.value)
        value_hash = _no_go_value_hash(row.category, plain_value)
        updates: dict[str, str | None] = {
            "value": _encrypt_value(plain_value),
            "value_hash": value_hash,
        }
        if row.note is not None:
            updates["note"] = _encrypt_value(_decrypt_value(row.note))
        bind.execute(
            sa.update(no_gos_t).where(no_gos_t.c.id == row.id).values(**updates)
        )


def _dedupe_no_gos_by_value_hash(bind: sa.engine.Connection) -> None:
    """Delete rows sharing ``(customer_id, value_hash)``, keeping the oldest.

    Same shape as the pre-rewrite ``_dedupe_no_gos``, re-keyed to
    ``value_hash`` (which now encodes both category and casefolded value —
    see the module docstring). Must run AFTER ``_backfill_no_gos`` has
    populated ``value_hash`` for every row.
    """
    no_gos_t = sa.table(
        "customer_no_gos",
        sa.column("id", sa.Integer),
        sa.column("customer_id", sa.Integer),
        sa.column("value_hash", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    rows = bind.execute(
        sa.select(
            no_gos_t.c.id,
            no_gos_t.c.customer_id,
            no_gos_t.c.value_hash,
            no_gos_t.c.created_at,
        )
    ).fetchall()

    kept_ids: dict[tuple, int] = {}
    duplicate_ids: list[int] = []
    for row in sorted(rows, key=lambda r: (r.created_at is None, r.created_at, r.id)):
        if row.value_hash is None:
            continue
        key = (row.customer_id, row.value_hash)
        if key in kept_ids:
            duplicate_ids.append(row.id)
        else:
            kept_ids[key] = row.id

    if duplicate_ids:
        bind.execute(sa.delete(no_gos_t).where(no_gos_t.c.id.in_(duplicate_ids)))


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        column_exists,
        create_index_if_not_exists,
        index_exists,
    )

    # ── a. Add value_hash column (nullable for backfill) ───────────────
    # Idempotent: a fresh DB built via create_all already has the column
    # (the ORM now declares it).
    if not column_exists("customer_no_gos", "value_hash"):
        op.add_column(
            "customer_no_gos",
            sa.Column("value_hash", sa.String(64), nullable=True),
        )

    # ── b. Widen value → TEXT BEFORE writing any ciphertext ────────────
    # Must happen before the backfill below — see module docstring.
    # SQLite doesn't enforce VARCHAR length; PG performs the rewrite.
    if dialect == "postgresql":
        op.alter_column(
            "customer_no_gos",
            "value",
            type_=sa.Text(),
            existing_nullable=False,
            existing_type=sa.String(_OLD_VALUE_LENGTH),
            postgresql_using="value::text",
        )

    # ── c. Backfill: encrypt value/note + compute value_hash ───────────
    _backfill_no_gos(bind)

    # ── d. Dedupe — the unique index below fails outright on any
    # remaining (customer_id, value_hash) collision. ───────────────────
    _dedupe_no_gos_by_value_hash(bind)

    # ── e. Drop the old functional index if present ────────────────────
    op.execute(f"DROP INDEX IF EXISTS {_OLD_INDEX_NAME}")

    # ── f. Create the new plain unique index ────────────────────────────
    create_index_if_not_exists(
        _NEW_INDEX_NAME,
        "customer_no_gos",
        ["customer_id", "value_hash"],
        unique=True,
    )

    # ── g. NOT NULL on value_hash — safe once every row is populated.
    # Re-applying on a fresh DB is a no-op (create_all already declared it).
    op.alter_column(
        "customer_no_gos",
        "value_hash",
        nullable=False,
        existing_type=sa.String(64),
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    from goldsmith_erp.db.migration_helpers import index_exists  # noqa: PLC0415

    # ── g/f. Drop NOT NULL + the new unique index ───────────────────────
    op.alter_column(
        "customer_no_gos",
        "value_hash",
        nullable=True,
        existing_type=sa.String(64),
    )
    if index_exists("customer_no_gos", _NEW_INDEX_NAME):
        op.drop_index(_NEW_INDEX_NAME, table_name="customer_no_gos")

    # ── c. Decrypt value/note back to plaintext BEFORE narrowing value ──
    no_gos_t = sa.table(
        "customer_no_gos",
        sa.column("id", sa.Integer),
        sa.column("value", sa.Text),
        sa.column("note", sa.Text),
    )
    rows = bind.execute(
        sa.select(no_gos_t.c.id, no_gos_t.c.value, no_gos_t.c.note)
    ).fetchall()
    for row in rows:
        updates: dict[str, str | None] = {}
        if row.value is not None:
            updates["value"] = _decrypt_value(row.value)
        if row.note is not None:
            updates["note"] = _decrypt_value(row.note)
        if updates:
            bind.execute(
                sa.update(no_gos_t).where(no_gos_t.c.id == row.id).values(**updates)
            )

    # ── b. Narrow value back to VARCHAR(200) (PostgreSQL only) ──────────
    if dialect == "postgresql":
        op.alter_column(
            "customer_no_gos",
            "value",
            type_=sa.String(_OLD_VALUE_LENGTH),
            existing_nullable=False,
            existing_type=sa.Text(),
            postgresql_using=f"value::varchar({_OLD_VALUE_LENGTH})",
        )

    # ── a. Drop value_hash last ──────────────────────────────────────────
    op.drop_column("customer_no_gos", "value_hash")
