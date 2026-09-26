"""Migration tests for 20260926_sc04_scan_log_location.

SC-04 follow-up: promotes ``scan_logs.context.location_id`` (JSON-only,
per commit 2877229) into a real, indexed ``location_id`` FK column.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "alembic" / "versions" / "20260926_sc04_scan_log_location.py"
_REVISION = "20260926_sc04_scan_log_location"


def _load_migration():
    spec = importlib.util.spec_from_file_location("sc04_scan_log_location", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sc04.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE workshop_locations (id INTEGER PRIMARY KEY,"
                " name VARCHAR(50))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE scan_logs (id VARCHAR(36) PRIMARY KEY,"
                " scanned_at DATETIME, raw_payload VARCHAR(500),"
                " context JSON)"
            )
        )
        conn.execute(text("INSERT INTO workshop_locations VALUES (1, 'Werkbank 1')"))
        conn.execute(
            text(
                "INSERT INTO scan_logs (id, scanned_at, raw_payload, context)"
                " VALUES (:id, :scanned_at, :raw_payload, :context)"
            ),
            [
                {
                    "id": "a",
                    "scanned_at": "2026-09-25 10:00:00",
                    "raw_payload": "ORDER:1",
                    "context": json.dumps(
                        {"location_id": 1, "current_location": "Werkbank 1"}
                    ),
                },
                {
                    "id": "b",
                    "scanned_at": "2026-09-25 10:05:00",
                    "raw_payload": "ORDER:2",
                    "context": json.dumps({"current_location": "Werkbank 1"}),
                },
                {
                    "id": "c",
                    "scanned_at": "2026-09-25 10:10:00",
                    "raw_payload": "ORDER:3",
                    "context": None,
                },
            ],
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


def _location_ids(engine) -> dict[str, object]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, location_id FROM scan_logs ORDER BY id")
        ).all()
    return dict(rows)


def test_revision_sits_on_top_of_w8_in_the_single_chain():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_w8_workshop_locations"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    # A later migration may land on top of this one — only the single-chain
    # invariant is this test's business, not literal head-ness.
    assert len(script.get_heads()) == 1


def test_upgrade_adds_column_and_index(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    insp = inspect(sqlite_engine)
    columns = {c["name"] for c in insp.get_columns("scan_logs")}
    assert "location_id" in columns
    index_names = {ix["name"] for ix in insp.get_indexes("scan_logs")}
    assert "ix_scan_logs_location_id" in index_names


def test_upgrade_backfills_location_id_from_context_json(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    assert _location_ids(sqlite_engine) == {"a": 1, "b": None, "c": None}


def test_round_trip_is_idempotent(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")
    assert _location_ids(sqlite_engine) == {"a": 1, "b": None, "c": None}

    _run(sqlite_engine, "downgrade")
    insp = inspect(sqlite_engine)
    assert "location_id" not in {c["name"] for c in insp.get_columns("scan_logs")}
    with sqlite_engine.connect() as conn:
        # The JSON copy is untouched by the downgrade — no data lost.
        context = conn.execute(
            text("SELECT context FROM scan_logs WHERE id = 'a'")
        ).scalar_one()
    assert json.loads(context)["location_id"] == 1

    _run(sqlite_engine, "downgrade")
    _run(sqlite_engine, "upgrade")
    assert _location_ids(sqlite_engine) == {"a": 1, "b": None, "c": None}
