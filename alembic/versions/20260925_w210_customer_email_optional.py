"""W2-10 (DOM-02, decision D-11): customers without an email address.

Upgrade:
1. Replace the full unique index ``ix_customers_email_hash`` with a partial
   unique index of the same name ``WHERE email_hash IS NOT NULL`` (PostgreSQL
   and SQLite both accept the predicate). Present emails stay unique through
   the unchanged HMAC blind index; absent ones never collide.
2. ``customers.email`` and ``customers.email_hash`` become nullable.
3. Rows carrying the placeholder a previous downgrade wrote
   (``no-email-<id>@invalid.local``, detected through its blind index, the
   ciphertext is never decrypted) get their email and hash back to NULL, so
   down/up round-trips are lossless.

Downgrade (reversible, lossy only in that the placeholder is visible to a
pre-W2-10 build):
1. Every customer without an email gets the encrypted placeholder
   ``no-email-<id>@invalid.local`` plus its blind index (unique per id).
2. The partial index is replaced by the original full unique index and both
   columns become NOT NULL again.

SQLite cannot ALTER a column's nullability, so step 2 runs through
``batch_alter_table`` there. On a fresh DB ``v1_initial``'s ``create_all()``
already produced the new shape; every step is idempotent.

Revision ID: 20260925_w210_email_optional
Revises: 20260925_w207_order_events
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260925_w210_email_optional"
down_revision: Union[str, None] = "20260925_w207_order_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "customers"
INDEX = "ix_customers_email_hash"
_PRESENT = "email_hash IS NOT NULL"


def placeholder_email(customer_id: int) -> str:
    """Placeholder a downgrade writes for a customer without an email."""
    return f"no-email-{customer_id}@invalid.local"


def _blind_index(value: str) -> str:
    from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: PLC0415

    return hmac_blind_index(value)


def _customers_table() -> sa.TableClause:
    from goldsmith_erp.db.types import EncryptedString  # noqa: PLC0415

    return sa.table(
        TABLE,
        sa.column("id", sa.Integer),
        sa.column("email", EncryptedString()),
        sa.column("email_hash", sa.String(64)),
    )


def _set_nullable(nullable: bool) -> None:
    columns = (
        ("email", sa.Text()),
        ("email_hash", sa.String(64)),
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(TABLE) as batch:
            for name, type_ in columns:
                batch.alter_column(name, existing_type=type_, nullable=nullable)
        return
    for name, type_ in columns:
        op.alter_column(TABLE, name, existing_type=type_, nullable=nullable)


def _clear_placeholders(bind: sa.engine.Connection) -> None:
    customers = _customers_table()
    rows = bind.execute(sa.select(customers.c.id, customers.c.email_hash)).all()
    for customer_id, email_hash in rows:
        if email_hash and email_hash == _blind_index(placeholder_email(customer_id)):
            bind.execute(
                customers.update()
                .where(customers.c.id == customer_id)
                .values(email=None, email_hash=None)
            )


def _fill_placeholders(bind: sa.engine.Connection) -> None:
    customers = _customers_table()
    rows = bind.execute(
        sa.select(customers.c.id).where(
            sa.or_(customers.c.email.is_(None), customers.c.email_hash.is_(None))
        )
    ).all()
    for (customer_id,) in rows:
        email = placeholder_email(customer_id)
        bind.execute(
            customers.update()
            .where(customers.c.id == customer_id)
            .values(email=email, email_hash=_blind_index(email))
        )


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_index_if_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    drop_index_if_exists(INDEX, TABLE)
    _set_nullable(True)
    op.create_index(
        INDEX,
        TABLE,
        ["email_hash"],
        unique=True,
        postgresql_where=sa.text(_PRESENT),
        sqlite_where=sa.text(_PRESENT),
    )
    _clear_placeholders(op.get_bind())


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_index_if_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    _fill_placeholders(op.get_bind())
    drop_index_if_exists(INDEX, TABLE)
    _set_nullable(False)
    op.create_index(INDEX, TABLE, ["email_hash"], unique=True)
