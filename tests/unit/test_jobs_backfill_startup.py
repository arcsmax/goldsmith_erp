"""Startup backfill of the jobs spine (``JOBS_BACKFILL_ON_STARTUP``).

``JobService.backfill_on_startup`` opens its own session, gives every order
and repair without a job one, commits and logs the counts. It is idempotent
and a no-op when the flag is off.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import select

from goldsmith_erp.core.config import Settings, settings
from goldsmith_erp.db.models import Order, OrderStatusEnum, RepairItemType, RepairJob
from goldsmith_erp.services.job_service import JobService
from tests.conftest import TestSessionLocal

pytestmark = pytest.mark.asyncio


async def _rows_without_jobs(db, customer_id: int) -> None:
    db.add(
        Order(title="Siegelring", customer_id=customer_id, status=OrderStatusEnum.DRAFT)
    )
    db.add(
        RepairJob(
            repair_number="REP-2026-9901",
            bag_number="TU-2026-9901",
            customer_id=customer_id,
            item_description="Kette löten",
            item_type=RepairItemType.CHAIN,
        )
    )
    await db.commit()


def test_flag_defaults_to_true():
    assert Settings.model_fields["JOBS_BACKFILL_ON_STARTUP"].default is True


async def test_backfill_on_startup_creates_jobs_commits_and_logs(
    db_session, sample_customer, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "JOBS_BACKFILL_ON_STARTUP", True)
    await _rows_without_jobs(db_session, sample_customer.id)

    with caplog.at_level(logging.INFO, logger="goldsmith_erp.services.job_service"):
        counts = await JobService.backfill_on_startup(TestSessionLocal)

    assert counts == {"orders": 1, "repairs": 1}
    assert any(r.message == "jobs_backfill_on_startup" for r in caplog.records)
    async with TestSessionLocal() as fresh:
        assert await JobService.count_missing(fresh) == {"orders": 0, "repairs": 0}
        repair = (await fresh.execute(select(RepairJob))).scalar_one()
        assert repair.job_id is not None

    # Idempotent: the second run finds nothing to do.
    assert await JobService.backfill_on_startup(TestSessionLocal) == {
        "orders": 0,
        "repairs": 0,
    }


async def test_backfill_on_startup_is_skipped_when_flag_is_off(
    db_session, sample_customer, monkeypatch
):
    monkeypatch.setattr(settings, "JOBS_BACKFILL_ON_STARTUP", False)
    await _rows_without_jobs(db_session, sample_customer.id)

    assert await JobService.backfill_on_startup(TestSessionLocal) is None
    async with TestSessionLocal() as fresh:
        assert await JobService.count_missing(fresh) == {"orders": 1, "repairs": 1}


async def test_startup_hook_is_registered():
    from goldsmith_erp import main

    handlers = main.app.router.on_startup
    assert main.backfill_jobs_on_startup in handlers
