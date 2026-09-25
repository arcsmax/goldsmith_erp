"""Migration + type tests for BE-15 (timezone-aware datetimes).

* ``20260925_be15_tz`` runs up/down/up on a scratch SQLite DB via
  MigrationContext (same pattern as test_migration_w207_order_events.py);
  its inventory must match every aware ``UtcDateTime`` column of the model.
* ``UtcDateTime`` round-trips aware values through SQLite (stored as naive
  UTC strings, read back aware UTC) and normalises naive input as UTC.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import DateTime, create_engine, inspect, select, text

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from goldsmith_erp.db.models import Base, CalendarEvent, CalendarEventType, Order
from goldsmith_erp.db.types import UtcDateTime

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "alembic" / "versions" / "20260925_be15_timestamptz.py"
_REVISION = "20260925_be15_tz"
_PRE_EXISTING_AWARE = {
    ("orders", "punzierung_verified_at"),
    ("scan_logs", "client_tap_at"),
    ("scan_logs", "server_resolved_at"),
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("be15_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    module = _load_migration()
    engine = create_engine(f"sqlite:///{tmp_path / 'be15.db'}", future=True)
    with engine.connect() as conn:
        for table, columns in module.COLUMNS.items():
            cols = ", ".join(f"{name} TIMESTAMP" for name in columns)
            conn.execute(
                text(
                    f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, note VARCHAR, {cols})"
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


def _columns(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_revision_sits_on_top_of_be14_in_the_single_chain():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_be14_numeric"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert script.get_heads() == [_REVISION]


def test_inventory_matches_every_aware_model_column():
    module = _load_migration()
    in_migration = {(t, c) for t, cols in module.COLUMNS.items() for c in cols}
    aware_in_model = set()
    naive_in_model = set()
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, UtcDateTime):
                target = aware_in_model if column.type._store_aware else naive_in_model
                target.add((table.name, column.name))
            else:
                assert not isinstance(
                    column.type, DateTime
                ), f"{table.name}.{column.name} is a plain DateTime; use UtcDateTime"
    assert in_migration == aware_in_model - _PRE_EXISTING_AWARE
    # The partition key is the only column that stays naive in the DB.
    assert naive_in_model == {("scan_logs", "scanned_at")}


def test_upgrade_downgrade_upgrade_keeps_values(sqlite_engine):
    with sqlite_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO orders (id, note, created_at) VALUES "
                "(1, 'keep', '2026-01-31 23:30:00.000000')"
            )
        )
        conn.commit()

    # SQLite has no time zone type and its reflection cannot tell the two
    # apart; the type change itself is verified on PostgreSQL (see the fix
    # report). Here: every direction runs and nothing is lost.
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")
    _run(sqlite_engine, "upgrade")
    assert {"note", "created_at"} <= _columns(sqlite_engine, "orders")

    with sqlite_engine.connect() as conn:
        row = conn.execute(text("SELECT note, created_at FROM orders")).one()
    assert row.note == "keep"
    assert str(row.created_at).startswith("2026-01-31 23:30:00")


def test_upgrade_fails_loudly_on_schema_drift(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'drift.db'}", future=True)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE activities (id INTEGER PRIMARY KEY)"))
        conn.commit()
    with pytest.raises(RuntimeError, match="missing"):
        _run(engine, "upgrade")
    engine.dispose()


@pytest.mark.asyncio
class TestUtcDateTimeOnSqlite:
    async def test_aware_value_round_trips_as_aware_utc(self, db_session, sample_user):
        berlin = datetime(2026, 3, 29, 3, 30, tzinfo=ZoneInfo("Europe/Berlin"))
        event = CalendarEvent(
            title="Anprobe",
            event_type=CalendarEventType.APPOINTMENT,
            start_datetime=berlin,
            end_datetime=berlin + timedelta(hours=1),
            user_id=sample_user.id,
        )
        db_session.add(event)
        await db_session.commit()
        event_id = event.id
        db_session.expunge_all()

        # Stored as a naive UTC string in SQLite ...
        raw = (
            await db_session.execute(
                text("SELECT start_datetime FROM calendar_events WHERE id = :i"),
                {"i": event_id},
            )
        ).scalar_one()
        assert str(raw).startswith("2026-03-29 01:30:00")

        # ... and read back aware UTC, the same instant.
        loaded = (
            await db_session.execute(
                select(CalendarEvent).where(CalendarEvent.id == event_id)
            )
        ).scalar_one()
        assert loaded.start_datetime.tzinfo is not None
        assert loaded.start_datetime.utcoffset() == timedelta(0)
        assert loaded.start_datetime == berlin

    async def test_naive_assignment_is_read_as_utc(self):
        order = Order(title="x", deadline=datetime(2026, 5, 1, 12, 0))
        assert order.deadline == datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    async def test_defaults_are_aware(self, db_session):
        order = Order(title="aware default")
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        assert order.created_at.tzinfo is not None
