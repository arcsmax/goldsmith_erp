"""Integration tests for the per-entity retention sweep (finding 2.3).

Seeds rows that straddle each retention boundary and asserts:
  (a) candidates are identified correctly per table;
  (b) DRY-RUN touches nothing;
  (c) --execute removes exactly the expired rows;
  (d) financial rows still inside their §147 AO / HGB §257 statutory period are
      NEVER touched — not in dry-run, not in execute;
  (e) a per-table failure is flagged (fail-loud) while other tables still run.

Runs on file-backed SQLite by default (see tests/integration/conftest.py). The
sweep decision is driven by explicit anchor-date predicates, not by DB FK
semantics, so it behaves identically on SQLite and PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    MaterialUsage,
    MetalPurchase,
    MetalType,
    Order,
    OrderStatusEnum,
    ScanLog,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.jobs.retention_sweep import (
    RETENTION_RULES,
    RetentionRule,
    sweep_retention,
)

# Fixed "now" so the boundary maths is deterministic.
NOW = datetime(2026, 7, 15)

# financial_10y cutoff at NOW = 2016-01-01 → 2015 expired, 2016 retained.
FIN_EXPIRED = datetime(2015, 6, 1)
FIN_WITHIN = datetime(2016, 6, 1)
# standard_24m cutoff at NOW = 2024-07-15.
SCAN_EXPIRED = datetime(2024, 1, 1)
SCAN_WITHIN = datetime(2026, 1, 1)


# ---------------------------------------------------------------------------
# FK-parent + row helpers
# ---------------------------------------------------------------------------


async def _mk_user(db: AsyncSession) -> User:
    user = User(
        email=f"u_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        first_name="T",
        last_name="U",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _mk_order(db: AsyncSession) -> Order:
    order = Order(title="Ring", description="750er", status=OrderStatusEnum.NEW)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _mk_activity(db: AsyncSession) -> Activity:
    activity = Activity(
        name=f"act_{uuid.uuid4().hex[:6]}",
        category="fabrication",
        created_at=NOW,
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return activity


async def _mk_metal_purchase(db: AsyncSession) -> MetalPurchase:
    purchase = MetalPurchase(
        date_purchased=NOW,
        metal_type=MetalType.GOLD_18K,
        weight_g=100.0,
        remaining_weight_g=100.0,
        price_total=4500.0,
        price_per_gram=45.0,
        supplier="S",
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)
    return purchase


async def _mk_scan_log(db: AsyncSession, user_id: int, scanned_at: datetime) -> str:
    sid = str(uuid.uuid4())
    db.add(
        ScanLog(
            id=sid,
            scanned_at=scanned_at,
            user_id=user_id,
            raw_payload="ORDER:1",
            retention_class="standard_24m",
        )
    )
    await db.commit()
    return sid


async def _mk_time_entry(
    db: AsyncSession,
    order_id: int,
    user_id: int,
    activity_id: int,
    created_at: datetime,
) -> str:
    tid = str(uuid.uuid4())
    db.add(
        TimeEntry(
            id=tid,
            order_id=order_id,
            user_id=user_id,
            activity_id=activity_id,
            start_time=created_at,
            end_time=created_at,
            duration_minutes=60,
            created_at=created_at,
            retention_class="financial_10y",
        )
    )
    await db.commit()
    return tid


async def _mk_material_usage(
    db: AsyncSession, order_id: int, metal_purchase_id: int, used_at: datetime
) -> int:
    row = MaterialUsage(
        order_id=order_id,
        metal_purchase_id=metal_purchase_id,
        weight_used_g=1.0,
        cost_at_time=45.0,
        price_per_gram_at_time=45.0,
        used_at=used_at,
        retention_class="financial_10y",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row.id


async def _count(db: AsyncSession, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.fixture
async def seeded(db_session: AsyncSession):
    """Seed one expired + one within-period row for every swept table."""
    user = await _mk_user(db_session)
    order = await _mk_order(db_session)
    activity = await _mk_activity(db_session)
    purchase = await _mk_metal_purchase(db_session)

    ids = {
        "scan_expired": await _mk_scan_log(db_session, user.id, SCAN_EXPIRED),
        "scan_within": await _mk_scan_log(db_session, user.id, SCAN_WITHIN),
        "te_expired": await _mk_time_entry(
            db_session, order.id, user.id, activity.id, FIN_EXPIRED
        ),
        "te_within": await _mk_time_entry(
            db_session, order.id, user.id, activity.id, FIN_WITHIN
        ),
        "mu_expired": await _mk_material_usage(
            db_session, order.id, purchase.id, FIN_EXPIRED
        ),
        "mu_within": await _mk_material_usage(
            db_session, order.id, purchase.id, FIN_WITHIN
        ),
    }
    return ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_identifies_candidates_and_touches_nothing(
    db_session: AsyncSession, seeded
):
    report = await sweep_retention(db_session, execute=False, now=NOW)

    assert report.executed is False
    assert not report.has_failures
    # Exactly one expired row per table.
    per_table = {r.label: r.candidates for r in report.results}
    assert per_table == {"scan_logs": 1, "time_entries": 1, "material_usage": 1}
    assert report.total_candidates == 3
    assert report.total_deleted == 0

    # Nothing was deleted — both rows survive in every table.
    assert await _count(db_session, ScanLog) == 2
    assert await _count(db_session, TimeEntry) == 2
    assert await _count(db_session, MaterialUsage) == 2


@pytest.mark.asyncio
async def test_execute_deletes_exactly_the_expired_rows(
    db_session: AsyncSession, seeded
):
    report = await sweep_retention(db_session, execute=True, now=NOW)

    assert report.executed is True
    assert not report.has_failures
    per_table = {r.label: r.deleted for r in report.results}
    assert per_table == {"scan_logs": 1, "time_entries": 1, "material_usage": 1}
    assert report.total_deleted == 3

    # One expired row removed from each table; the within-period row remains.
    assert await _count(db_session, ScanLog) == 1
    assert await _count(db_session, TimeEntry) == 1
    assert await _count(db_session, MaterialUsage) == 1


@pytest.mark.asyncio
async def test_financial_within_statutory_period_is_never_touched(
    db_session: AsyncSession, seeded
):
    await sweep_retention(db_session, execute=True, now=NOW)

    # The mid-2016 financial rows are inside their 10-year window and must
    # survive an --execute run.
    te_within = (
        await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == seeded["te_within"])
        )
    ).scalar_one_or_none()
    mu_within = (
        await db_session.execute(
            select(MaterialUsage).where(MaterialUsage.id == seeded["mu_within"])
        )
    ).scalar_one_or_none()
    assert te_within is not None
    assert mu_within is not None

    # …and the expired ones are gone.
    te_expired = (
        await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == seeded["te_expired"])
        )
    ).scalar_one_or_none()
    assert te_expired is None


@pytest.mark.asyncio
async def test_per_table_failure_is_flagged_and_other_tables_still_run(
    db_session: AsyncSession, seeded
):
    good_rule = next(r for r in RETENTION_RULES if r.label == "scan_logs")
    # A rule whose anchor column does not exist raises inside _sweep_rule.
    bad_rule = RetentionRule(
        label="broken",
        model=TimeEntry,
        retention_class="financial_10y",
        anchor_attr="does_not_exist",
        pk_attr="id",
        legal_basis="x",
        period_human="y",
        financial_year_end_years=10,
    )

    report = await sweep_retention(
        db_session, execute=True, now=NOW, rules=(good_rule, bad_rule)
    )

    assert report.has_failures
    assert [r.label for r in report.failures] == ["broken"]
    # The good rule still ran and deleted its expired scan_log.
    scan_result = next(r for r in report.results if r.label == "scan_logs")
    assert scan_result.deleted == 1
    assert await _count(db_session, ScanLog) == 1
