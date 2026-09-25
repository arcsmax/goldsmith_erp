"""Migration tests for 20260925_w6_outbox (ARCH-04 / ARCH-05)."""

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

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "alembic" / "versions" / "20260925_w6_outbox_messages.py"
_REVISION = "20260925_w6_outbox"


def _load_migration():
    spec = importlib.util.spec_from_file_location("w6_outbox_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w6.db'}", future=True)
    yield engine
    engine.dispose()


def _run(engine, fn_name: str) -> None:
    module = _load_migration()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn_name)()
        conn.commit()


def test_revision_is_the_single_head_on_top_of_w216():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_w216_altgold_id"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert _REVISION in {rev.revision for rev in script.walk_revisions()}


def test_upgrade_creates_table_with_defaults_and_unique_dedupe(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    cols = {c["name"] for c in inspect(sqlite_engine).get_columns("outbox_messages")}
    assert cols == {
        "id",
        "kind",
        "payload",
        "dedupe_key",
        "status",
        "attempts",
        "next_attempt_at",
        "last_error",
        "created_at",
        "sent_at",
    }
    with sqlite_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO outbox_messages (kind, payload, dedupe_key)"
                " VALUES ('customer_update', '{}', 'k1')"
            )
        )
        # NULL dedupe keys never collide.
        conn.execute(
            text("INSERT INTO outbox_messages (kind, payload) VALUES ('x', '{}')")
        )
        conn.execute(
            text("INSERT INTO outbox_messages (kind, payload) VALUES ('x', '{}')")
        )
        row = conn.execute(
            text("SELECT status, attempts FROM outbox_messages WHERE id = 1")
        ).one()
        assert tuple(row) == ("pending", 0)
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO outbox_messages (kind, payload, dedupe_key)"
                    " VALUES ('x', '{}', 'k1')"
                )
            )


def test_status_check_constraint_rejects_unknown(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    with sqlite_engine.connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO outbox_messages (kind, payload, status)"
                    " VALUES ('x', '{}', 'bogus')"
                )
            )


def test_round_trip_downgrade_then_upgrade(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    assert "outbox_messages" not in inspect(sqlite_engine).get_table_names()
    _run(sqlite_engine, "upgrade")
    assert "outbox_messages" in inspect(sqlite_engine).get_table_names()
