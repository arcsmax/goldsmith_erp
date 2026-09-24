"""Migration tests for 20260925_c22_cu_dedupe (C2.2).

Same pattern as test_migration_gdpr01_consents.py: run ``upgrade()`` /
``downgrade()`` on a scratch SQLite DB and check ORM parity.
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
    / "20260925_c22_customer_update_dedupe.py"
)
_INDEX = "uq_customer_updates_dedupe_key"


def _load_migration():
    spec = importlib.util.spec_from_file_location("c22_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'c22.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE customer_updates (id INTEGER PRIMARY KEY,"
                " status TEXT NOT NULL)"
            )
        )
        conn.execute(text("INSERT INTO customer_updates VALUES (1, 'sent')"))
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


def _insert(engine, row_id: int, key, status: str) -> None:
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO customer_updates VALUES (:id, :s, :k)"),
            {"id": row_id, "s": status, "k": key},
        )
        conn.commit()


def test_revision_chain_points_at_previous_head():
    module = _load_migration()
    assert module.revision == "20260925_c22_cu_dedupe"
    assert module.down_revision == "20260925_w110_invoice_snap"


def test_upgrade_adds_column_and_partial_unique_index(sqlite_engine):
    _run(sqlite_engine, "upgrade")

    insp = inspect(sqlite_engine)
    assert "dedupe_key" in {c["name"] for c in insp.get_columns("customer_updates")}
    assert _INDEX in {i["name"] for i in insp.get_indexes("customer_updates")}

    _insert(sqlite_engine, 2, "auto:order:1:pickup_ready", "send_failed")
    _insert(sqlite_engine, 3, "auto:order:1:pickup_ready", "sent")
    _insert(sqlite_engine, 4, None, "sent")
    _insert(sqlite_engine, 5, None, "sent")
    with pytest.raises(IntegrityError):
        _insert(sqlite_engine, 6, "auto:order:1:pickup_ready", "draft")


def test_upgrade_is_idempotent(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")


def test_downgrade_removes_both_and_reupgrade_works(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    insp = inspect(sqlite_engine)
    assert "dedupe_key" not in {c["name"] for c in insp.get_columns("customer_updates")}
    _run(sqlite_engine, "downgrade")
    _run(sqlite_engine, "upgrade")
    assert _INDEX in {
        i["name"] for i in inspect(sqlite_engine).get_indexes("customer_updates")
    }


def test_orm_create_all_declares_the_same_index(tmp_path):
    from goldsmith_erp.db.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'orm.db'}", future=True)
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as conn:
            ddl = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE name = :n"), {"n": _INDEX}
            ).scalar_one()
        assert "UNIQUE" in ddl
        assert "status <> 'send_failed'" in ddl
    finally:
        engine.dispose()
