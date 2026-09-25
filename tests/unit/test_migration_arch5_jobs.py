"""Migration tests for 20260925_arch5_jobs (ARCH phase 5, jobs spine).

Runs the migration in isolation on a scratch SQLite DB with minimal copies
of the tables it touches, then checks the backfill: one job per order and
per repair with the mapped status and per-year numbers, job_id attached on
invoices / customer updates / media / events, a synthetic event per repair,
the AU / REP counters seeded, idempotent re-run, and up/down/up.
"""

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
_PATH = _ROOT / "alembic" / "versions" / "20260925_arch5_jobs_spine.py"
_REVISION = "20260925_arch5_jobs"

_LEGACY_DDL = (
    "CREATE TABLE users (id INTEGER PRIMARY KEY)",
    "CREATE TABLE customers (id INTEGER PRIMARY KEY)",
    "CREATE TABLE orders (id INTEGER PRIMARY KEY, title VARCHAR, status VARCHAR(30),"
    " customer_id INTEGER REFERENCES customers(id), deadline DATETIME,"
    " resume_date DATE, is_deleted BOOLEAN DEFAULT 0, price NUMERIC,"
    " created_at DATETIME, updated_at DATETIME)",
    "CREATE TABLE repair_jobs (id INTEGER PRIMARY KEY, repair_number VARCHAR(20),"
    " customer_id INTEGER, item_description TEXT, status VARCHAR(30),"
    " estimated_completion_date DATETIME, is_deleted BOOLEAN DEFAULT 0,"
    " created_at DATETIME, updated_at DATETIME)",
    "CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_number VARCHAR(20),"
    " order_id INTEGER NOT NULL REFERENCES orders(id), status VARCHAR(20),"
    " cancels_invoice_id INTEGER)",
    "CREATE UNIQUE INDEX uq_invoices_one_active_per_order ON invoices (order_id)"
    " WHERE status <> 'cancelled' AND cancels_invoice_id IS NULL",
    "CREATE TABLE customer_updates (id INTEGER PRIMARY KEY, order_id INTEGER,"
    " repair_job_id INTEGER, subject VARCHAR(300))",
    "CREATE TABLE media_assets (id VARCHAR(36) PRIMARY KEY, owner_type VARCHAR(20),"
    " owner_id INTEGER)",
    "CREATE TABLE order_events (id INTEGER PRIMARY KEY,"
    " order_id INTEGER NOT NULL REFERENCES orders(id), from_status VARCHAR(30),"
    " to_status VARCHAR(30) NOT NULL, user_id INTEGER, reason VARCHAR(500),"
    " created_at DATETIME NOT NULL, meta JSON)",
    "CREATE TABLE number_sequences (kind VARCHAR(10), year INTEGER,"
    " last_value INTEGER NOT NULL, PRIMARY KEY (kind, year))",
)

_SEED = (
    "INSERT INTO customers (id) VALUES (1), (2)",
    "INSERT INTO orders (id, title, status, customer_id, deadline, created_at,"
    " updated_at) VALUES"
    " (1, 'Ehering', 'completed', 1, '2026-10-01 00:00:00',"
    " '2025-12-31 23:30:00', '2026-01-02 10:00:00'),"
    " (2, 'Anhänger', 'on_hold', 2, NULL, '2026-03-01 10:00:00',"
    " '2026-03-05 10:00:00'),"
    " (3, 'Kette', 'new', NULL, NULL, '2026-02-01 10:00:00', NULL)",
    "INSERT INTO repair_jobs (id, repair_number, customer_id, item_description,"
    " status, estimated_completion_date, created_at, updated_at) VALUES"
    " (1, 'REP-2026-0007', 1, 'Ring   weiten', 'quoted', '2026-10-02 00:00:00',"
    " '2026-04-01 10:00:00', '2026-04-02 10:00:00'),"
    " (2, 'REP-2026-0009', NULL, 'Kette löten', 'picked_up', NULL,"
    " '2026-05-01 10:00:00', NULL)",
    "INSERT INTO invoices (id, invoice_number, order_id, status) VALUES"
    " (1, 'RE-2026-0001', 1, 'draft')",
    "INSERT INTO customer_updates (id, order_id, repair_job_id, subject) VALUES"
    " (1, 1, NULL, 'a'), (2, NULL, 1, 'b')",
    "INSERT INTO media_assets (id, owner_type, owner_id) VALUES"
    " ('m1', 'order', 2), ('m2', 'repair', 2), ('m3', 'consultation', 1)",
    "INSERT INTO order_events (order_id, to_status, created_at) VALUES"
    " (1, 'completed', '2026-01-02 10:00:00')",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("arch5_jobs", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'arch5.db'}", future=True)
    with eng.begin() as conn:
        for ddl in _LEGACY_DDL:
            conn.execute(text(ddl))
        for sql in _SEED:
            conn.execute(text(sql))
    yield eng
    eng.dispose()


def _run(engine, fn_name: str) -> None:
    module = _load_migration()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn_name)()
        conn.commit()


def _rows(engine, sql: str) -> list:
    with engine.connect() as conn:
        return list(conn.execute(text(sql)).mappings())


def test_revision_is_the_single_head_on_top_of_arch4():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_arch4_media"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    assert script.get_heads() == [_REVISION]


def test_status_maps_cover_every_enum_value():
    from goldsmith_erp.db.models import JobStatus, OrderStatusEnum, RepairJobStatus
    from goldsmith_erp.services import job_service

    module = _load_migration()
    assert set(module.ORDER_STATUS_TO_JOB) == {s.value for s in OrderStatusEnum}
    assert set(module.REPAIR_STATUS_TO_JOB) == {s.value for s in RepairJobStatus}
    assert set(module.JOB_STATUSES) == {s.value for s in JobStatus}
    # The frozen copies agree with the service mapping.
    for status, job in job_service.ORDER_STATUS_TO_JOB.items():
        assert module.ORDER_STATUS_TO_JOB[status.value] == job.value
    for status, job in job_service.REPAIR_STATUS_TO_JOB.items():
        assert module.REPAIR_STATUS_TO_JOB[status.value] == job.value


def test_upgrade_creates_one_job_per_order_and_repair(engine):
    _run(engine, "upgrade")

    jobs = _rows(engine, "SELECT * FROM jobs ORDER BY id")
    assert len(jobs) == 5
    by_number = {j["number"]: j for j in jobs}
    # Berlin year: 2025-12-31 23:30 UTC is already 2026 in Berlin.
    assert set(by_number) == {
        "AU-2026-0001",
        "AU-2026-0002",
        "AU-2026-0003",
        "REP-2026-0007",
        "REP-2026-0009",
    }
    first = by_number["AU-2026-0001"]
    assert first["kind"] == "order"
    assert first["status"] == "ready"
    assert first["kind_status"] == "completed"
    assert first["title"] == "Ehering"
    assert first["customer_id"] == 1
    # Numbered in created_at order: order 3 (Feb) before order 2 (Mar).
    assert by_number["AU-2026-0002"]["kind_status"] == "new"
    assert by_number["AU-2026-0002"]["status"] == "draft"
    held = by_number["AU-2026-0003"]
    assert held["status"] == "on_hold"
    assert held["on_hold_since"] is not None
    repair = by_number["REP-2026-0007"]
    assert repair["kind"] == "repair"
    assert repair["status"] == "awaiting_approval"
    assert repair["title"] == "Ring weiten"
    assert by_number["REP-2026-0009"]["status"] == "delivered"

    orders = _rows(engine, "SELECT id, job_id FROM orders ORDER BY id")
    assert all(o["job_id"] is not None for o in orders)
    repairs = _rows(engine, "SELECT id, job_id FROM repair_jobs ORDER BY id")
    assert all(r["job_id"] is not None for r in repairs)


def test_upgrade_attaches_job_ids_and_backfills_repair_events(engine):
    _run(engine, "upgrade")
    job_of_order = {
        r["id"]: r["job_id"] for r in _rows(engine, "SELECT id, job_id FROM orders")
    }
    job_of_repair = {
        r["id"]: r["job_id"]
        for r in _rows(engine, "SELECT id, job_id FROM repair_jobs")
    }

    invoice = _rows(engine, "SELECT job_id FROM invoices")[0]
    assert invoice["job_id"] == job_of_order[1]
    updates = {
        r["id"]: r["job_id"]
        for r in _rows(engine, "SELECT id, job_id FROM customer_updates")
    }
    assert updates == {1: job_of_order[1], 2: job_of_repair[1]}
    media = {
        r["id"]: r["job_id"]
        for r in _rows(engine, "SELECT id, job_id FROM media_assets")
    }
    assert media == {"m1": job_of_order[2], "m2": job_of_repair[2], "m3": None}

    events = _rows(engine, "SELECT * FROM order_events ORDER BY id")
    assert events[0]["job_id"] == job_of_order[1]
    repair_events = [e for e in events if e["repair_job_id"] is not None]
    assert len(repair_events) == 2
    assert {e["to_status"] for e in repair_events} == {"quoted", "picked_up"}
    assert all(
        e["order_id"] is None and e["reason"] == "backfill" for e in repair_events
    )


def test_upgrade_seeds_counters_and_is_idempotent(engine):
    _run(engine, "upgrade")
    _run(engine, "upgrade")

    assert len(_rows(engine, "SELECT id FROM jobs")) == 5
    assert len(_rows(engine, "SELECT id FROM order_events")) == 3
    counters = {
        (r["kind"], r["year"]): r["last_value"]
        for r in _rows(engine, "SELECT * FROM number_sequences")
    }
    assert counters == {("AU", 2026): 3, ("REP", 2026): 9}


def test_upgrade_makes_order_id_nullable_and_adds_job_index(engine):
    _run(engine, "upgrade")
    insp = inspect(engine)
    invoice_cols = {c["name"]: c for c in insp.get_columns("invoices")}
    assert invoice_cols["order_id"]["nullable"] is True
    event_cols = {c["name"]: c for c in insp.get_columns("order_events")}
    assert event_cols["order_id"]["nullable"] is True
    assert "repair_job_id" in event_cols
    index_names = {i["name"] for i in insp.get_indexes("invoices")}
    assert "uq_invoices_one_active_per_job" in index_names
    assert "uq_invoices_one_active_per_order" in index_names

    repair_job = _rows(engine, "SELECT job_id FROM repair_jobs WHERE id = 1")[0]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO invoices (invoice_number, order_id, job_id, status)"
                " VALUES ('RE-2026-0002', NULL, :job, 'draft')"
            ),
            {"job": repair_job["job_id"]},
        )
    # A second live invoice for the same job is refused.
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO invoices (invoice_number, order_id, job_id, status)"
                    " VALUES ('RE-2026-0003', NULL, :job, 'draft')"
                ),
                {"job": repair_job["job_id"]},
            )
    # The per-order partial index survived the table rebuild: a Storno for
    # order 1 is still allowed next to its live invoice.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO invoices (invoice_number, order_id, status,"
                " cancels_invoice_id) VALUES ('RE-2026-0004', 1, 'draft', 1)"
            )
        )


def test_downgrade_refuses_while_a_repair_invoice_exists(engine):
    _run(engine, "upgrade")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO invoices (invoice_number, order_id, status)"
                " VALUES ('RE-2026-0005', NULL, 'draft')"
            )
        )
    with pytest.raises(RuntimeError, match="repair invoice"):
        _run(engine, "downgrade")


def test_up_down_up_round_trip(engine):
    _run(engine, "upgrade")
    _run(engine, "downgrade")

    insp = inspect(engine)
    assert "jobs" not in insp.get_table_names()
    for table in ("orders", "repair_jobs", "invoices", "customer_updates"):
        assert "job_id" not in {c["name"] for c in insp.get_columns(table)}
    event_cols = {c["name"]: c for c in insp.get_columns("order_events")}
    assert "repair_job_id" not in event_cols
    assert event_cols["order_id"]["nullable"] is False
    invoice_cols = {c["name"]: c for c in insp.get_columns("invoices")}
    assert invoice_cols["order_id"]["nullable"] is False
    assert len(_rows(engine, "SELECT id FROM order_events")) == 1
    assert _rows(engine, "SELECT * FROM number_sequences") == []

    _run(engine, "upgrade")
    assert len(_rows(engine, "SELECT id FROM jobs")) == 5
