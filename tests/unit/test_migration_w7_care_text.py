"""Migration tests for 20260925_w7_care_text (W7 followup)."""

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
_PATH = _ROOT / "alembic" / "versions" / "20260925_w7_care_text.py"
_REVISION = "20260925_w7_care_text"


def _load_migration():
    spec = importlib.util.spec_from_file_location("w7_care_text_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w7_care_text.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE workshop_settings (id INTEGER PRIMARY KEY,"
                " name VARCHAR NOT NULL)"
            )
        )
        conn.execute(
            text("INSERT INTO workshop_settings (id, name) VALUES (1, 'Test')")
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
    return {c["name"] for c in inspect(engine).get_columns("workshop_settings")}


def test_revision_is_the_single_head_on_top_of_arch5_jobs():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_arch5_jobs"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert _REVISION in {rev.revision for rev in script.walk_revisions()}


def test_upgrade_adds_nullable_care_text_existing_row_untouched(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    assert "care_text" in _columns(sqlite_engine)
    with sqlite_engine.connect() as conn:
        row = conn.execute(
            text("SELECT name, care_text FROM workshop_settings WHERE id = 1")
        ).one()
    assert row == ("Test", None)


def test_round_trip_is_idempotent(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    assert "care_text" not in _columns(sqlite_engine)
    _run(sqlite_engine, "downgrade")
    _run(sqlite_engine, "upgrade")
    assert "care_text" in _columns(sqlite_engine)
