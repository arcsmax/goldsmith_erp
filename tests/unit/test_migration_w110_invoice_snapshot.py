"""Migration tests for 20260925_w110_invoice_snap (W1-10: GDPR-01, BE-23).

Same pattern as test_migration_gdpr01_consents.py: load the migration by
file path and run ``upgrade()`` / ``downgrade()`` on a scratch SQLite DB
holding a minimal pre-W1-10 schema, then check the backfill and ORM parity.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations
from goldsmith_erp.db.types import EncryptedString

_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260925_w110_invoice_snapshot.py"
)
_COLUMNS = {"snapshot", "issued_at", "issued_pdf", "issued_pdf_sha256"}


def _load_migration():
    spec = importlib.util.spec_from_file_location("w110_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_LEGACY_DDL = [
    "CREATE TABLE customers (id INTEGER PRIMARY KEY, first_name TEXT NOT NULL,"
    " last_name TEXT NOT NULL, company_name TEXT, street TEXT, postal_code TEXT,"
    " city TEXT, country TEXT)",
    "CREATE TABLE orders (id INTEGER PRIMARY KEY, title TEXT, completed_at"
    " TIMESTAMP)",
    "CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_number TEXT,"
    " order_id INTEGER, customer_id INTEGER, status TEXT, issue_date TIMESTAMP,"
    " due_date TIMESTAMP, subtotal FLOAT, tax_rate FLOAT, tax_amount FLOAT,"
    " total FLOAT, notes TEXT, payment_method TEXT)",
    "CREATE TABLE invoice_line_items (id INTEGER PRIMARY KEY, invoice_id"
    " INTEGER, line_type TEXT, description TEXT, quantity FLOAT, unit_price"
    " FLOAT, total FLOAT)",
    "CREATE TABLE scrap_gold (id INTEGER PRIMARY KEY, order_id INTEGER, status"
    " TEXT, total_value_eur FLOAT)",
]


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w110.db'}", future=True)
    now = datetime(2026, 9, 1, 10, 0)
    with engine.connect() as conn:
        for ddl in _LEGACY_DDL:
            conn.execute(text(ddl))
        conn.execute(
            text(
                "INSERT INTO customers VALUES (1, 'Erika', 'Muster', NULL,"
                " 'Ringweg 5', '80331', 'München', 'Deutschland'),"
                " (2, '[GELÖSCHT]', '[GELÖSCHT]', NULL, NULL, NULL, NULL, NULL)"
            )
        )
        conn.execute(
            text("INSERT INTO orders VALUES (10, 'Ehering', :d), (11, 'Kette', NULL)"),
            {"d": now},
        )
        rows = [
            (100, "RE-2026-0001", 10, 1, "sent"),
            (101, "RE-2026-0002", 11, 1, "draft"),
            (102, "RE-2026-0003", 11, 2, "paid"),
        ]
        for inv_id, number, order_id, cust_id, status in rows:
            conn.execute(
                text(
                    "INSERT INTO invoices VALUES (:id, :n, :o, :c, :s, :i, :d,"
                    " 500.0, 19.0, 95.0, 595.0, 'Danke', 'Ueberweisung')"
                ),
                {
                    "id": inv_id,
                    "n": number,
                    "o": order_id,
                    "c": cust_id,
                    "s": status,
                    "i": now,
                    "d": now + timedelta(days=14),
                },
            )
        conn.execute(
            text(
                "INSERT INTO invoice_line_items VALUES"
                " (1, 100, 'other', 'Auftrag: Ehering', 1.0, 500.0, 500.0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO scrap_gold VALUES (1, 10, 'credited', 120.5),"
                " (2, 10, 'received', 999.0)"
            )
        )
        conn.commit()
    yield engine
    engine.dispose()


def _run(engine, fn_name: str) -> None:
    module = _load_migration()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn_name)()
        conn.commit()


def _raw_snapshot(engine, invoice_id: int):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT snapshot FROM invoices WHERE id = :id"), {"id": invoice_id}
        ).scalar_one()


def _snapshot(engine, invoice_id: int):
    raw = _raw_snapshot(engine, invoice_id)
    if raw is None:
        return None
    plain = EncryptedString().process_result_value(raw, engine.dialect)
    return json.loads(plain)


def test_revision_chain_points_at_previous_head():
    module = _load_migration()
    assert module.revision == "20260925_w110_invoice_snap"
    assert module.down_revision == "20260925_w117_one_running"


def test_upgrade_adds_columns_and_backfills_issued_invoices(sqlite_engine):
    _run(sqlite_engine, "upgrade")

    cols = {c["name"] for c in inspect(sqlite_engine).get_columns("invoices")}
    assert _COLUMNS <= cols

    sent = _snapshot(sqlite_engine, 100)
    assert sent["backfilled"] is True
    assert sent["recipient_anonymized"] is False
    assert sent["recipient"]["name"] == "Erika Muster"
    assert sent["recipient"]["city"] == "München"
    assert sent["invoice"]["invoice_number"] == "RE-2026-0001"
    assert sent["invoice"]["service_date"] == "2026-09-01T10:00:00"
    assert sent["lines"][0]["description"] == "Auftrag: Ehering"
    assert sent["totals"]["scrap_gold_credit"] == pytest.approx(120.5)
    assert sent["totals"]["amount_due"] == pytest.approx(474.5)

    assert _snapshot(sqlite_engine, 101) is None  # DRAFT: lazily, not here
    assert _snapshot(sqlite_engine, 102)["recipient_anonymized"] is True


def test_backfilled_snapshot_is_encrypted_at_rest(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    raw = _raw_snapshot(sqlite_engine, 100)
    assert "Erika" not in raw
    assert "Ringweg" not in raw


def test_upgrade_is_idempotent_and_does_not_overwrite(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    first = _raw_snapshot(sqlite_engine, 100)
    _run(sqlite_engine, "upgrade")
    assert _raw_snapshot(sqlite_engine, 100) == first


def test_downgrade_drops_columns_and_reupgrade_works(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    cols = {c["name"] for c in inspect(sqlite_engine).get_columns("invoices")}
    assert not (_COLUMNS & cols)

    _run(sqlite_engine, "downgrade")  # idempotent no-op
    _run(sqlite_engine, "upgrade")
    assert _snapshot(sqlite_engine, 100)["backfilled"] is True


def test_backfill_layout_matches_the_service_snapshot(sqlite_engine):
    from goldsmith_erp.services.invoice_snapshot_service import InvoiceSnapshotService

    _run(sqlite_engine, "upgrade")
    backfilled = _snapshot(sqlite_engine, 100)
    invoice = SimpleNamespace(
        invoice_number="X",
        order_id=1,
        issue_date=None,
        due_date=None,
        notes=None,
        payment_method=None,
        subtotal=0,
        tax_rate=19,
        tax_amount=0,
        total=0,
    )
    service = InvoiceSnapshotService.build(invoice, [], None, None)  # type: ignore[arg-type]

    assert set(service) <= set(backfilled)
    # Snapshot version 2 (W2-04) added the Storno reference to the invoice
    # header; the v1 layout the migration writes is otherwise identical and
    # still renders (InvoiceSnapshotService.render reads those keys with get).
    v2_header_keys = {"cancels_invoice_number", "cancels_invoice_date", "storno_reason"}
    for section in ("recipient", "seller", "invoice", "totals"):
        extra = v2_header_keys if section == "invoice" else set()
        assert set(service[section]) - extra == set(backfilled[section]), section


def test_orm_create_all_has_the_snapshot_columns(tmp_path):
    from goldsmith_erp.db.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'orm.db'}", future=True)
    try:
        Base.metadata.create_all(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("invoices")}
        assert _COLUMNS <= cols
    finally:
        engine.dispose()
