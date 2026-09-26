"""Migration tests for 20260925_gdpr01_consents (GDPR-01/02/11).

Same pattern as test_migration_v12a_sent_index.py: load the migration by
file path, run ``upgrade()`` / ``downgrade()`` against a scratch SQLite DB
via MigrationContext/Operations, and check ORM parity.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text

from alembic.migration import MigrationContext
from alembic.operations import Operations

_ALEMBIC_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_PATH = _ALEMBIC_VERSIONS / "20260925_gdpr01_consents_hold.py"
_CONSENT_INDEXES = {
    "ix_customer_consents_id",
    "ix_customer_consents_customer_id",
    "ix_customer_consents_purpose",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("gdpr01_migration", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gdpr01.db'}", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    with engine.connect() as conn:
        # Minimal legacy shape: pre-migration customers / users tables.
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE customers (id INTEGER PRIMARY KEY,"
                " first_name TEXT NOT NULL)"
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


def test_revision_chain_points_at_previous_head():
    module = _load_migration()
    assert module.revision == "20260925_gdpr01_consents"
    assert module.down_revision == "20260610_e1_gdpr_audit_nofk"


def test_upgrade_creates_table_column_and_indexes(sqlite_engine):
    _run(sqlite_engine, "upgrade")

    insp = inspect(sqlite_engine)
    cols = {c["name"] for c in insp.get_columns("customer_consents")}
    assert {
        "id",
        "customer_id",
        "purpose",
        "method",
        "wording_version",
        "granted_at",
        "revoked_at",
        "recorded_by_user_id",
        "revoked_by_user_id",
        "note",
        "created_at",
    } <= cols
    assert _CONSENT_INDEXES <= {
        i["name"] for i in insp.get_indexes("customer_consents")
    }
    assert "retention_hold_until" in {c["name"] for c in insp.get_columns("customers")}
    assert "ix_customers_retention_hold_until" in {
        i["name"] for i in insp.get_indexes("customers")
    }


def test_upgrade_is_idempotent(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "upgrade")  # must not raise


def test_downgrade_removes_everything_and_reupgrade_works(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    _run(sqlite_engine, "downgrade")

    insp = inspect(sqlite_engine)
    assert "customer_consents" not in insp.get_table_names()
    assert "retention_hold_until" not in {
        c["name"] for c in insp.get_columns("customers")
    }

    _run(sqlite_engine, "downgrade")  # idempotent no-op
    _run(sqlite_engine, "upgrade")
    assert "customer_consents" in inspect(sqlite_engine).get_table_names()


def test_consent_fk_cascades_with_customer(sqlite_engine):
    _run(sqlite_engine, "upgrade")
    with sqlite_engine.connect() as conn:
        conn.execute(text("INSERT INTO customers (id, first_name) VALUES (1, 'x')"))
        conn.execute(
            text(
                "INSERT INTO customer_consents (customer_id, purpose, method,"
                " granted_at, created_at) VALUES (1, 'health_data', 'written',"
                " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(text("DELETE FROM customers WHERE id = 1"))
        remaining = conn.execute(
            text("SELECT COUNT(*) FROM customer_consents")
        ).scalar_one()
        conn.commit()
    assert remaining == 0


def test_orm_create_all_matches_migration_index_names(tmp_path):
    from goldsmith_erp.db.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'orm.db'}", future=True)
    try:
        Base.metadata.create_all(engine)
        insp = inspect(engine)
        assert _CONSENT_INDEXES <= {
            i["name"] for i in insp.get_indexes("customer_consents")
        }
        assert "ix_customers_retention_hold_until" in {
            i["name"] for i in insp.get_indexes("customers")
        }
    finally:
        engine.dispose()
