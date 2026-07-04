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
  never crash. See ``_labor_cost_from_activity_hours`` below — this is a
  DIFFERENT case from an activity with a NULL ``hourly_rate``, which is a
  legitimate, intentional shop-default fallback already handled inside
  ``CostCalculationService._calculate_labor_cost_per_activity`` (Task 1).
* Raw ``hourly_rate`` values are never returned to callers — only
  aggregate computed costs (see ``models/estimator.py::
  LaborEstimateResponse``).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Activity as ActivityModel
from goldsmith_erp.ml.labor_estimator import (
    EstimateFeatures,
    LaborEstimate,
    LaborEstimator,
)
from goldsmith_erp.models.estimator import LaborEstimateResponse
from goldsmith_erp.services import labor_corpus_service
from goldsmith_erp.services.cost_calculation_service import CostCalculationService

logger = logging.getLogger(__name__)

# Tag recorded on future EstimateAccuracy rows (Task 4 storage, wired once
# Phase 3 persists an accepted estimate onto a quote) so calibration can be
# sliced by estimator revision if the tier/percentile logic ever changes.
ESTIMATOR_VERSION = "labor_estimator_v1"


async def _labor_cost_from_activity_hours(
    db: AsyncSession, activity_hours: dict[int, float]
) -> float:
    """
    Convert a ``{activity_id: hours}`` breakdown into a labor cost via the
    Task-1 per-activity hourly-rate path, guarding against stale/unknown
    activity ids.

    ``CostCalculationService._calculate_labor_cost_per_activity`` already
    falls back to the shop default rate (``settings.DEFAULT_HOURLY_RATE``)
    for an activity whose ``hourly_rate`` is NULL *or* whose id isn't
    found in the DB — that blanket fallback is correct for the "NULL rate"
    case (Task 1's intentional default) but WRONG for "id not found": a
    stale/unknown activity_id (the corpus order referenced an ``Activity``
    that has since been deleted) silently reusing the shop-default rate
    would produce a plausible-looking but unverifiable price. So this
    helper resolves which ids actually exist FIRST, logs a warning and
    drops any unknown id's hours entirely (excluded from the cost, not
    charged at any rate), and only forwards the known subset onward to
    the Task-1 per-activity costing path.
    """
    if not activity_hours:
        return 0.0

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

    known_activity_hours = {
        activity_id: hours
        for activity_id, hours in activity_hours.items()
        if activity_id in known_ids
    }

    return await CostCalculationService._calculate_labor_cost_per_activity(
        db, known_activity_hours
    )


def _scale_cost(labor_cost_p50: float, hours_p50: float, hours_target: float) -> float:
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
        return 0.0
    return round(labor_cost_p50 * (hours_target / hours_p50), 2)


async def estimate_labor(
    db: AsyncSession, features: EstimateFeatures
) -> LaborEstimateResponse:
    """
    Produce a labor-hours + labor-cost estimate for the given job features.

    Pipeline: load the corpus (Task 2) -> ``LaborEstimator.estimate``
    (Task 3) -> convert ``suggested_activities`` to a labor cost via the
    Task-1 per-activity rate path (with the unknown-activity_id guard
    documented on ``_labor_cost_from_activity_hours``).

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

    labor_cost_p50 = await _labor_cost_from_activity_hours(
        db, estimate.suggested_activities
    )
    labor_cost_p20 = _scale_cost(labor_cost_p50, estimate.hours_p50, estimate.hours_p20)
    labor_cost_p80 = _scale_cost(labor_cost_p50, estimate.hours_p50, estimate.hours_p80)

    return LaborEstimateResponse(
        hours_p50=estimate.hours_p50,
        hours_p20=estimate.hours_p20,
        hours_p80=estimate.hours_p80,
        labor_cost_p50=round(labor_cost_p50, 2),
        labor_cost_p20=labor_cost_p20,
        labor_cost_p80=labor_cost_p80,
        sample_size=estimate.sample_size,
        similarity_level=estimate.similarity_level,
        similar_orders=estimate.similar_orders,
        insufficient_data=False,
    )
