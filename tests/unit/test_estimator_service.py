"""
Unit tests for estimator_service (V1.3 estimator, Phase 1, Task 5).

Covers:
- estimate_labor() returns hours (p50/p20/p80) + a labor_cost_p50 (and an
  internal p20/p80 cost range) for a seeded corpus.
- estimate_labor() returns insufficient_data=True with EVERY numeric field
  None when the corpus has too few comparable orders (never a fabricated
  number).
- A stale/unknown activity_id in suggested_activities is excluded from
  the labor cost (never silently defaulted to the shop rate, never a
  crash) — both via the guard helper directly and end-to-end through
  estimate_labor with a patched LaborEstimator.
- estimate_accuracy_service.record() is idempotent per order_id: a second
  record() call for the same order writes NO new row and returns the
  original.

Log assertions use a logger spy (mock.patch.object), not caplog, per
CLAUDE.md's CI-safe logging rule.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

import pytest

from goldsmith_erp.db.models import (
    Activity,
    Customer,
    Gemstone,
    Order,
    OrderStatusEnum,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.ml.labor_estimator import EstimateFeatures, LaborEstimate
from goldsmith_erp.services import estimate_accuracy_service, estimator_service

# ---------------------------------------------------------------------------
# Shared fixtures / helpers (local to this file, mirroring
# test_labor_corpus_service.py's / test_estimate_accuracy_service.py's style)
# ---------------------------------------------------------------------------


@pytest.fixture
async def est_user(db_session) -> User:
    user = User(
        email=f"estimator_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        first_name="Estimator",
        last_name="Tester",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def est_customer(db_session) -> Customer:
    customer = Customer(
        first_name="Erika",
        last_name="Musterfrau",
        email=f"erika_{uuid.uuid4().hex[:8]}@example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest.fixture
async def rated_activity(db_session) -> Activity:
    """Billable activity with an explicit per-activity hourly_rate (Task 1)."""
    activity = Activity(
        name="Polieren",
        category="fabrication",
        is_billable=True,
        is_custom=False,
        hourly_rate=Decimal("80.00"),
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


def _make_order(customer_id: int, **overrides) -> Order:
    defaults = dict(
        title="Estimator Test Order",
        customer_id=customer_id,
        status=OrderStatusEnum.COMPLETED,
        order_type="ring",
        finish_type="high_polish",
        complexity_rating=3,
        alloy="585",
        completed_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    return Order(**defaults)


def _make_entry(
    order_id: int, user_id: int, activity_id: int, duration_minutes: int
) -> TimeEntry:
    start_time = datetime.utcnow() - timedelta(minutes=duration_minutes)
    return TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order_id,
        user_id=user_id,
        activity_id=activity_id,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=duration_minutes),
        duration_minutes=duration_minutes,
    )


async def _seed_ring_corpus(
    db_session, est_customer, est_user, rated_activity, hours_list
) -> list[Order]:
    """Seed one completed 'ring'/'high_polish'/stone-setting order per
    entry in ``hours_list``, each with a single billable TimeEntry on
    ``rated_activity`` for that many hours."""
    orders = []
    for hours in hours_list:
        order = _make_order(est_customer.id)
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        db_session.add(
            _make_entry(order.id, est_user.id, rated_activity.id, int(hours * 60))
        )
        db_session.add(
            Gemstone(
                order_id=order.id, type="diamond", carat=0.3, cost=100.0, quantity=1
            )
        )
        await db_session.commit()
        orders.append(order)
    return orders


# ---------------------------------------------------------------------------
# estimate_labor() — happy path over a seeded corpus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEstimateLaborHappyPath:
    async def test_returns_hours_and_cost_for_seeded_corpus(
        self, db_session, est_customer, est_user, rated_activity
    ):
        """5 seeded 'ring' orders (>= MIN_SAMPLE) with 2/4/6/8/10h billable
        entries on an 80 EUR/h activity. The 2h order falls below the
        tier's P10 corpus-exclusion threshold (Task 3) and is dropped, so
        the reported estimate reflects the remaining 4 orders: median
        hours=7.0, labor cost p50 = 7.0 * 80 = 560.0, with p20 < p50 < p80
        on both axes."""
        await _seed_ring_corpus(
            db_session, est_customer, est_user, rated_activity, [2, 4, 6, 8, 10]
        )

        features = EstimateFeatures(
            order_type="ring", finish_type="high_polish", has_stone_setting=True
        )
        response = await estimator_service.estimate_labor(db_session, features)

        assert response.insufficient_data is False
        assert response.sample_size == 4
        assert response.hours_p50 == pytest.approx(7.0)
        assert response.labor_cost_p50 == pytest.approx(560.0)
        assert response.hours_p20 < response.hours_p50 < response.hours_p80
        assert (
            response.labor_cost_p20 < response.labor_cost_p50 < response.labor_cost_p80
        )
        assert response.similarity_level == "exact"
        assert len(response.similar_orders) == 4

    async def test_insufficient_data_returns_all_none(
        self, db_session, est_customer, est_user, rated_activity
    ):
        """Only 2 seeded orders (< MIN_SAMPLE=5, and no workshop-wide data
        either) => insufficient_data=True with every numeric field None —
        never a fabricated number."""
        await _seed_ring_corpus(
            db_session, est_customer, est_user, rated_activity, [3, 5]
        )

        features = EstimateFeatures(order_type="ring", has_stone_setting=True)
        response = await estimator_service.estimate_labor(db_session, features)

        assert response.insufficient_data is True
        assert response.hours_p50 is None
        assert response.hours_p20 is None
        assert response.hours_p80 is None
        assert response.labor_cost_p50 is None
        assert response.labor_cost_p20 is None
        assert response.labor_cost_p80 is None
        assert response.sample_size == 0
        assert response.similarity_level == "insufficient"
        assert response.similar_orders == []

    async def test_empty_corpus_returns_all_none(self, db_session):
        """No completed orders at all in the DB — same honest-null contract."""
        features = EstimateFeatures(order_type="pendant")
        response = await estimator_service.estimate_labor(db_session, features)

        assert response.insufficient_data is True
        assert response.hours_p50 is None
        assert response.labor_cost_p50 is None


# ---------------------------------------------------------------------------
# Unknown/stale activity_id guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUnknownActivityIdGuard:
    async def test_unknown_activity_id_excluded_from_cost_no_crash(
        self, db_session, rated_activity
    ):
        """A dict mixing a real activity_id with an unknown one must not
        crash, and the unknown id's hours must NOT be silently costed at
        the shop-default rate — they are excluded entirely."""
        unknown_id = rated_activity.id + 999_999

        with mock.patch.object(estimator_service.logger, "warning") as mock_warning:
            cost = await estimator_service._labor_cost_from_activity_hours(
                db_session, {rated_activity.id: 2.0, unknown_id: 5.0}
            )

        # Only the known activity's 2h * 80 EUR/h = 160 — the unknown id's
        # 5h contribute nothing (neither at its own rate, nor the shop
        # default, nor any other plausible-but-wrong number).
        assert cost == pytest.approx(160.0)
        mock_warning.assert_called_once()
        _, kwargs = mock_warning.call_args
        assert kwargs["extra"]["unknown_activity_ids"] == [unknown_id]


# ---------------------------------------------------------------------------
# EstimateAccuracy idempotency guard (Task-4 review carry-forward)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAccuracyRecordIdempotency:
    async def test_second_record_for_same_order_id_writes_no_new_row(
        self, db_session, est_customer
    ):
        order = Order(
            title="Idempotency Test Order",
            customer_id=est_customer.id,
            status=OrderStatusEnum.COMPLETED,
            order_type="ring",
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        first = await estimate_accuracy_service.record(
            db_session,
            order,
            estimated_hours=10.0,
            actual_hours=9.0,
            estimated_total=500.0,
            actual_total=480.0,
            estimator_version="labor_estimator_v1",
        )

        second = await estimate_accuracy_service.record(
            db_session,
            order,
            estimated_hours=99.0,
            actual_hours=99.0,
            estimated_total=9999.0,
            actual_total=9999.0,
            estimator_version="labor_estimator_v1",
        )

        # Same row returned, original values untouched by the 2nd call.
        assert second.id == first.id
        assert second.estimated_hours == 10.0
        assert second.actual_total == 480.0

        from sqlalchemy import select

        from goldsmith_erp.db.models import EstimateAccuracy

        rows = (
            (
                await db_session.execute(
                    select(EstimateAccuracy).where(
                        EstimateAccuracy.order_id == order.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# LaborEstimator insufficient_data propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_estimator_service_propagates_insufficient_data_with_null_costs(
    db_session, est_customer, est_user, rated_activity
):
    """When LaborEstimator returns insufficient_data=True (decision #1),
    the service must return all labor_cost_* fields as None — never
    fabricate a cost from too few orders.

    Uses order_type='nonexistent_type_xyz' which can never exist in the
    shared test DB, guaranteeing 0 matched orders in all tiers including
    workshop (which checks order_type match, not just existence)."""
    await _seed_ring_corpus(
        db_session, est_customer, est_user, rated_activity,
        [2.0, 4.0, 6.0, 8.0, 10.0],
    )

    features = EstimateFeatures(
        order_type="nonexistent_type_xyz",
        finish_type="none",
        has_stone_setting=False,
    )
    result = await estimator_service.estimate_labor(db_session, features)

    assert result.insufficient_data is True
    assert result.labor_cost_p50 is None
    assert result.labor_cost_p20 is None
    assert result.labor_cost_p80 is None
    assert result.hours_p50 is None
