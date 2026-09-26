"""Migration tests for 20260925_w207_order_events (W2-07, ARCH-01, DOM-46).

Same pattern as test_migration_w117_one_running_timer.py: load the migration
by file path and run ``upgrade()`` / ``downgrade()`` on a scratch SQLite DB
via MigrationContext/Operations. The chain position is checked through the
real alembic script directory (alembic.ini).

Covers: new columns + ``order_events`` table, the legacy ``new`` mapping
(``draft`` without a price, ``confirmed`` with one), one backfill event per
order (reason "backfill"), idempotence, and down/up round trip restoring
``new``.
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
_PATH = _ROOT / "alembic" / "versions" / "20260925_w207_order_events.py"
_REVISION = "20260925_w207_order_events"


def _load_migration():
    spec = importlib.util.spec_from_file_location("w207_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'w207.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR)"))
        conn.execute(
            text(
                "CREATE TABLE orders (id INTEGER PRIMARY KEY, title VARCHAR,"
                " price FLOAT, status VARCHAR(19) NOT NULL,"
                " created_at TIMESTAMP, updated_at TIMESTAMP)"
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


def _insert_order(engine, order_id: int, status: str, price) -> None:
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO orders (id, title, price, status, created_at,"
                " updated_at) VALUES (:id, 'x', :price, :status,"
                " '2026-01-01 10:00:00', '2026-02-01 12:00:00')"
            ),
            {"id": order_id, "price": price, "status": status},
        )
        conn.commit()


def _statuses(engine) -> dict[int, str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, status FROM orders")).all()
    return {r[0]: r[1] for r in rows}


def _events(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT order_id, from_status, to_status, reason, created_at,"
                " meta FROM order_events ORDER BY order_id, id"
            )
        ).mappings()
        out = []
        for row in rows:
            item = dict(row)
            if isinstance(item["meta"], str):
                item["meta"] = json.loads(item["meta"])
            out.append(item)
    return out


def test_revision_sits_on_top_of_c22_in_the_single_chain():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_c22_cu_dedupe"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    # W2-10 / W2-04 build on top of this revision; the chain stays linear.
    assert len(script.get_heads()) == 1
    chain = {rev.revision for rev in script.walk_revisions()}
    assert _REVISION in chain


def test_upgrade_adds_columns_and_events_table(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    insp = inspect(sqlite_engine)
    cols = {c["name"] for c in insp.get_columns("orders")}
    assert {"hold_reason", "resume_date", "cancel_reason"} <= cols
    event_cols = {c["name"] for c in insp.get_columns("order_events")}
    assert {
        "id",
        "order_id",
        "from_status",
        "to_status",
        "user_id",
        "reason",
        "created_at",
        "meta",
    } <= event_cols
    fks = insp.get_foreign_keys("order_events")
    assert {fk["referred_table"] for fk in fks} == {"orders", "users"}


def test_upgrade_maps_legacy_new_by_price(sqlite_engine):
    _insert_order(sqlite_engine, 1, "new", None)
    _insert_order(sqlite_engine, 2, "new", 0)
    _insert_order(sqlite_engine, 3, "new", 450.0)
    _insert_order(sqlite_engine, 4, "in_progress", 800.0)

    _run(sqlite_engine, "upgrade")

    assert _statuses(sqlite_engine) == {
        1: "draft",
        2: "draft",
        3: "confirmed",
        4: "in_progress",
    }


def test_upgrade_backfills_one_event_per_order(sqlite_engine):
    _insert_order(sqlite_engine, 1, "new", None)
    _insert_order(sqlite_engine, 2, "in_progress", 800.0)

    _run(sqlite_engine, "upgrade")

    events = _events(sqlite_engine)
    assert [(e["order_id"], e["from_status"], e["to_status"]) for e in events] == [
        (1, None, "draft"),
        (2, None, "in_progress"),
    ]
    assert all(e["reason"] == "backfill" for e in events)
    assert str(events[0]["created_at"]).startswith("2026-02-01 12:00:00")
    assert events[0]["meta"]["backfill"] is True
    assert events[0]["meta"]["legacy_status"] == "new"
    assert "legacy_status" not in events[1]["meta"]


def test_upgrade_is_idempotent(sqlite_engine):
    _insert_order(sqlite_engine, 1, "in_progress", 10.0)
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")
    assert len(_events(sqlite_engine)) == 1


def test_downgrade_restores_new_and_drops_objects_then_reupgrade(sqlite_engine):
    _insert_order(sqlite_engine, 1, "new", None)
    _insert_order(sqlite_engine, 2, "new", 99.0)
    _insert_order(sqlite_engine, 3, "quality_check", 99.0)

    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")

    insp = inspect(sqlite_engine)
    assert "order_events" not in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("orders")}
    assert not {"hold_reason", "resume_date", "cancel_reason"} & cols
    assert _statuses(sqlite_engine) == {1: "new", 2: "new", 3: "quality_check"}

    _run(sqlite_engine, "downgrade")  # idempotent no-op
    _run(sqlite_engine, "upgrade")
    assert _statuses(sqlite_engine) == {1: "draft", 2: "confirmed", 3: "quality_check"}
    assert len(_events(sqlite_engine)) == 3


def test_downgrade_maps_on_hold_and_cancelled_back_for_old_code(sqlite_engine):
    _insert_order(sqlite_engine, 1, "in_progress", 10.0)
    _run(sqlite_engine, "upgrade")
    with sqlite_engine.connect() as conn:
        conn.execute(text("UPDATE orders SET status = 'on_hold' WHERE id = 1"))
        conn.execute(
            text(
                "INSERT INTO orders (id, title, price, status) VALUES"
                " (2, 'y', 5.0, 'cancelled')"
            )
        )
        conn.commit()

    _run(sqlite_engine, "downgrade")
    # Pre-W2-07 code does not know these values; they fall back to the
    # nearest status it can render (documented in the migration).
    assert _statuses(sqlite_engine) == {1: "in_progress", 2: "draft"}
