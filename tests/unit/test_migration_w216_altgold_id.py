"""Migration tests for 20260925_w216_altgold_id (W2-16, DOM-21)."""

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
_PATH = _ROOT / "alembic" / "versions" / "20260925_w216_altgold_id.py"
_REVISION = "20260925_w216_altgold_id"
_ID_COLUMNS = {
    "id_document_type",
    "id_document_number",
    "id_issuing_authority",
    "id_checked_by",
    "id_checked_at",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("w216_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w216.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE scrap_gold (id INTEGER PRIMARY KEY,"
                " order_id INTEGER NOT NULL, created_by INTEGER NOT NULL,"
                " status VARCHAR(20) NOT NULL, total_value_eur FLOAT)"
            )
        )
        conn.execute(text("INSERT INTO scrap_gold VALUES (1, 1, 1, 'signed', 2500.0)"))
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
    return {c["name"] for c in inspect(engine).get_columns("scrap_gold")}


def test_revision_is_the_single_head_on_top_of_w214():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_w214_interrupt_resume"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert _REVISION in {rev.revision for rev in script.walk_revisions()}


def test_upgrade_adds_nullable_id_columns_existing_rows_untouched(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    assert _ID_COLUMNS <= _columns(sqlite_engine)
    with sqlite_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status, id_document_type, id_document_number"
                " FROM scrap_gold WHERE id = 1"
            )
        ).one()
    assert row == ("signed", None, None)


def test_round_trip_is_idempotent(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    assert not _ID_COLUMNS & _columns(sqlite_engine)
    _run(sqlite_engine, "downgrade")
    _run(sqlite_engine, "upgrade")
    assert _ID_COLUMNS <= _columns(sqlite_engine)
