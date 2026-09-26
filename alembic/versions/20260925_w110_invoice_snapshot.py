"""W1-10 (GDPR-01 snapshot part, BE-23) — immutable invoice snapshot.

Adds to ``invoices``:

- ``snapshot`` (TEXT; ``EncryptedString`` on the ORM): JSON with recipient,
  seller, order reference, lines and totals, written at invoice creation.
- ``issued_at``, ``issued_pdf`` (TEXT; base64 PDF, ``EncryptedString``) and
  ``issued_pdf_sha256``: the PDF frozen when the invoice is issued.

Data migration (best effort): every existing non-DRAFT invoice without a
snapshot gets one built from the CURRENT customer/order/line data, marked
``"backfilled": true`` — the original recipient at issue time is not
recoverable. Invoices whose customer is already anonymised (GDPR erasure
after the grace period) are counted and flagged
``"recipient_anonymized": true``; they need a note in the Art. 30 record.
DRAFT invoices get their snapshot lazily on first use
(``InvoiceSnapshotService.ensure_snapshot``). The frozen PDF of a backfilled
issued invoice is written on its first download.

The snapshot document layout must stay identical to
``services/invoice_snapshot_service.py::InvoiceSnapshotService.build``
(version 1); it is inlined here so this migration never changes behaviour
when the service evolves.

Idempotent and dialect-neutral (SQLite tests, PostgreSQL production).
On a fresh DB ``v1_initial``'s ``create_all()`` already created the columns.

Revision ID: 20260925_w110_invoice_snap
Revises: 20260925_w117_one_running
Create Date: 2026-09-25
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260925_w110_invoice_snap"
down_revision: Union[str, None] = "20260925_w117_one_running"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_ANONYMIZED_NAME = "[GELÖSCHT]"
_CREDIT_STATUSES = ("signed", "credited")
_NEW_COLUMNS = ("snapshot", "issued_at", "issued_pdf", "issued_pdf_sha256")


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _money(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _tables() -> Dict[str, sa.TableClause]:
    from goldsmith_erp.db.types import EncryptedString  # noqa: PLC0415

    return {
        "invoices": sa.table(
            "invoices",
            sa.column("id", sa.Integer()),
            sa.column("invoice_number", sa.String()),
            sa.column("order_id", sa.Integer()),
            sa.column("customer_id", sa.Integer()),
            sa.column("status", sa.String()),
            sa.column("issue_date", sa.DateTime()),
            sa.column("due_date", sa.DateTime()),
            sa.column("subtotal", sa.Float()),
            sa.column("tax_rate", sa.Float()),
            sa.column("tax_amount", sa.Float()),
            sa.column("total", sa.Float()),
            sa.column("notes", sa.Text()),
            sa.column("payment_method", sa.String()),
            sa.column("snapshot", EncryptedString()),
        ),
        "lines": sa.table(
            "invoice_line_items",
            sa.column("id", sa.Integer()),
            sa.column("invoice_id", sa.Integer()),
            sa.column("line_type", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("quantity", sa.Float()),
            sa.column("unit_price", sa.Float()),
            sa.column("total", sa.Float()),
        ),
        "customers": sa.table(
            "customers",
            sa.column("id", sa.Integer()),
            sa.column("first_name", EncryptedString()),
            sa.column("last_name", EncryptedString()),
            sa.column("company_name", EncryptedString()),
            sa.column("street", EncryptedString()),
            sa.column("postal_code", EncryptedString()),
            sa.column("city", EncryptedString()),
            sa.column("country", sa.String()),
        ),
        "orders": sa.table(
            "orders",
            sa.column("id", sa.Integer()),
            sa.column("title", sa.String()),
            sa.column("completed_at", sa.DateTime()),
        ),
        "scrap_gold": sa.table(
            "scrap_gold",
            sa.column("order_id", sa.Integer()),
            sa.column("status", sa.String()),
            sa.column("total_value_eur", sa.Float()),
        ),
    }


def _recipient(customer: Any) -> Dict[str, Optional[str]]:
    if customer is None:
        keys = ("company_name", "street", "postal_code", "city", "country")
        return {"name": "", **{k: None for k in keys}}
    return {
        "name": f"{customer.first_name or ''} {customer.last_name or ''}".strip(),
        "company_name": customer.company_name,
        "street": customer.street,
        "postal_code": customer.postal_code,
        "city": customer.city,
        "country": customer.country,
    }


def _credit(conn: sa.Connection, t: Dict[str, Any], inv: Any) -> float:
    if str(inv.status).lower() == "cancelled":
        return 0.0
    sg = t["scrap_gold"]
    rows = conn.execute(
        sa.select(sg.c.total_value_eur).where(
            sg.c.order_id == inv.order_id,
            sa.cast(sg.c.status, sa.Text()).in_(_CREDIT_STATUSES),
        )
    )
    return round(sum(_money(r[0]) for r in rows), 2)


def _snapshot(conn: sa.Connection, t: Dict[str, Any], inv: Any) -> Dict[str, Any]:
    from goldsmith_erp.core.config import settings  # noqa: PLC0415

    customer = conn.execute(
        sa.select(t["customers"]).where(t["customers"].c.id == inv.customer_id)
    ).first()
    order = conn.execute(
        sa.select(t["orders"]).where(t["orders"].c.id == inv.order_id)
    ).first()
    lines = conn.execute(
        sa.select(t["lines"])
        .where(t["lines"].c.invoice_id == inv.id)
        .order_by(t["lines"].c.id)
    ).fetchall()
    credit = _credit(conn, t, inv)
    recipient = _recipient(customer)
    return {
        "version": 1,
        "backfilled": True,
        "recipient_anonymized": recipient["name"].startswith(_ANONYMIZED_NAME),
        "captured_at": datetime.utcnow().isoformat(),
        "recipient": recipient,
        "seller": {
            "name": settings.WORKSHOP_NAME,
            "contact": settings.WORKSHOP_CONTACT,
        },
        "invoice": {
            "invoice_number": inv.invoice_number,
            "order_id": inv.order_id,
            "order_title": order.title if order is not None else None,
            "issue_date": _iso(inv.issue_date),
            "due_date": _iso(inv.due_date),
            "service_date": _iso(order.completed_at) if order is not None else None,
            "notes": inv.notes,
            "payment_method": inv.payment_method,
        },
        "lines": [
            {
                "line_type": str(line.line_type).lower(),
                "description": line.description,
                "quantity": _money(line.quantity),
                "unit_price": _money(line.unit_price),
                "total": _money(line.total),
            }
            for line in lines
        ],
        "totals": {
            "subtotal": _money(inv.subtotal),
            "tax_rate": _money(inv.tax_rate),
            "tax_amount": _money(inv.tax_amount),
            "total": _money(inv.total),
            "scrap_gold_credit": credit,
            "amount_due": round(_money(inv.total) - credit, 2),
        },
    }


def _backfill() -> None:
    conn = op.get_bind()
    t = _tables()
    invoices = t["invoices"]
    rows = conn.execute(
        sa.select(invoices).where(
            invoices.c.snapshot.is_(None),
            # PG stores a native enum: compare as text (values are lowercase).
            sa.cast(invoices.c.status, sa.Text()) != "draft",
        )
    ).fetchall()
    anonymized = 0
    for inv in rows:
        snapshot = _snapshot(conn, t, inv)
        anonymized += int(snapshot["recipient_anonymized"])
        conn.execute(
            invoices.update()
            .where(invoices.c.id == inv.id)
            .values(snapshot=json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
        )
    logger.warning(
        "W1-10 invoice snapshot backfill: %d issued invoices backfilled from "
        "current data, %d of them with an already anonymised recipient "
        "(note these in the Art. 30 record).",
        len(rows),
        anonymized,
    )


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        table_exists,
    )

    if not table_exists("invoices"):
        return
    add_column_if_not_exists(
        "invoices", sa.Column("snapshot", sa.Text(), nullable=True)
    )
    add_column_if_not_exists(
        "invoices", sa.Column("issued_at", sa.DateTime(), nullable=True)
    )
    add_column_if_not_exists(
        "invoices", sa.Column("issued_pdf", sa.Text(), nullable=True)
    )
    add_column_if_not_exists(
        "invoices", sa.Column("issued_pdf_sha256", sa.String(64), nullable=True)
    )
    _backfill()


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
    )

    # Downgrading discards the immutable copies of issued invoices; export
    # them first (§147 AO retention).
    for column in reversed(_NEW_COLUMNS):
        drop_column_if_exists("invoices", column)
