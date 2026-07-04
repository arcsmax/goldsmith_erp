# src/goldsmith_erp/ml/labor_estimator.py
"""
Statistical labor-hours estimator — V1.3 estimator, Phase 1, Task 3.

``LaborEstimator`` turns a job's features into an honest hours estimate
(median + P20/P80) by relaxing similarity tiers over the labor corpus
(``labor_corpus_service.CorpusOrder`` rows, Task 2) until enough comparable
orders are found. **Statistical, not ML** — this module is pure Python
(``statistics`` + hand-rolled percentile interpolation) and has no
dependency on numpy/xgboost/sklearn/pandas, so it works even in
environments where those packages fail to import (see the ``fix/ml-duration
-predictor-api`` libomp issue this plan explicitly routes around).

Design notes
------------
* **Tier relaxation.** Four similarity tiers, most to least specific:
  ``exact`` (order_type + finish_type + has_stone_setting all match) ->
  ``type_finish`` (order_type + finish_type, stone-setting dropped) ->
  ``type`` (order_type only) -> ``workshop`` (the whole corpus, unfiltered).
  The FIRST tier whose matched set reaches ``MIN_SAMPLE`` wins — we never
  keep looking once a tier is "big enough", even if a stricter tier came
  close. If even ``workshop`` has fewer than ``MIN_SAMPLE`` orders, the
  estimate is honestly reported as ``insufficient_data`` with every number
  ``None`` rather than fabricating confidence from a handful of orders.
* **Corpus-exclusion (post-tier).** Within the chosen tier's matched set,
  orders whose ``actual_hours`` falls below the P10 threshold *of that same
  set* are treated as implausibly-under-tracked time (e.g. a forgotten
  timer) and dropped before computing percentiles. Their ids are reported
  in ``excluded_orders`` for transparency. This exclusion happens strictly
  AFTER the tier is chosen and is never used to justify relaxing to a
  broader tier — if exclusion drops the remaining set below
  ``MIN_SAMPLE``, the estimate still reports from the (now smaller)
  remaining set at the tier that was already selected. Re-relaxing at that
  point would let a handful of excluded outliers silently widen the
  comparison pool, which is the opposite of "never fake confidence".
* **Percentiles.** ``hours_p50`` uses ``statistics.median`` directly (which,
  for an even-length list, averages the two middle values — the same
  result our own linear-interpolation helper produces at the 50th
  percentile). ``hours_p20``/``hours_p80``/the internal P10 exclusion
  threshold use ``_percentile()``, a manual linear-interpolation-between-
  ranks implementation (the same method numpy's default ``'linear'`` mode
  and Excel's ``PERCENTILE.INC`` use) — no numpy dependency required.
* **suggested_activities** is the per-activity MEDIAN hours across the
  matched (post-exclusion) set, computed only from orders that actually
  logged that activity (no zero-filling for orders that didn't). This
  drives per-activity cost conversion in Task 5.
* **Immutability.** ``CorpusOrder.activity_hours`` is a shared dict living
  inside a frozen dataclass (Task 2) — this module never mutates it. Any
  aggregation builds fresh lists/dicts.
"""
from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from goldsmith_erp.services.labor_corpus_service import CorpusOrder

# ── Similarity tiers, most to least specific ─────────────────────────────────
SimilarityLevel = Literal["exact", "type_finish", "type", "workshop", "insufficient"]

# ── Percentile thresholds (named, not magic numbers) ─────────────────────────
P10: float = 10.0  # corpus-exclusion threshold: drop implausibly-low hours
P20: float = 20.0
P50: float = 50.0
P80: float = 80.0

# ── Rounding precision for reported hours ─────────────────────────────────────
ROUND_DP: int = 2

# ── Cap on how many similar-order ids we surface for explainability ─────────
MAX_SIMILAR_ORDERS: int = 20


@dataclass(frozen=True)
class EstimateFeatures:
    """The job features an estimate is requested for."""

    order_type: str
    finish_type: str | None = None
    has_stone_setting: bool = False
    alloy: str | None = None
    complexity_rating: int | None = None


@dataclass(frozen=True)
class LaborEstimate:
    """
    Result of a labor-hours estimate.

    ``hours_p50``/``hours_p20``/``hours_p80`` and ``suggested_activities``
    are ``None``/empty whenever ``insufficient_data`` is ``True`` — never
    auto-filled from too few comparable orders.
    """

    hours_p50: float | None
    hours_p20: float | None
    hours_p80: float | None
    sample_size: int
    similarity_level: SimilarityLevel
    similar_orders: list[int]
    suggested_activities: dict[int, float]  # activity_id -> median hours
    excluded_orders: list[int]
    insufficient_data: bool


def _matches_exact(order: CorpusOrder, features: EstimateFeatures) -> bool:
    return (
        order.order_type == features.order_type
        and order.finish_type == features.finish_type
        and order.has_stone_setting == features.has_stone_setting
    )


def _matches_type_finish(order: CorpusOrder, features: EstimateFeatures) -> bool:
    return (
        order.order_type == features.order_type
        and order.finish_type == features.finish_type
    )


def _matches_type(order: CorpusOrder, features: EstimateFeatures) -> bool:
    return order.order_type == features.order_type


def _matches_workshop(_order: CorpusOrder, _features: EstimateFeatures) -> bool:
    return True


# Ordered most-specific-first; the first tier whose matched set reaches
# MIN_SAMPLE is used (see LaborEstimator.estimate).
_TIER_PREDICATES: tuple[
    tuple[SimilarityLevel, Callable[[CorpusOrder, EstimateFeatures], bool]], ...
] = (
    ("exact", _matches_exact),
    ("type_finish", _matches_type_finish),
    ("type", _matches_type),
    ("workshop", _matches_workshop),
)


def _percentile(sorted_values: Sequence[float], percentile: float) -> float:
    """
    Linear-interpolation percentile of an already-sorted, non-empty sequence.

    Same method as numpy's default ``'linear'`` interpolation / Excel's
    ``PERCENTILE.INC``: the rank ``index = (percentile / 100) * (n - 1)`` is
    computed, and the value is interpolated between the two bracketing
    elements. Requires ``sorted_values`` to already be sorted ascending —
    callers sort once and reuse across P10/P20/P80 to avoid re-sorting.
    """
    if not sorted_values:
        raise ValueError("Cannot compute a percentile of an empty sequence.")

    if len(sorted_values) == 1:
        return sorted_values[0]

    index = (percentile / 100.0) * (len(sorted_values) - 1)
    lower_index = int(index)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = index - lower_index

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return lower_value + fraction * (upper_value - lower_value)


def _exclude_implausibly_low(
    matched: list[CorpusOrder],
) -> tuple[list[CorpusOrder], list[int]]:
    """
    Drop orders whose ``actual_hours`` is below the P10 threshold of ``matched``.

    Returns ``(remaining, excluded_order_ids)``. If the threshold happens to
    exclude every order (only possible with pathological/duplicate data),
    exclusion is skipped entirely rather than returning an empty set —
    corpus-exclusion is a refinement, never a way to make a tier report zero
    comparable orders.
    """
    sorted_hours = sorted(order.actual_hours for order in matched)
    threshold = _percentile(sorted_hours, P10)

    remaining = [order for order in matched if order.actual_hours >= threshold]
    excluded = [order for order in matched if order.actual_hours < threshold]

    if not remaining:
        return list(matched), []

    return remaining, [order.order_id for order in excluded]


def _median_activity_hours(orders: Sequence[CorpusOrder]) -> dict[int, float]:
    """
    Per-activity median hours across ``orders``, built from fresh lists.

    Only orders that actually logged an activity contribute to that
    activity's median (no zero-filling) — and ``CorpusOrder.activity_hours``
    (a shared dict on a frozen dataclass) is only ever read here, never
    mutated.
    """
    hours_by_activity: dict[int, list[float]] = {}
    for order in orders:
        for activity_id, hours in order.activity_hours.items():
            hours_by_activity.setdefault(activity_id, []).append(hours)

    return {
        activity_id: round(statistics.median(hours_list), ROUND_DP)
        for activity_id, hours_list in hours_by_activity.items()
    }


def _insufficient_estimate() -> LaborEstimate:
    return LaborEstimate(
        hours_p50=None,
        hours_p20=None,
        hours_p80=None,
        sample_size=0,
        similarity_level="insufficient",
        similar_orders=[],
        suggested_activities={},
        excluded_orders=[],
        insufficient_data=True,
    )


def _build_estimate(
    level: SimilarityLevel, matched: list[CorpusOrder]
) -> LaborEstimate:
    remaining, excluded_ids = _exclude_implausibly_low(matched)

    remaining_hours = sorted(order.actual_hours for order in remaining)
    hours_p50 = round(statistics.median(remaining_hours), ROUND_DP)
    hours_p20 = round(_percentile(remaining_hours, P20), ROUND_DP)
    hours_p80 = round(_percentile(remaining_hours, P80), ROUND_DP)

    return LaborEstimate(
        hours_p50=hours_p50,
        hours_p20=hours_p20,
        hours_p80=hours_p80,
        sample_size=len(remaining),
        similarity_level=level,
        similar_orders=[order.order_id for order in remaining][:MAX_SIMILAR_ORDERS],
        suggested_activities=_median_activity_hours(remaining),
        excluded_orders=excluded_ids,
        insufficient_data=False,
    )


class LaborEstimator:
    """
    Statistical (non-ML) labor-hours estimator over a ``CorpusOrder`` corpus.

    ``MIN_SAMPLE`` is the minimum matched-order count a similarity tier must
    reach before its statistics are considered honest enough to report.
    """

    MIN_SAMPLE: int = 5

    def estimate(
        self, features: EstimateFeatures, corpus: list[CorpusOrder]
    ) -> LaborEstimate:
        """
        Relax similarity tiers over ``corpus`` until one reaches ``MIN_SAMPLE``.

        Returns the first (most specific) tier's estimate once its matched
        set is large enough. If even the ``workshop`` tier (the whole
        corpus) falls short, returns an ``insufficient_data`` estimate with
        every number ``None`` — never fabricates confidence from too few
        comparable orders.
        """
        for level, predicate in _TIER_PREDICATES:
            matched = [order for order in corpus if predicate(order, features)]
            if len(matched) >= self.MIN_SAMPLE:
                return _build_estimate(level, matched)

        return _insufficient_estimate()
