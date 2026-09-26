"""Migration tests for 20260925_be14_numeric (BE-14: Float money -> NUMERIC).

Same pattern as test_migration_w207_order_events.py: load the migration by
file path and run ``upgrade()`` / ``downgrade()`` on a scratch SQLite DB via
MigrationContext/Operations; the chain position is checked through the real
alembic script directory.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Float, Numeric, create_engine, inspect, text

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "alembic" / "versions" / "20260925_be14_numeric_money.py"
_REVISION = "20260925_be14_numeric"


def _load_migration():
    spec = importlib.util.spec_from_file_location("be14_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    module = _load_migration()
    engine = create_engine(f"sqlite:///{tmp_path / 'be14.db'}", future=True)
    with engine.connect() as conn:
        for table, columns in module._by_table().items():
            cols = ", ".join(f"{name} FLOAT" for name, _ in columns)
            conn.execute(
                text(
                    f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, note VARCHAR, {cols})"
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


def test_revision_sits_on_top_of_w6_outbox_in_the_single_chain():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_w6_outbox"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert _REVISION in {rev.revision for rev in script.walk_revisions()}


def test_inventory_matches_the_orm_numeric_columns():
    """Every Numeric column of the model is in the migration and vice versa."""
    from goldsmith_erp.db.models import Base

    module = _load_migration()
    in_migration = {(t, c): spec for t, c, spec in module.COLUMNS}
    in_model = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, Numeric) and not isinstance(column.type, Float):
                in_model[(table.name, column.name)] = (
                    column.type.precision,
                    column.type.scale,
                )
    # activities.hourly_rate was Numeric(10, 2) before this migration.
    in_model.pop(("activities", "hourly_rate"))
    assert in_model == in_migration


def test_upgrade_converts_types_and_keeps_values(sqlite_engine):
    with sqlite_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO invoices (id, note, subtotal, tax_rate, tax_amount, total)"
                " VALUES (1, 'keep', 3.01, 19.0, 0.5719, 3.5819)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO metal_purchases (id, weight_g, remaining_weight_g,"
                " price_total, price_per_gram) VALUES (1, 12.3456, 10.0, 1234.5, 95.43219)"
            )
        )
        conn.commit()

    _run(sqlite_engine, "upgrade")

    insp = inspect(sqlite_engine)
    types = {c["name"]: c["type"] for c in insp.get_columns("invoices")}
    assert isinstance(types["total"], Numeric) and not isinstance(types["total"], Float)
    assert (types["total"].precision, types["total"].scale) == (12, 2)
    assert (types["tax_rate"].precision, types["tax_rate"].scale) == (5, 2)
    mp = {c["name"]: c["type"] for c in insp.get_columns("metal_purchases")}
    assert (mp["weight_g"].precision, mp["weight_g"].scale) == (12, 3)
    assert (mp["price_per_gram"].precision, mp["price_per_gram"].scale) == (12, 4)

    with sqlite_engine.connect() as conn:
        row = conn.execute(
            text("SELECT note, subtotal, total FROM invoices WHERE id = 1")
        ).one()
    # Data and unrelated columns survive the table rebuild.
    assert row.note == "keep"
    assert Decimal(str(row.subtotal)) == Decimal("3.01")


def test_downgrade_restores_float_and_round_trips(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    insp = inspect(sqlite_engine)
    types = {c["name"]: c["type"] for c in insp.get_columns("orders")}
    assert isinstance(types["price"], Float)
    _run(sqlite_engine, "upgrade")
    types = {c["name"]: c["type"] for c in inspect(sqlite_engine).get_columns("orders")}
    assert (types["price"].precision, types["price"].scale) == (12, 2)


def test_upgrade_fails_loudly_on_schema_drift(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'drift.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, price FLOAT)"))
        conn.commit()
    with pytest.raises(RuntimeError, match="missing"):
        _run(engine, "upgrade")
    engine.dispose()
