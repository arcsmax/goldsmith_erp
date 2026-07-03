# tests/unit/test_migration_v12a_sent_index.py
"""
Migration tests for the ``uq_cost_change_one_sent_per_order`` partial
unique index added to 20260703_v12a_customer_updates (security re-review
fix: at most one SENT CostChangeRequest per order — the DB-level
invariant behind CostChangeService.send()'s cross-row race handling).

Follows the established migration-test pattern
(test_migration_slice_2.py): load the migration module by file path, run
``upgrade()`` against a scratch file-backed SQLite DB via
MigrationContext/Operations, then assert the index's existence, partial
WHERE clause, enforcement, and the guarded-creation idempotency.

The legacy-DB scenario exercised here: ``cost_change_requests`` already
exists (created by an earlier run of this same migration, before the
index was added to it in-place — sanctioned edit, migration unreleased)
but has NO index. ``create_table_if_not_exists`` no-ops on it;
``create_index_if_not_exists`` must create the index.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic.migration import MigrationContext
from alembic.operations import Operations

_ALEMBIC_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_V12A_PATH = _ALEMBIC_VERSIONS / "20260703_v12a_customer_updates.py"

_INDEX_NAME = "uq_cost_change_one_sent_per_order"


def _load_migration():
    spec = importlib.util.spec_from_file_location("v12a_migration", str(_V12A_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    """Fresh file-backed SQLite engine with FK enforcement on."""
    db_file = tmp_path / "v12a.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    yield engine
    engine.dispose()


def _create_legacy_cost_change_table(conn) -> None:
    """Minimal pre-index cost_change_requests shape (raw DDL — no ORM, so
    the ORM's __table_args__ index is deliberately absent)."""
    conn.execute(
        text(
            "CREATE TABLE cost_change_requests ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  order_id INTEGER NOT NULL,"
            "  quote_id INTEGER,"
            "  original_amount FLOAT NOT NULL,"
            "  new_amount FLOAT NOT NULL,"
            "  delta_percent FLOAT NOT NULL,"
            "  reason TEXT NOT NULL,"
            "  line_items JSON,"
            "  status VARCHAR(20) NOT NULL DEFAULT 'draft',"
            "  response_method VARCHAR(20),"
            "  response_evidence TEXT,"
            "  responded_at DATETIME,"
            "  recorded_by INTEGER,"
            "  created_at DATETIME NOT NULL,"
            "  created_by INTEGER NOT NULL,"
            "  updated_at DATETIME NOT NULL"
            ")"
        )
    )


def _run_upgrade(engine) -> None:
    module = _load_migration()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
        conn.commit()


def _insert_row(conn, order_id: int, status: str) -> None:
    conn.execute(
        text(
            "INSERT INTO cost_change_requests "
            "(order_id, original_amount, new_amount, delta_percent, reason,"
            " status, created_at, created_by, updated_at) VALUES "
            "(:order_id, 1000.0, 1100.0, 10.0, 'Testgrund', :status,"
            " CURRENT_TIMESTAMP, 1, CURRENT_TIMESTAMP)"
        ),
        {"order_id": order_id, "status": status},
    )


class TestV12aSentIndexMigration:
    def test_upgrade_creates_partial_unique_index_on_legacy_table(self, sqlite_engine):
        with sqlite_engine.connect() as conn:
            _create_legacy_cost_change_table(conn)
            conn.commit()

        _run_upgrade(sqlite_engine)

        with sqlite_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type='index' " "AND name=:name"
                ),
                {"name": _INDEX_NAME},
            ).one_or_none()
        assert row is not None, f"{_INDEX_NAME} was not created"
        ddl = row[0].lower()
        assert "unique" in ddl
        assert "where" in ddl and "'sent'" in ddl  # partial, status-scoped

    def test_migrated_index_enforces_one_sent_per_order(self, sqlite_engine):
        with sqlite_engine.connect() as conn:
            _create_legacy_cost_change_table(conn)
            conn.commit()
        _run_upgrade(sqlite_engine)

        with sqlite_engine.connect() as conn:
            _insert_row(conn, order_id=1, status="sent")
            # Second SENT for the same order — index violation.
            with pytest.raises(IntegrityError):
                _insert_row(conn, order_id=1, status="sent")
            conn.rollback()

        with sqlite_engine.connect() as conn:
            # Non-SENT rows and SENT rows on other orders stay unaffected.
            _insert_row(conn, order_id=1, status="sent")
            _insert_row(conn, order_id=1, status="draft")
            _insert_row(conn, order_id=1, status="superseded")
            _insert_row(conn, order_id=2, status="sent")
            conn.commit()

    def test_upgrade_is_idempotent(self, sqlite_engine):
        """create_index_if_not_exists guard: a second upgrade() run (e.g.
        a legacy DB that already caught up) must be a clean no-op."""
        with sqlite_engine.connect() as conn:
            _create_legacy_cost_change_table(conn)
            conn.commit()

        _run_upgrade(sqlite_engine)
        _run_upgrade(sqlite_engine)  # must not raise

        with sqlite_engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='index' "
                    "AND name=:name"
                ),
                {"name": _INDEX_NAME},
            ).scalar_one()
        assert count == 1

    def test_orm_create_all_produces_the_same_index(self, sqlite_engine):
        """ORM parity (slice-2 test precedent): Base.metadata.create_all()
        — the unit-test DB path — must materialise the identically-named
        index so both provisioning paths enforce the same invariant."""
        from goldsmith_erp.db.models import Base

        Base.metadata.create_all(sqlite_engine)

        index_names = {
            ix["name"]
            for ix in inspect(sqlite_engine).get_indexes("cost_change_requests")
        }
        assert _INDEX_NAME in index_names
