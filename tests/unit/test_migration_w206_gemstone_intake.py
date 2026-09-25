"""Migration tests for 20260925_w206_gemstone_intake (W2-06, DOM-04).

Same pattern as test_migration_w207_order_events.py: load the migration by
file path and run ``upgrade()`` / ``downgrade()`` on a scratch SQLite DB.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "alembic" / "versions" / "20260925_w206_gemstone_intake.py"
_REVISION = "20260925_w206_gemstone_intake"


def _load_migration():
    spec = importlib.util.spec_from_file_location("w206_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w206.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE gemstones (id INTEGER PRIMARY KEY,"
                " order_id INTEGER NOT NULL, type VARCHAR(50) NOT NULL,"
                " cost FLOAT NOT NULL, quantity INTEGER,"
                " setting_type VARCHAR(100))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO gemstones (id, order_id, type, cost, quantity)"
                " VALUES (1, 1, 'diamond', 120.0, 3)"
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


def _columns(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("gemstones")}


def test_revision_sits_on_top_of_w204_in_the_single_chain():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_w204_invoice_ustg14"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert _REVISION in {rev.revision for rev in script.walk_revisions()}


def test_upgrade_adds_customer_stone_flag_defaulting_to_false(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    assert "is_customer_stone" in _columns(sqlite_engine)
    with sqlite_engine.connect() as conn:
        value = conn.execute(
            text("SELECT is_customer_stone FROM gemstones WHERE id = 1")
        ).scalar_one()
    assert value in (0, False)


def test_upgrade_is_idempotent_and_round_trips(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    assert "is_customer_stone" not in _columns(sqlite_engine)
    _run(sqlite_engine, "downgrade")  # no-op
    _run(sqlite_engine, "upgrade")
    assert "is_customer_stone" in _columns(sqlite_engine)
    with sqlite_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM gemstones")).scalar_one()
    assert count == 1
