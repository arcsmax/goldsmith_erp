"""W2-04 (DOM-24, DOM-24b, BE-16; decision D-12): §14 UStG invoices,
workshop settings, Storno link and gap-free per-year numbering.

Upgrade:
1. ``workshop_settings``: singleton (CHECK ``id = 1``) with the seller data
   §14 Abs. 4 UStG requires on a Rechnung (name, address, Steuernummer or
   USt-IdNr., bank details, Kleinunternehmer flag, default VAT rate, footer).
   No row is inserted: the service falls back to ``WORKSHOP_NAME`` until an
   ADMIN saves the form.
2. ``number_sequences`` (kind, year, last_value): the counter behind
   RE-YYYY-NNNN (invoices) and KV-YYYY-NNNN (quotes). Seeded from the
   numerically highest existing number per kind and year (not the string
   MAX, which breaks at 10,000), so existing documents keep their numbers
   and the next one continues without a gap.
3. ``invoices.cancels_invoice_id`` (FK to ``invoices.id``, RESTRICT; a
   Stornorechnung points at the invoice it cancels) and
   ``invoices.service_date`` (Leistungsdatum), both nullable.
4. Partial unique index ``uq_invoices_one_active_per_order`` on
   ``invoices(order_id) WHERE status <> 'cancelled' AND cancels_invoice_id
   IS NULL``. Pre-flight: if an order already has two live invoices the
   migration stops with the order ids (an operator must cancel one).

Downgrade drops the index, both columns and both tables. Lossy: Storno
invoices stay as ordinary rows without their link, and the counters are
gone (pre-W2-04 code derives numbers from MAX again).

SQLite (tests) cannot add a FK to an existing table, so there the column is
added without the constraint (``create_all`` declares it inline on a fresh
DB). Every step is idempotent.

Revision ID: 20260925_w204_invoice_ustg14
Revises: 20260925_w210_email_optional
Create Date: 2026-09-25
"""

from __future__ import annotations

import re
from typing import Dict, Sequence, Tuple, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260925_w204_invoice_ustg14"
down_revision: Union[str, None] = "20260925_w210_email_optional"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SETTINGS = "workshop_settings"
SEQUENCES = "number_sequences"
ACTIVE_INDEX = "uq_invoices_one_active_per_order"
CANCELS_FK = "fk_invoices_cancels_invoice_id"
CANCELS_INDEX = "ix_invoices_cancels_invoice_id"
_ACTIVE = "status <> 'cancelled' AND cancels_invoice_id IS NULL"
# (kind, table, column) of every document number drawn from the counter.
_NUMBERED = (("RE", "invoices", "invoice_number"), ("KV", "quotes", "quote_number"))


def _create_settings_table() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_table_if_not_exists,
    )

    create_table_if_not_exists(
        SETTINGS,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("owner_name", sa.String(200), nullable=True),
        sa.Column("street", sa.String(200), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("tax_number", sa.String(50), nullable=True),
        sa.Column("vat_id", sa.String(20), nullable=True),
        sa.Column("iban", sa.String(34), nullable=True),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("bank_name", sa.String(100), nullable=True),
        sa.Column(
            "is_kleinunternehmer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "default_vat_rate", sa.Float(), nullable=False, server_default="19.0"
        ),
        sa.Column("invoice_footer", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "updated_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("id = 1", name="ck_workshop_settings_singleton"),
    )


def _create_sequences_table() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_table_if_not_exists,
    )

    create_table_if_not_exists(
        SEQUENCES,
        sa.Column("kind", sa.String(10), primary_key=True),
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
    )


def _add_invoice_columns() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        create_fk_if_not_exists,
        create_index_if_not_exists,
    )

    add_column_if_not_exists(
        "invoices", sa.Column("cancels_invoice_id", sa.Integer(), nullable=True)
    )
    add_column_if_not_exists(
        "invoices", sa.Column("service_date", sa.DateTime(), nullable=True)
    )
    create_fk_if_not_exists(
        CANCELS_FK,
        "invoices",
        "invoices",
        ["cancels_invoice_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    create_index_if_not_exists(CANCELS_INDEX, "invoices", ["cancels_invoice_id"])


def _orders_with_several_live_invoices(bind: sa.engine.Connection) -> list[int]:
    rows = bind.execute(
        sa.text(
            "SELECT order_id FROM invoices WHERE "
            f"{_ACTIVE} GROUP BY order_id HAVING COUNT(*) > 1"
        )
    ).all()
    return [int(r[0]) for r in rows]


def _create_active_index(bind: sa.engine.Connection) -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_index_if_not_exists,
        index_exists,
    )

    if index_exists("invoices", ACTIVE_INDEX):
        return
    duplicates = _orders_with_several_live_invoices(bind)
    if duplicates:
        raise RuntimeError(
            f"{ACTIVE_INDEX}: Auftraege {duplicates} haben mehr als eine aktive "
            "Rechnung. Bitte vor der Migration die ueberzaehlige Rechnung "
            "stornieren (Status cancelled)."
        )
    create_index_if_not_exists(
        ACTIVE_INDEX,
        "invoices",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE),
        sqlite_where=sa.text(_ACTIVE),
    )


def highest_numbers(kind: str, numbers: Sequence[str]) -> Dict[Tuple[str, int], int]:
    """Numerically highest suffix per (kind, year) among ``numbers``."""
    pattern = re.compile(rf"^{re.escape(kind)}-(\d{{4}})-(\d+)$")
    highest: Dict[Tuple[str, int], int] = {}
    for number in numbers:
        match = pattern.match(number or "")
        if match is None:
            continue
        key = (kind, int(match.group(1)))
        highest[key] = max(highest.get(key, 0), int(match.group(2)))
    return highest


def _seed_sequences(bind: sa.engine.Connection) -> None:
    from goldsmith_erp.db.migration_helpers import table_exists  # noqa: PLC0415

    sequences = sa.table(
        SEQUENCES,
        sa.column("kind", sa.String),
        sa.column("year", sa.Integer),
        sa.column("last_value", sa.Integer),
    )
    existing = {
        (kind, year): value
        for kind, year, value in bind.execute(
            sa.select(sequences.c.kind, sequences.c.year, sequences.c.last_value)
        ).all()
    }
    for kind, table, column in _NUMBERED:
        if not table_exists(table):
            continue
        numbers = [r[0] for r in bind.execute(sa.text(f"SELECT {column} FROM {table}"))]
        for key, value in highest_numbers(kind, numbers).items():
            if key not in existing:
                bind.execute(
                    sequences.insert().values(
                        kind=key[0], year=key[1], last_value=value
                    )
                )
            elif existing[key] < value:
                bind.execute(
                    sequences.update()
                    .where(sequences.c.kind == key[0], sequences.c.year == key[1])
                    .values(last_value=value)
                )


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import table_exists  # noqa: PLC0415

    _create_settings_table()
    _create_sequences_table()
    bind = op.get_bind()
    if table_exists("invoices"):
        _add_invoice_columns()
        _create_active_index(bind)
    _seed_sequences(bind)


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        drop_constraint_if_exists,
        drop_index_if_exists,
        drop_table_if_exists,
        table_exists,
    )

    if table_exists("invoices"):
        drop_index_if_exists(ACTIVE_INDEX, "invoices")
        drop_index_if_exists(CANCELS_INDEX, "invoices")
        drop_constraint_if_exists(CANCELS_FK, "invoices", type_="foreignkey")
        drop_column_if_exists("invoices", "service_date")
        drop_column_if_exists("invoices", "cancels_invoice_id")
    drop_table_if_exists(SEQUENCES)
    drop_table_if_exists(SETTINGS)
