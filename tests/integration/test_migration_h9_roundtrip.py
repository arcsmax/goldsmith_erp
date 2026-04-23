"""H9 migration round-trip integration test (F2a).

Guards the invariant that ``alembic upgrade head → downgrade base →
upgrade head`` completes cleanly against a fresh PostgreSQL 15 database.
Regression test for the F2a escalation (2026-04-23): the H9 migration
``20260420_h9_explicit_ondelete_restrict.py`` shipped with a
``downgrade()`` that collided with the pre-existing
``fk_customers_deleted_by_users`` constraint, blocking any alembic
``downgrade`` step and therefore the CI migration smoke-test (F2).

PostgreSQL only
---------------
The H9 migration is a no-op on SQLite (it explicitly returns early when
``bind.dialect.name == "sqlite"``), so exercising the round-trip on
SQLite would not validate the fix. This test is skipped unless a real
Postgres URL is provided via one of:

  * ``MIGRATION_TEST_DATABASE_URL`` — explicit, preferred in CI
  * ``DATABASE_URL`` — fall-back if it points to Postgres

The URL must be a maintainance-capable connection (we create and drop
a scratch database to isolate this test from any running app DB).

Why a scratch DB, not the session DB
------------------------------------
Running ``alembic upgrade → downgrade base → upgrade`` against a DB
that other tests share would destroy their schema. We therefore
connect to the Postgres instance with AUTOCOMMIT, create
``goldsmith_h9_roundtrip_<pid>_<uuid8>``, point alembic at it for the
round-trip, then drop it (even on failure).
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _candidate_db_url() -> str | None:
    """Return the best available PG URL for round-trip testing, or None.

    Order of preference:
      1. MIGRATION_TEST_DATABASE_URL (explicit opt-in for this test)
      2. DATABASE_URL, iff it looks like Postgres
    """
    url = os.environ.get("MIGRATION_TEST_DATABASE_URL")
    if url:
        return url
    url = os.environ.get("DATABASE_URL")
    if url and "postgres" in url.lower():
        return url
    return None


_PG_URL = _candidate_db_url()

pytestmark = pytest.mark.skipif(
    not _PG_URL,
    reason=(
        "H9 round-trip exercises PostgreSQL-only DDL. "
        "Set MIGRATION_TEST_DATABASE_URL to a Postgres URL to run it."
    ),
)


def _split_url(url: str) -> tuple[str, str]:
    """Return (server_url_without_db_name, original_db_name).

    ``server_url_without_db_name`` is a URL whose path is ``/postgres``
    — safe to open with AUTOCOMMIT so we can create/drop the scratch DB.
    """
    parsed = urlparse(url)
    original_db = parsed.path.lstrip("/") or "postgres"
    server = parsed._replace(path="/postgres")
    return urlunparse(server), original_db


def _make_alembic_config(db_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    # env.py also honours MIGRATION_DATABASE_URL; set it so subprocess
    # invocations from the same process pick up the override too.
    os.environ["MIGRATION_DATABASE_URL"] = db_url
    return cfg


@pytest.fixture
def scratch_pg_url():
    """Create a throwaway PG database and yield its URL; drop on teardown.

    The scratch DB name encodes pid + random suffix so concurrent test
    runs do not collide.
    """
    assert _PG_URL is not None  # skipif guards this
    server_url, _ = _split_url(_PG_URL)
    scratch_name = f"goldsmith_h9_roundtrip_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    # AUTOCOMMIT so CREATE DATABASE / DROP DATABASE are not wrapped in a txn.
    engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{scratch_name}"'))
        parsed = urlparse(_PG_URL)
        scratch_url = urlunparse(parsed._replace(path=f"/{scratch_name}"))
        try:
            yield scratch_url
        finally:
            # Terminate any lingering connections and drop.
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity "
                        "WHERE datname = :dbname AND pid <> pg_backend_pid()"
                    ),
                    {"dbname": scratch_name},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}"'))
    finally:
        engine.dispose()


def test_h9_upgrade_downgrade_upgrade_round_trip(scratch_pg_url: str) -> None:
    """Alembic must handle a full upgrade→downgrade→upgrade cycle cleanly.

    This is the F2a regression test: before the drop-if-exists guard was
    added to ``20260420_h9_explicit_ondelete_restrict.py::downgrade()``,
    the first downgrade step raised
    ``psycopg2.errors.DuplicateObject: constraint
    "fk_customers_deleted_by_users" for relation "customers" already
    exists`` because migration ``20260406_review`` creates that FK by
    that exact name and H9's upgrade leaves it in place.
    """
    cfg = _make_alembic_config(scratch_pg_url)

    # Step 1 — forward migration from empty DB to HEAD.
    command.upgrade(cfg, "head")

    # Step 2 — full reverse back to empty. This is the step that fails
    # on unfixed HEAD.
    command.downgrade(cfg, "base")

    # Step 3 — forward again, to prove the downgrade left the DB in a
    # state compatible with re-application (not merely "didn't error").
    command.upgrade(cfg, "head")
