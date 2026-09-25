"""Migration tests for 20260925_w214_interrupt_resume (W2-14, BE-19)."""

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
_PATH = _ROOT / "alembic" / "versions" / "20260925_w214_interrupt_resume.py"
_REVISION = "20260925_w214_interrupt_resume"


def _load_migration():
    spec = importlib.util.spec_from_file_location("w214_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w214.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE interruptions (id INTEGER PRIMARY KEY,"
                " time_entry_id VARCHAR(36) NOT NULL, reason VARCHAR(100) NOT NULL,"
                " duration_minutes INTEGER NOT NULL, timestamp TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO interruptions VALUES"
                " (1, 'e1', 'kundenanruf', 12, '2026-09-25 10:00:00')"
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
    return {c["name"] for c in inspect(engine).get_columns("interruptions")}


def test_revision_sits_on_top_of_w206_in_the_single_chain():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_w206_gemstone_intake"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert _REVISION in {rev.revision for rev in script.walk_revisions()}


def test_upgrade_adds_nullable_resumed_at_and_keeps_durations(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    assert "resumed_at" in _columns(sqlite_engine)
    with sqlite_engine.connect() as conn:
        row = conn.execute(
            text("SELECT duration_minutes, resumed_at FROM interruptions")
        ).one()
    assert row == (12, None)


def test_round_trip_is_idempotent(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    assert "resumed_at" not in _columns(sqlite_engine)
    _run(sqlite_engine, "downgrade")
    _run(sqlite_engine, "upgrade")
    assert "resumed_at" in _columns(sqlite_engine)
