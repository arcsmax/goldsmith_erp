"""Migration tests for W2-10 (customer email optional) and W2-04 (§14 UStG
invoices, workshop settings, Storno link, per-year counters).

Same pattern as test_migration_w207_order_events.py: each migration is loaded
by file path and ``upgrade()`` / ``downgrade()`` run on a scratch SQLite DB
through MigrationContext/Operations; the chain position is checked through
the real alembic script directory (alembic.ini). Both are run up, down, up.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from goldsmith_erp.core.encryption import hmac_blind_index

_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS = _ROOT / "alembic" / "versions"
_W210 = "20260925_w210_email_optional"
_W204 = "20260925_w204_invoice_ustg14"


def _load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, str(_VERSIONS / filename))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _w210():
    return _load("20260925_w210_customer_email_optional.py", "w210_migration")


def _w204():
    return _load("20260925_w204_invoice_ustg14.py", "w204_migration")


def _run(engine, module, fn_name: str) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn_name)()
        conn.commit()


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'w2.db'}", future=True)
    with eng.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR)"))
        conn.execute(
            text(
                "CREATE TABLE customers (id INTEGER PRIMARY KEY,"
                " first_name TEXT NOT NULL, email TEXT NOT NULL,"
                " email_hash VARCHAR(64) NOT NULL, phone TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX ix_customers_email_hash ON customers (email_hash)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE invoices (id INTEGER PRIMARY KEY,"
                " invoice_number VARCHAR(20) NOT NULL UNIQUE,"
                " order_id INTEGER NOT NULL, status VARCHAR(9) NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE quotes (id INTEGER PRIMARY KEY,"
                " quote_number VARCHAR(20) NOT NULL UNIQUE)"
            )
        )
        conn.commit()
    yield eng
    eng.dispose()


# --------------------------------------------------------------------------
# Chain
# --------------------------------------------------------------------------


def test_chain_is_linear_w207_w210_w204():
    assert _w210().revision == _W210
    assert _w210().down_revision == "20260925_w207_order_events"
    assert _w204().revision == _W204
    assert _w204().down_revision == _W210
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert script.get_heads() == [_W204]


# --------------------------------------------------------------------------
# W2-10
# --------------------------------------------------------------------------


def _columns(engine, table: str) -> dict:
    return {c["name"]: c for c in inspect(engine).get_columns(table)}


def _insert_customer(engine, customer_id: int, email, email_hash) -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO customers (id, first_name, email, email_hash)"
                " VALUES (:id, 'x', :email, :hash)"
            ),
            {"id": customer_id, "email": email, "hash": email_hash},
        )
        conn.commit()


def test_w210_makes_email_optional_and_unique_only_when_present(engine):
    _insert_customer(engine, 1, "cipher-a", "hash-a")
    _run(engine, _w210(), "upgrade")

    cols = _columns(engine, "customers")
    assert cols["email"]["nullable"] is True
    assert cols["email_hash"]["nullable"] is True
    _insert_customer(engine, 2, None, None)
    _insert_customer(engine, 3, None, None)  # two NULLs never collide
    with pytest.raises(IntegrityError):
        _insert_customer(engine, 4, "cipher-b", "hash-a")  # present -> unique


def test_w210_down_up_round_trip_restores_null_emails(engine):
    _insert_customer(engine, 1, "cipher-a", "hash-a")
    module = _w210()
    _run(engine, module, "upgrade")
    _insert_customer(engine, 2, None, None)

    _run(engine, module, "downgrade")
    cols = _columns(engine, "customers")
    assert cols["email"]["nullable"] is False
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT email, email_hash FROM customers WHERE id = 2")
        ).one()
    assert row[0] is not None
    assert row[1] == hmac_blind_index(module.placeholder_email(2))

    _run(engine, module, "upgrade")
    with engine.connect() as conn:
        rows = dict(
            conn.execute(text("SELECT id, email_hash FROM customers ORDER BY id")).all()
        )
    assert rows == {1: "hash-a", 2: None}


def test_w210_upgrade_is_idempotent(engine):
    module = _w210()
    _run(engine, module, "upgrade")
    _run(engine, module, "upgrade")
    indexes = {i["name"] for i in inspect(engine).get_indexes("customers")}
    assert "ix_customers_email_hash" in indexes


# --------------------------------------------------------------------------
# W2-04
# --------------------------------------------------------------------------


def _insert_invoice(engine, invoice_id: int, number: str, order_id: int, status: str):
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO invoices (id, invoice_number, order_id, status)"
                " VALUES (:id, :n, :o, :s)"
            ),
            {"id": invoice_id, "n": number, "o": order_id, "s": status},
        )
        conn.commit()


def _sequences(engine) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT kind, year, last_value FROM number_sequences")
        ).all()
    return {(r[0], r[1]): r[2] for r in rows}


def test_w204_creates_tables_columns_and_seeds_counters_numerically(engine):
    _insert_invoice(engine, 1, "RE-2026-9999", 1, "sent")
    _insert_invoice(engine, 2, "RE-2026-10000", 2, "paid")
    _insert_invoice(engine, 3, "RE-2025-0042", 3, "cancelled")
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO quotes (id, quote_number) VALUES (1, 'KV-2026-0007')")
        )
        conn.commit()

    _run(engine, _w204(), "upgrade")

    insp = inspect(engine)
    assert {"workshop_settings", "number_sequences"} <= set(insp.get_table_names())
    cols = _columns(engine, "invoices")
    assert {"cancels_invoice_id", "service_date"} <= set(cols)
    settings_cols = set(_columns(engine, "workshop_settings"))
    assert {
        "name",
        "owner_name",
        "street",
        "postal_code",
        "city",
        "phone",
        "email",
        "tax_number",
        "vat_id",
        "iban",
        "bic",
        "is_kleinunternehmer",
        "default_vat_rate",
        "invoice_footer",
    } <= settings_cols
    # String MAX would say 9999; the seed must be numeric.
    assert _sequences(engine) == {
        ("RE", 2026): 10000,
        ("RE", 2025): 42,
        ("KV", 2026): 7,
    }


def test_w204_one_live_invoice_per_order_but_storno_and_cancelled_allowed(engine):
    _insert_invoice(engine, 1, "RE-2026-0001", 7, "cancelled")
    _run(engine, _w204(), "upgrade")
    _insert_invoice(engine, 2, "RE-2026-0002", 7, "sent")
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO invoices (id, invoice_number, order_id, status,"
                " cancels_invoice_id) VALUES (3, 'RE-2026-0003', 7, 'sent', 1)"
            )
        )
        conn.commit()
    with pytest.raises(IntegrityError):
        _insert_invoice(engine, 4, "RE-2026-0004", 7, "draft")


def test_w204_stops_when_an_order_already_has_two_live_invoices(engine):
    _insert_invoice(engine, 1, "RE-2026-0001", 5, "sent")
    _insert_invoice(engine, 2, "RE-2026-0002", 5, "draft")
    with pytest.raises(RuntimeError, match="5"):
        _run(engine, _w204(), "upgrade")


def test_w204_down_up_round_trip(engine):
    _insert_invoice(engine, 1, "RE-2026-0003", 1, "sent")
    module = _w204()
    _run(engine, module, "upgrade")
    _run(engine, module, "downgrade")

    insp = inspect(engine)
    assert "workshop_settings" not in insp.get_table_names()
    assert "number_sequences" not in insp.get_table_names()
    assert "cancels_invoice_id" not in _columns(engine, "invoices")

    _run(engine, module, "upgrade")
    _run(engine, module, "upgrade")  # idempotent
    assert _sequences(engine) == {("RE", 2026): 3}
