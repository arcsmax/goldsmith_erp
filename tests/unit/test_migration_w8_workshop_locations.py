"""Migration tests for 20260925_w8_workshop_locations (Standorte)."""

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
_PATH = _ROOT / "alembic" / "versions" / "20260925_w8_workshop_locations.py"
_REVISION = "20260925_w8_workshop_locations"


def _load_migration():
    spec = importlib.util.spec_from_file_location("w8_locations", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w8.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE orders (id INTEGER PRIMARY KEY,"
                " current_location VARCHAR(50))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE time_entries (id VARCHAR(36) PRIMARY KEY,"
                " location VARCHAR(50))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE location_history (id INTEGER PRIMARY KEY,"
                " order_id INTEGER, location VARCHAR(50) NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO orders VALUES (1, 'Tresor'), (2, '  Werkbank 1 '),"
                " (3, NULL), (4, '   ')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO time_entries VALUES ('a', 'Werkbank 1'),"
                " ('b', 'werkbank 1'), ('c', NULL), ('d', 'Ausstellung')"
            )
        )
        conn.execute(text("INSERT INTO location_history VALUES (1, 1, 'Gießerei')"))
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


def _locations(engine) -> dict[str, str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name, kind FROM workshop_locations")).all()
    return {name: kind for name, kind in rows}


def test_revision_sits_on_top_of_w7_in_the_single_chain():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_w7_care_text"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert script.get_heads() == [_REVISION]


def test_upgrade_seeds_distinct_trimmed_strings(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    locations = _locations(sqlite_engine)
    # "Werkbank 1" / " Werkbank 1 " / "werkbank 1" collapse into one row;
    # NULL and blank values are skipped.
    assert sorted(n.lower() for n in locations) == [
        "ausstellung",
        "gießerei",
        "tresor",
        "werkbank 1",
    ]
    by_lower = {n.lower(): k for n, k in locations.items()}
    assert by_lower["tresor"] == "safe"
    assert by_lower["werkbank 1"] == "bench"
    assert by_lower["ausstellung"] == "showroom"


def test_upgrade_backfills_location_id_by_name(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    with sqlite_engine.connect() as conn:
        ids = dict(
            conn.execute(text("SELECT lower(name), id FROM workshop_locations")).all()
        )
        orders = dict(conn.execute(text("SELECT id, location_id FROM orders")).all())
        entries = dict(
            conn.execute(text("SELECT id, location_id FROM time_entries")).all()
        )
    assert orders == {1: ids["tresor"], 2: ids["werkbank 1"], 3: None, 4: None}
    assert entries == {
        "a": ids["werkbank 1"],
        "b": ids["werkbank 1"],
        "c": None,
        "d": ids["ausstellung"],
    }


def test_round_trip_is_idempotent_and_keeps_text_columns(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")
    assert len(_locations(sqlite_engine)) == 4
    _run(sqlite_engine, "downgrade")
    insp = inspect(sqlite_engine)
    assert "workshop_locations" not in insp.get_table_names()
    assert "location_id" not in {c["name"] for c in insp.get_columns("orders")}
    with sqlite_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT current_location FROM orders WHERE id = 1")
            ).scalar_one()
            == "Tresor"
        )
    _run(sqlite_engine, "downgrade")
    _run(sqlite_engine, "upgrade")
    assert len(_locations(sqlite_engine)) == 4
