"""Migration tests for 20260925_w117_one_running (BE-12, W1-17).

Same pattern as test_migration_gdpr01_consents.py: load the migration by
file path, run ``upgrade()`` / ``downgrade()`` on a scratch SQLite DB via
MigrationContext/Operations, and check ORM parity.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic.migration import MigrationContext
from alembic.operations import Operations

_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260925_w117_one_running_timer.py"
)
_INDEX = "uq_time_entries_one_running"


def _load_migration():
    spec = importlib.util.spec_from_file_location("w117_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w117.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE time_entries (id TEXT PRIMARY KEY, user_id INTEGER"
                " NOT NULL, start_time TIMESTAMP NOT NULL, end_time TIMESTAMP)"
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


def _insert(engine, entry_id: str, user_id: int, ended: bool) -> None:
    end = "CURRENT_TIMESTAMP" if ended else "NULL"
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO time_entries (id, user_id, start_time, end_time)"
                f" VALUES (:id, :uid, CURRENT_TIMESTAMP, {end})"
            ),
            {"id": entry_id, "uid": user_id},
        )
        conn.commit()


def _index_names(engine) -> set[str]:
    return {i["name"] for i in inspect(engine).get_indexes("time_entries")}


def test_revision_chain_points_at_previous_head():
    module = _load_migration()
    assert module.revision == "20260925_w117_one_running"
    assert module.down_revision == "20260925_gdpr01_consents"


def test_upgrade_creates_partial_unique_index(sqlite_engine):
    _insert(sqlite_engine, "a", 1, ended=True)
    _insert(sqlite_engine, "b", 1, ended=True)

    _run(sqlite_engine, "upgrade")

    assert _INDEX in _index_names(sqlite_engine)
    _insert(sqlite_engine, "c", 1, ended=False)  # one running: fine
    _insert(sqlite_engine, "d", 2, ended=False)  # other user: fine
    with pytest.raises(IntegrityError):
        _insert(sqlite_engine, "e", 1, ended=False)


def test_upgrade_is_idempotent(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")
    assert _INDEX in _index_names(sqlite_engine)


def test_upgrade_refuses_existing_duplicates_with_counts(sqlite_engine):
    _insert(sqlite_engine, "a", 7, ended=False)
    _insert(sqlite_engine, "b", 7, ended=False)

    with pytest.raises(RuntimeError, match="user_id=7: 2 offen"):
        _run(sqlite_engine, "upgrade")
    assert _INDEX not in _index_names(sqlite_engine)


def test_downgrade_drops_index_and_reupgrade_works(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    assert _INDEX not in _index_names(sqlite_engine)

    _run(sqlite_engine, "downgrade")  # idempotent no-op
    _run(sqlite_engine, "upgrade")
    assert _INDEX in _index_names(sqlite_engine)


def test_orm_create_all_declares_the_same_partial_index(tmp_path):
    from goldsmith_erp.db.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'orm.db'}", future=True)
    try:
        Base.metadata.create_all(engine)
        indexes = {i["name"]: i for i in inspect(engine).get_indexes("time_entries")}
        assert indexes[_INDEX]["unique"]
        assert indexes[_INDEX]["column_names"] == ["user_id"]
        with engine.connect() as conn:
            ddl = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE name = :n"), {"n": _INDEX}
            ).scalar_one()
        assert "end_time IS NULL" in ddl
    finally:
        engine.dispose()
