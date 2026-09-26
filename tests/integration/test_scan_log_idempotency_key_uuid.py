"""PostgreSQL regression test — ``scan_logs.idempotency_key`` UUID drift.

Production regression (2026-09 audit backlog: "pre-existing PG drift
(scan_logs partitions/types/index)"):

  * The Alembic-migrated PostgreSQL schema
    (``alembic/versions/20260418_add_qr_barcode_core_tables.py``) creates
    ``scan_logs.id`` and ``scan_logs.idempotency_key`` as native ``UUID``
    columns.
  * The ``ScanLog`` ORM model (``db/models/system.py``) declared both as
    ``String(36)``.
  * PostgreSQL's ``bind_typing = BindTyping.RENDER_CASTS`` (used by the
    asyncpg dialect) renders an explicit ``::VARCHAR`` cast for a
    ``String``-typed bind parameter. Comparing that against a real
    ``uuid`` column has no operator, so every scan carrying an
    idempotency key (100% of client scans — the frontend always sends
    ``crypto.randomUUID()``) failed on ``POST /api/v1/scan/log`` with::

        asyncpg.exceptions.UndefinedFunctionError: operator does not
        exist: uuid = character varying

    raised from ``scanner_service._find_by_idempotency_key``, which runs
    its pre-insert SELECT before any row is written — so the very FIRST
    scan with a key already failed, not just the retried one.

  * SQLite (the unit suite's DB) has no native UUID type, so the
    migration's SQLite fallback path creates both columns as
    ``VARCHAR(36)`` — matching the ORM's ``String(36)`` exactly. That is
    why the unit suite never caught this: the drift is PostgreSQL-only.

Requires a real, Alembic-migrated PostgreSQL database
(``TEST_DATABASE_URL`` pointing at Postgres) — see
``tests/integration/test_pg_concurrency.py`` for the identical gating
pattern. ``tests/integration/conftest.py``'s session-scoped
``create_tables`` fixture calls ``Base.metadata.create_all()``, which is
a no-op against an already-migrated database (every table already
exists, and ``create_all`` checks that first) — so this test exercises
the *actual* production schema (native UUID columns), not a
``create_all()`` approximation built from the ORM's own (previously
wrong) column types.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import ScanLog as ScanLogModel
from goldsmith_erp.db.models import User
from goldsmith_erp.models.scanner import ScanLogCreate
from goldsmith_erp.services.scanner_service import ScannerService

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _TEST_DATABASE_URL.startswith("postgresql"),
        reason=(
            "Reproduces a PostgreSQL-only ORM/schema type mismatch "
            "(scan_logs.id / idempotency_key are UUID in Postgres, "
            "VARCHAR(36) in SQLite). Set TEST_DATABASE_URL to a "
            "postgresql+asyncpg URL pointing at an Alembic-migrated "
            "(alembic upgrade head) database."
        ),
    ),
]


class TestScanLogIdempotencyKeyUuidPostgres:
    async def test_log_scan_twice_same_key_dedupes_on_postgres(
        self, db_session: AsyncSession, admin_user: User
    ) -> None:
        """Same idempotency_key twice -> exactly one row; the second call
        returns the first row instead of inserting (or raising).

        Before the fix, the FIRST call already raised
        ``asyncpg.exceptions.UndefinedFunctionError`` out of
        ``_find_by_idempotency_key``'s pre-insert SELECT.
        """
        key = uuid.uuid4()
        event = ScanLogCreate(raw_payload="ORDER:1", idempotency_key=str(key))

        first = await ScannerService.log_scan(db_session, admin_user.id, event)
        second = await ScannerService.log_scan(db_session, admin_user.id, event)

        assert first.id == second.id, (
            "Idempotency-key dedupe must return the original row, not "
            "insert (or fail on) a second call."
        )
        assert str(first.idempotency_key) == str(key)

        count_result = await db_session.execute(
            select(func.count())
            .select_from(ScanLogModel)
            .where(ScanLogModel.idempotency_key == str(key))
        )
        assert (
            count_result.scalar_one() == 1
        ), "Exactly one scan_logs row should exist for this idempotency key."

    async def test_scan_log_id_round_trips_as_canonical_uuid_string(
        self, db_session: AsyncSession, admin_user: User
    ) -> None:
        """``ScanLog.id`` is also a native UUID column on Postgres — a
        client-generated ``str(uuid.uuid4())`` primary key must insert
        and read back as the same canonical (dashed) string."""
        event = ScanLogCreate(raw_payload="ORDER:2")
        row = await ScannerService.log_scan(db_session, admin_user.id, event)

        # Round-trips through uuid.UUID cleanly (raises ValueError otherwise).
        parsed = uuid.UUID(row.id)
        assert str(parsed) == row.id

        reloaded = await db_session.execute(
            select(ScanLogModel).where(ScanLogModel.id == row.id)
        )
        assert reloaded.scalar_one().id == row.id
