"""
Estimator service — V1.3 estimator, Phase 1, Task 5.

Wires Tasks 1-4 together: loads the labor corpus (Task 2,
``labor_corpus_service.load_corpus``), runs the statistical
``LaborEstimator`` (Task 3) to get an honest hours estimate, and converts
its per-activity suggested hours into a labor COST via the Task-1
per-activity hourly-rate path (``CostCalculationService``). Returns a
single customer-facing ``labor_cost_p50`` plus an internal-only P20/P80
cost range.

Financial-exposure rules (CLAUDE.md, this plan's Global Constraints —
this is PRICING data, correctness is the #1 requirement):

* ``insufficient_data`` => every numeric field on the response is
  ``None``. Never fabricate a number from too few comparable orders.
* A stale/unknown ``activity_id`` in ``suggested_activities`` (e.g. the
  ``Activity`` row was deleted after the corpus order was recorded) must
  not silently produce a plausible-but-wrong price: those hours are
  excluded from the labor cost computation and logged as a warning,
  never crash. See ``_known_activity_hours`` below — this is a DIFFERENT
  case from an activity with a NULL ``hourly_rate``, which is a
  legitimate, intentional shop-default fallback already handled inside
  ``CostCalculationService._calculate_labor_cost_per_activity`` (Task 1).
* Raw ``hourly_rate`` values are never returned to callers — only
  aggregate computed costs (see ``models/estimator.py::
  LaborEstimateResponse``).

Cost basis (BE-10 / decision D-09, 2026-09-25 audit, assumption A6 — the
plan's stated default, since neither pending estimator decision had been
answered by Max at fix time): ``labor_cost_p50 = hours_p50 x blended
rate``. The "blended rate" is the known-activity-hours-weighted average
EUR/hour over ``suggested_activities`` (``_blended_hourly_rate``).
Before this fix, ``labor_cost_p50`` was priced as
``sum(cost(activity) for activity in suggested_activities)`` — but
``suggested_activities`` (Task 3) only carried the median hours from
orders that happened to log each activity, with NO zero-filling, so its
hours could sum to MORE than ``hours_p50`` (a one-off activity on a
single matched order still counted its full hours). That summed a
different, larger number of hours than the ``hours_p50`` actually shown
to the customer — e.g. 5 comparable rings each with 1h Polieren, one of
which also logged 2h Gravur: ``hours_p50`` is 1h, but the old code priced
3h (1 Polieren + 2 Gravur) worth of labor. Pricing at ``hours_p50 x
blended rate`` instead guarantees the priced total is always exactly the
``hours_p50`` figure shown, using whatever per-activity rate information
``suggested_activities`` provides to build a representative EUR/hour
figure (labor_estimator.py's zero-fill + 50%-presence floor keeps that
breakdown's summed hours close to ``hours_p50``, but ``estimate_labor``
never relies on them being exactly equal).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import Activity as ActivityModel
from goldsmith_erp.ml.labor_estimator import (
    EstimateFeatures,
    LaborEstimate,
    LaborEstimator,
)
from goldsmith_erp.models._common import dec, money
from goldsmith_erp.models.estimator import LaborEstimateResponse
from goldsmith_erp.services import labor_corpus_service
from goldsmith_erp.services.cost_calculation_service import CostCalculationService

logger = logging.getLogger(__name__)

# Tag recorded on future EstimateAccuracy rows (Task 4 storage, wired once
# Phase 3 persists an accepted estimate onto a quote) so calibration can be
# sliced by estimator revision if the tier/percentile logic ever changes.
ESTIMATOR_VERSION = "labor_estimator_v1"


async def _known_activity_hours(
    db: AsyncSession, activity_hours: dict[int, float]
) -> dict[int, float]:
    """
    Resolve a ``{activity_id: hours}`` breakdown to only the subset whose
    ``activity_id`` still exists in the DB, guarding against stale/unknown
    activity ids.

    ``CostCalculationService._calculate_labor_cost_per_activity`` already
    falls back to the shop default rate (``settings.DEFAULT_HOURLY_RATE``)
    for an activity whose ``hourly_rate`` is NULL *or* whose id isn't
    found in the DB — that blanket fallback is correct for the "NULL rate"
    case (Task 1's intentional default) but WRONG for "id not found": a
    stale/unknown activity_id (the corpus order referenced an ``Activity``
    that has since been deleted) silently reusing the shop-default rate
    would produce a plausible-looking but unverifiable price. So this
    helper resolves which ids actually exist FIRST, logs a warning, and
    drops any unknown id's hours entirely (excluded from the cost, not
    charged at any rate) — the known subset is what both
    ``_labor_cost_from_activity_hours`` and ``_blended_hourly_rate``
    forward onward to the Task-1 per-activity costing path.
    """
    if not activity_hours:
        return {}

    result = await db.execute(
        select(ActivityModel.id).where(ActivityModel.id.in_(activity_hours.keys()))
    )
    known_ids = set(result.scalars().all())
    unknown_ids = set(activity_hours) - known_ids

    if unknown_ids:
        logger.warning(
            "estimator_service: unknown/stale activity_id(s) in "
            "suggested_activities — excluding their hours from the labor "
            "cost computation rather than silently defaulting to the "
            "shop rate",
            extra={"unknown_activity_ids": sorted(unknown_ids)},
        )

    return {
        activity_id: hours
        for activity_id, hours in activity_hours.items()
        if activity_id in known_ids
    }


async def _labor_cost_from_activity_hours(
    db: AsyncSession, activity_hours: dict[int, float]
) -> Decimal:
    """
    Convert a ``{activity_id: hours}`` breakdown into a labor cost via the
    Task-1 per-activity hourly-rate path, guarding against stale/unknown
    activity ids (see ``_known_activity_hours``).

    Kept as a standalone helper (used directly by
    ``TestUnknownActivityIdGuard`` in tests/unit/test_estimator_service.py)
    — ``estimate_labor`` itself no longer calls this for its priced total
    (see ``_blended_hourly_rate`` / BE-10 module docstring), since costing
    only the known-activity subset of hours understates the price
    whenever ``suggested_activities`` includes a hole (a stale id, or an
    activity below the 50% presence floor) relative to ``hours_p50``.
    """
    known_activity_hours = await _known_activity_hours(db, activity_hours)
    return await CostCalculationService._calculate_labor_cost_per_activity(
        db, known_activity_hours
    )


async def _blended_hourly_rate(
    db: AsyncSession, activity_hours: dict[int, float]
) -> Decimal:
    """
    Weighted-average EUR/hour rate across a ``{activity_id: hours}``
    breakdown (BE-10 / decision D-09): the known-activity subset's total
    per-activity cost (Task 1's rate path, via ``_known_activity_hours``)
    divided by its total hours — an activity that makes up more of the
    job pulls the blended rate further toward its own rate.

    Falls back to the shop default rate (``settings.DEFAULT_HOURLY_RATE``)
    when there are no known, positive-hour activities to weight by (e.g.
    every suggested activity referenced a stale/deleted ``Activity`` row).
    This mirrors Task 1's existing "unset/unknown rate -> shop default"
    fallback rather than inventing a new "cannot price" behavior: refusing
    to price would discard the still-honest ``hours_p50`` figure over a
    rate-lookup edge case, not a "too few comparable orders" one — the
    ``insufficient_data`` case already covers the latter.
    """
    known_activity_hours = await _known_activity_hours(db, activity_hours)
    total_known_hours = sum(known_activity_hours.values())
    if total_known_hours <= 0:
        return dec(settings.DEFAULT_HOURLY_RATE)

    total_known_cost = await CostCalculationService._calculate_labor_cost_per_activity(
        db, known_activity_hours
    )
    return total_known_cost / dec(total_known_hours)


def _scale_cost(
    labor_cost_p50: Decimal, hours_p50: float, hours_target: float
) -> Decimal:
    """
    Approximate the P20/P80 labor cost by scaling ``labor_cost_p50`` by
    the ratio of ``hours_target`` to ``hours_p50``.

    ``suggested_activities`` (Task 3) only carries per-activity MEDIAN
    (p50-equivalent) hours, not a full per-activity P20/P80 breakdown, so
    there is no exact per-activity cost at the range endpoints. Scaling
    the p50 cost by the aggregate hours ratio preserves the per-activity
    rate mix already computed at p50 while giving an honest, proportional
    internal cost range. Guards ``hours_p50 <= 0`` (no ratio is defined,
    and this should be unreachable for a non-insufficient estimate) by
    returning 0.0 rather than dividing by zero.
    """
    if hours_p50 <= 0:
        return Decimal("0.00")
    return money(labor_cost_p50 * dec(hours_target) / dec(hours_p50))


async def estimate_labor(
    db: AsyncSession, features: EstimateFeatures
) -> LaborEstimateResponse:
    """
    Produce a labor-hours + labor-cost estimate for the given job features.

    Pipeline: load the corpus (Task 2) -> ``LaborEstimator.estimate``
    (Task 3) -> price ``hours_p50 x blended rate`` (BE-10 / decision D-09,
    ``_blended_hourly_rate``, with the unknown-activity_id guard
    documented on ``_known_activity_hours``).

    When the estimate reports ``insufficient_data``, every numeric field
    on the response is ``None`` — this is never overridden with a
    fabricated number, per the plan's "never fake confidence" rule.
    ``sample_size``/``similarity_level``/``similar_orders`` are still
    returned in that case (honest facts about the corpus, not a
    fabricated price).
    """
    corpus = await labor_corpus_service.load_corpus(db)
    estimate: LaborEstimate = LaborEstimator().estimate(features, corpus)

    if estimate.insufficient_data:
        return LaborEstimateResponse(
            hours_p50=None,
            hours_p20=None,
            hours_p80=None,
            labor_cost_p50=None,
            labor_cost_p20=None,
            labor_cost_p80=None,
            sample_size=estimate.sample_size,
            similarity_level=estimate.similarity_level,
            similar_orders=estimate.similar_orders,
            insufficient_data=True,
        )

    if (
        estimate.hours_p50 is None
        or estimate.hours_p20 is None
        or estimate.hours_p80 is None
    ):
        # Unreachable given insufficient_data is False (LaborEstimator only
        # ever leaves these None together with insufficient_data=True), but
        # checked explicitly (not `assert`, which `-O` strips) so a future
        # estimator bug fails loudly instead of silently computing a price
        # from a None hours value.
        raise ValueError(
            "LaborEstimate reported insufficient_data=False but is missing "
            "an hours percentile — refusing to compute a price from it"
        )

    # BE-10 / decision D-09: price at hours_p50 x blended rate, NOT
    # sum(per-activity cost) -- see this module's docstring. This
    # guarantees the priced total is always exactly hours_p50 hours' worth,
    # regardless of whether suggested_activities' own hours sum to it.
    blended_rate = await _blended_hourly_rate(db, estimate.suggested_activities)
    labor_cost_p50 = money(dec(estimate.hours_p50) * blended_rate)
    labor_cost_p20 = _scale_cost(labor_cost_p50, estimate.hours_p50, estimate.hours_p20)
    labor_cost_p80 = _scale_cost(labor_cost_p50, estimate.hours_p50, estimate.hours_p80)

    return LaborEstimateResponse(
        hours_p50=estimate.hours_p50,
        hours_p20=estimate.hours_p20,
        hours_p80=estimate.hours_p80,
        labor_cost_p50=labor_cost_p50,
        labor_cost_p20=labor_cost_p20,
        labor_cost_p80=labor_cost_p80,
        sample_size=estimate.sample_size,
        similarity_level=estimate.similarity_level,
        similar_orders=estimate.similar_orders,
        insufficient_data=False,
    )
