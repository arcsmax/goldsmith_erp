"""
Unit tests for the estimator's cost basis (BE-10 / W1-16 / decision D-09).

Before this fix, ``estimator_service.estimate_labor`` priced labor as
``sum(per-activity cost)`` where the per-activity hours
(``suggested_activities``, from ``labor_estimator._median_activity_hours``)
were the median hours ONLY across the orders that logged that activity —
no zero-filling. An activity logged by a small minority of the matched
set (e.g. one ring out of five that also needed Gravur) still dragged its
full median hours into the breakdown, so the priced cost summed to MORE
hours than ``hours_p50`` — the number actually shown to the customer.

Fix (assumption A6 / decision D-09, the plan's stated default):
  * ``labor_estimator._median_activity_hours`` now zero-fills each
    activity's hours across the WHOLE matched set and reports it in
    ``suggested_activities`` only when present in at least 50% of that
    set (``ACTIVITY_PRESENCE_THRESHOLD``) — a one-off activity like
    Gravur above is dropped rather than inflating the breakdown.
  * ``estimator_service.estimate_labor`` prices at ``hours_p50 x blended
    rate``, where the blended rate is the known-activity-weighted average
    EUR/hour over ``suggested_activities`` (``_blended_hourly_rate``) —
    never ``sum(per-activity cost)`` again, so the priced total is always
    exactly ``hours_p50`` hours' worth, consistent with the number shown.

Covers:
- ``_median_activity_hours`` (via ``LaborEstimator.estimate``): zero-
  filling + the 50% presence threshold, using the plan's own example
  (five rings each 1h Polieren, one of them also 2h Gravur).
- The suggested-activities' zero-filled hours sum to within 10% of
  ``hours_p50`` for that same scenario.
- ``estimate_labor`` end-to-end: ``labor_cost_p50 == 75.00`` (hours_p50=
  1.0h x 75 EUR/h), not the pre-fix ``225.00`` (1h Polieren + 2h Gravur,
  both costed, summed without regard to hours_p50).
- P20/P80 labor cost still scales proportionally from the corrected p50
  base.
- ``_blended_hourly_rate`` falls back to the shop default rate (never a
  crash, never a fabricated per-activity price) when every suggested
  activity_id is stale/unknown.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import Activity as ActivityModel
from goldsmith_erp.db.models import (
    Customer,
    Gemstone,
    Order,
    OrderStatusEnum,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.ml.labor_estimator import EstimateFeatures, LaborEstimator
from goldsmith_erp.services import estimator_service
from goldsmith_erp.services.labor_corpus_service import CorpusOrder

pytestmark = pytest.mark.unit

POLIEREN_ID = 1
GRAVUR_ID = 2


# ---------------------------------------------------------------------------
# Pure-Python: labor_estimator zero-fill + 50% presence threshold
# ---------------------------------------------------------------------------


def _corpus_order(
    order_id: int, actual_hours: float, activity_hours: dict[int, float]
) -> CorpusOrder:
    return CorpusOrder(
        order_id=order_id,
        order_type="ring",
        finish_type="polished",
        complexity_rating=3,
        has_stone_setting=True,
        alloy="gold_585",
        actual_hours=actual_hours,
        activity_hours=activity_hours,
    )


def _five_rings_one_with_gravur() -> list[CorpusOrder]:
    """Five rings each with 1.0h Polieren; one of them ALSO has 2.0h
    Gravur (so that one order's total actual_hours is 3.0h). Matches the
    MASTER-FIX-PLAN.md W1-16 packet's example exactly."""
    return [
        _corpus_order(901, actual_hours=1.0, activity_hours={POLIEREN_ID: 1.0}),
        _corpus_order(902, actual_hours=1.0, activity_hours={POLIEREN_ID: 1.0}),
        _corpus_order(903, actual_hours=1.0, activity_hours={POLIEREN_ID: 1.0}),
        _corpus_order(904, actual_hours=1.0, activity_hours={POLIEREN_ID: 1.0}),
        _corpus_order(
            905, actual_hours=3.0, activity_hours={POLIEREN_ID: 1.0, GRAVUR_ID: 2.0}
        ),
    ]


def _estimate_five_rings():
    features = EstimateFeatures(
        order_type="ring", finish_type="polished", has_stone_setting=True
    )
    return LaborEstimator().estimate(features, _five_rings_one_with_gravur())


def test_hours_p50_is_the_median_of_total_hours_per_order() -> None:
    """hours_p50 is 1.0h -- the median of the TOTAL hours per order,
    unaffected by the fact that one order also logged Gravur."""
    estimate = _estimate_five_rings()

    assert estimate.insufficient_data is False
    assert estimate.sample_size == 5
    assert estimate.hours_p50 == 1.0


def test_gravur_not_suggested_below_50pct_presence() -> None:
    """Gravur is logged on only 1 of the 5 matched orders (20% < 50%) and
    must not appear in suggested_activities at all (BE-10)."""
    estimate = _estimate_five_rings()

    assert GRAVUR_ID not in estimate.suggested_activities
    assert estimate.suggested_activities == {POLIEREN_ID: 1.0}


def test_suggested_hours_sum_within_10_percent_of_hours_p50() -> None:
    estimate = _estimate_five_rings()

    suggested_sum = sum(estimate.suggested_activities.values())
    assert suggested_sum == pytest.approx(estimate.hours_p50, rel=0.10)


def test_activity_present_in_exactly_half_the_set_is_still_suggested() -> None:
    """'At least 50%' includes exactly 50% -- a 3-of-6 activity is
    suggested, zero-filled across all 6 (not just the 3 that logged it)."""
    corpus = [
        _corpus_order(1001, actual_hours=4.0, activity_hours={POLIEREN_ID: 4.0}),
        _corpus_order(1002, actual_hours=4.0, activity_hours={POLIEREN_ID: 4.0}),
        _corpus_order(1003, actual_hours=4.0, activity_hours={POLIEREN_ID: 4.0}),
        _corpus_order(
            1004,
            actual_hours=8.0,
            activity_hours={POLIEREN_ID: 4.0, GRAVUR_ID: 4.0},
        ),
        _corpus_order(
            1005,
            actual_hours=8.0,
            activity_hours={POLIEREN_ID: 4.0, GRAVUR_ID: 4.0},
        ),
        _corpus_order(
            1006,
            actual_hours=8.0,
            activity_hours={POLIEREN_ID: 4.0, GRAVUR_ID: 4.0},
        ),
    ]
    features = EstimateFeatures(
        order_type="ring", finish_type="polished", has_stone_setting=True
    )

    estimate = LaborEstimator().estimate(features, corpus)

    # Gravur logged on 3/6 = 50% -- meets "at least 50%", so it IS
    # suggested. Zero-filled across all 6: [0, 0, 0, 4, 4, 4] -> median 2.0.
    assert GRAVUR_ID in estimate.suggested_activities
    assert estimate.suggested_activities[GRAVUR_ID] == 2.0


# ---------------------------------------------------------------------------
# DB-backed: estimator_service.estimate_labor prices at hours_p50 x blended rate
# ---------------------------------------------------------------------------


def _make_order(customer_id: int, **overrides) -> Order:
    defaults = dict(
        title="Cost Basis Test Order",
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


@pytest.fixture
async def cb_user(db_session) -> User:
    user = User(
        email=f"cost_basis_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        first_name="CostBasis",
        last_name="Tester",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def cb_customer(db_session) -> Customer:
    customer = Customer(
        first_name="Cost",
        last_name="Basis",
        email=f"cost_basis_{uuid.uuid4().hex[:8]}@example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest.fixture
async def polieren_activity(db_session) -> ActivityModel:
    activity = ActivityModel(
        name="Polieren",
        category="fabrication",
        is_billable=True,
        is_custom=False,
        hourly_rate=Decimal("75.00"),
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest.fixture
async def gravur_activity(db_session) -> ActivityModel:
    activity = ActivityModel(
        name="Gravur",
        category="fabrication",
        is_billable=True,
        is_custom=False,
        hourly_rate=Decimal("75.00"),
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest.mark.asyncio
class TestEstimateLaborCostBasis:
    async def test_labor_cost_p50_matches_hours_p50_times_blended_rate(
        self, db_session, cb_customer, cb_user, polieren_activity, gravur_activity
    ):
        """The five-rings-one-with-Gravur scenario end-to-end: labor_cost_p50
        must be 75.00 (hours_p50=1.0h x 75 EUR/h), NOT the pre-fix 225.00
        (1h Polieren + 2h Gravur, both @ 75 EUR/h, summed regardless of
        hours_p50)."""
        per_order_activity_hours = [
            {polieren_activity.id: 1.0},
            {polieren_activity.id: 1.0},
            {polieren_activity.id: 1.0},
            {polieren_activity.id: 1.0},
            {polieren_activity.id: 1.0, gravur_activity.id: 2.0},
        ]
        for hours_by_activity in per_order_activity_hours:
            order = _make_order(cb_customer.id)
            db_session.add(order)
            await db_session.commit()
            await db_session.refresh(order)
            for activity_id, hours in hours_by_activity.items():
                db_session.add(
                    _make_entry(order.id, cb_user.id, activity_id, int(hours * 60))
                )
            db_session.add(
                Gemstone(
                    order_id=order.id, type="diamond", carat=0.3, cost=100.0, quantity=1
                )
            )
            await db_session.commit()

        features = EstimateFeatures(
            order_type="ring", finish_type="high_polish", has_stone_setting=True
        )
        response = await estimator_service.estimate_labor(db_session, features)

        assert response.insufficient_data is False
        assert response.sample_size == 5
        assert float(response.hours_p50) == pytest.approx(1.0)
        assert float(response.labor_cost_p50) == pytest.approx(75.00)
        # The pre-fix bug priced 3h (1h Polieren + 2h Gravur) at 75/h = 225.00.
        assert float(response.labor_cost_p50) != pytest.approx(225.00)

    async def test_p20_p80_cost_scales_from_the_corrected_p50_base(
        self, db_session, cb_customer, cb_user, polieren_activity, gravur_activity
    ):
        per_order_activity_hours = [
            {polieren_activity.id: 1.0},
            {polieren_activity.id: 1.0},
            {polieren_activity.id: 1.0},
            {polieren_activity.id: 1.0},
            {polieren_activity.id: 1.0, gravur_activity.id: 2.0},
        ]
        for hours_by_activity in per_order_activity_hours:
            order = _make_order(cb_customer.id)
            db_session.add(order)
            await db_session.commit()
            await db_session.refresh(order)
            for activity_id, hours in hours_by_activity.items():
                db_session.add(
                    _make_entry(order.id, cb_user.id, activity_id, int(hours * 60))
                )
            db_session.add(
                Gemstone(
                    order_id=order.id, type="diamond", carat=0.3, cost=100.0, quantity=1
                )
            )
            await db_session.commit()

        features = EstimateFeatures(
            order_type="ring", finish_type="high_polish", has_stone_setting=True
        )
        response = await estimator_service.estimate_labor(db_session, features)

        assert response.insufficient_data is False
        # Pin the corrected p50 base explicitly -- otherwise this test
        # would pass just as well against the pre-fix 225.00 base, since
        # the p20/p80 scaling ratio is self-consistent either way.
        assert float(response.labor_cost_p50) == pytest.approx(75.00)
        expected_p20 = round(
            float(response.labor_cost_p50) * (response.hours_p20 / response.hours_p50),
            2,
        )
        expected_p80 = round(
            float(response.labor_cost_p50) * (response.hours_p80 / response.hours_p50),
            2,
        )
        assert float(response.labor_cost_p20) == pytest.approx(expected_p20)
        assert float(response.labor_cost_p80) == pytest.approx(expected_p80)


@pytest.mark.asyncio
async def test_blended_rate_falls_back_to_shop_default_when_all_ids_unknown(
    db_session,
) -> None:
    """Every suggested activity_id is stale/unknown -> fall back to the
    shop default rate (never a crash, never a fabricated per-activity
    price) so estimate_labor can still honestly price hours_p50."""
    rate = await estimator_service._blended_hourly_rate(
        db_session, {910_001: 2.0, 910_002: 3.0}
    )
    assert rate == settings.DEFAULT_HOURLY_RATE


@pytest.mark.asyncio
async def test_blended_rate_ignores_unknown_ids_and_weights_by_known_hours(
    db_session, polieren_activity, gravur_activity
) -> None:
    """A mix of a real 75 EUR/h activity, a real 100 EUR/h activity, and a
    stale id: the blended rate is the known-hours-weighted average of the
    two real rates, with the stale id's hours excluded entirely."""
    gravur_activity.hourly_rate = Decimal("100.00")
    db_session.add(gravur_activity)
    await db_session.commit()
    await db_session.refresh(gravur_activity)

    unknown_id = gravur_activity.id + 999_999
    rate = await estimator_service._blended_hourly_rate(
        db_session,
        {polieren_activity.id: 3.0, gravur_activity.id: 1.0, unknown_id: 5.0},
    )

    # (3h * 75 + 1h * 100) / (3h + 1h) = 325 / 4 = 81.25
    assert float(rate) == pytest.approx(81.25)
