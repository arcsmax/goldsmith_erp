"""
Unit tests for LaborEstimator (V1.3 estimator, Phase 1, Task 3).

Covers:
- Exact-tier match with >= MIN_SAMPLE similar orders returns a correct
  median + P20 < P50 < P80 range and lists the matched order ids.
- Sparse finish_type relaxes tier-by-tier down to the "type" tier.
- An empty/tiny corpus reports insufficient_data with every hours field None.
- A low-outlier order is excluded (P10 corpus-exclusion) and the reported
  P50 reflects only the remaining set.
- suggested_activities returns per-activity medians over the matched
  (post-exclusion) set only.
- estimate() never mutates a CorpusOrder's activity_hours dict.

Pure Python, no DB — corpora are built directly as CorpusOrder instances.
"""

from goldsmith_erp.ml.labor_estimator import EstimateFeatures, LaborEstimator
from goldsmith_erp.services.labor_corpus_service import CorpusOrder


def _corpus_order(
    order_id: int,
    *,
    order_type: str = "ring",
    finish_type: str | None = "polished",
    has_stone_setting: bool = True,
    alloy: str | None = "gold_585",
    complexity_rating: int | None = 3,
    actual_hours: float,
    activity_hours: dict[int, float] | None = None,
) -> CorpusOrder:
    """Build a CorpusOrder with sensible defaults so tests only spell out
    the fields that matter for the scenario under test."""
    return CorpusOrder(
        order_id=order_id,
        order_type=order_type,
        finish_type=finish_type,
        complexity_rating=complexity_rating,
        has_stone_setting=has_stone_setting,
        alloy=alloy,
        actual_hours=actual_hours,
        activity_hours=activity_hours or {},
    )


def test_exact_tier_match_returns_median_and_ordered_percentile_range() -> None:
    """>= MIN_SAMPLE orders matching order_type+finish_type+stone-setting
    exactly should be used at the "exact" tier, with P20 < P50 < P80."""
    corpus = [
        _corpus_order(101, actual_hours=2.0),
        _corpus_order(102, actual_hours=4.0),
        _corpus_order(103, actual_hours=6.0),
        _corpus_order(104, actual_hours=8.0),
        _corpus_order(105, actual_hours=10.0),
        _corpus_order(106, actual_hours=12.0),
    ]
    features = EstimateFeatures(
        order_type="ring", finish_type="polished", has_stone_setting=True
    )

    estimate = LaborEstimator().estimate(features, corpus)

    assert estimate.similarity_level == "exact"
    assert estimate.insufficient_data is False
    # order 101 (hours=2.0) sits below the P10 threshold of the 6-order set
    # and is dropped before percentiles are computed.
    assert estimate.excluded_orders == [101]
    assert estimate.sample_size == 5
    assert estimate.similar_orders == [102, 103, 104, 105, 106]
    assert estimate.hours_p50 == 8.0
    assert estimate.hours_p20 is not None
    assert estimate.hours_p80 is not None
    assert estimate.hours_p20 < estimate.hours_p50 < estimate.hours_p80


def test_sparse_finish_type_relaxes_to_type_tier() -> None:
    """When fewer than MIN_SAMPLE orders share the requested finish_type,
    the estimator relaxes past "exact" and "type_finish" down to "type"
    (order_type only)."""
    corpus = [
        _corpus_order(
            201, finish_type="matte", has_stone_setting=False, actual_hours=5.0
        ),
        _corpus_order(
            202, finish_type="polished", has_stone_setting=False, actual_hours=6.0
        ),
        _corpus_order(
            203, finish_type="polished", has_stone_setting=True, actual_hours=7.0
        ),
        _corpus_order(
            204, finish_type="brushed", has_stone_setting=False, actual_hours=8.0
        ),
        _corpus_order(
            205, finish_type="hammered", has_stone_setting=True, actual_hours=9.0
        ),
        _corpus_order(
            206, finish_type="satin", has_stone_setting=False, actual_hours=10.0
        ),
    ]
    features = EstimateFeatures(
        order_type="ring", finish_type="matte", has_stone_setting=False
    )

    estimate = LaborEstimator().estimate(features, corpus)

    # Only order 201 matches "exact"/"type_finish" (count=1, below
    # MIN_SAMPLE); all six orders share order_type="ring" so "type" reaches
    # MIN_SAMPLE=5 (actually 6) first. Order 201 (hours=5.0, the lowest of
    # the six) then falls below that set's P10 threshold and is excluded.
    assert estimate.similarity_level == "type"
    assert estimate.insufficient_data is False
    assert estimate.excluded_orders == [201]
    assert estimate.sample_size == 5
    assert estimate.hours_p50 == 8.0


def test_insufficient_data_when_corpus_too_small_at_every_tier() -> None:
    """Fewer than MIN_SAMPLE orders in the corpus overall (even at the
    "workshop" tier) must report insufficient_data with no fabricated
    numbers."""
    corpus = [
        _corpus_order(301, actual_hours=5.0),
        _corpus_order(302, actual_hours=6.0),
    ]
    features = EstimateFeatures(order_type="ring")

    estimate = LaborEstimator().estimate(features, corpus)

    assert estimate.insufficient_data is True
    assert estimate.similarity_level == "insufficient"
    assert estimate.sample_size == 0
    assert estimate.hours_p50 is None
    assert estimate.hours_p20 is None
    assert estimate.hours_p80 is None
    assert estimate.similar_orders == []
    assert estimate.suggested_activities == {}
    assert estimate.excluded_orders == []


def test_empty_corpus_is_insufficient_data() -> None:
    """An empty corpus is the degenerate case of "too small at every tier"."""
    estimate = LaborEstimator().estimate(EstimateFeatures(order_type="ring"), [])

    assert estimate.insufficient_data is True
    assert estimate.hours_p50 is None


def test_low_outlier_order_is_excluded_and_median_reflects_remaining_set() -> None:
    """An order whose actual_hours is far below the rest of its tier's set
    is excluded (P10 corpus-exclusion) and the reported P50 comes from the
    remaining orders only."""
    corpus = [
        _corpus_order(
            401,
            order_type="pendant",
            finish_type=None,
            has_stone_setting=False,
            actual_hours=0.5,  # forgotten-timer style implausible outlier
        ),
        _corpus_order(
            402,
            order_type="pendant",
            finish_type=None,
            has_stone_setting=False,
            actual_hours=8.0,
        ),
        _corpus_order(
            403,
            order_type="pendant",
            finish_type=None,
            has_stone_setting=False,
            actual_hours=8.5,
        ),
        _corpus_order(
            404,
            order_type="pendant",
            finish_type=None,
            has_stone_setting=False,
            actual_hours=9.0,
        ),
        _corpus_order(
            405,
            order_type="pendant",
            finish_type=None,
            has_stone_setting=False,
            actual_hours=9.5,
        ),
        _corpus_order(
            406,
            order_type="pendant",
            finish_type=None,
            has_stone_setting=False,
            actual_hours=10.0,
        ),
    ]
    features = EstimateFeatures(
        order_type="pendant", finish_type=None, has_stone_setting=False
    )

    estimate = LaborEstimator().estimate(features, corpus)

    assert estimate.similarity_level == "exact"
    assert estimate.excluded_orders == [401]
    assert 401 not in estimate.similar_orders
    assert estimate.sample_size == 5
    assert estimate.hours_p50 == 9.0


def test_suggested_activities_are_per_activity_medians_over_matched_set() -> None:
    """suggested_activities holds the median hours per activity_id, computed
    only from orders in the matched (post-exclusion) set that actually
    logged that activity — no zero-filling."""
    corpus = [
        _corpus_order(
            501,
            order_type="bracelet",
            finish_type="polished",
            has_stone_setting=False,
            actual_hours=10.0,  # excluded by P10 corpus-exclusion below
            activity_hours={1: 4.0, 2: 3.0},
        ),
        _corpus_order(
            502,
            order_type="bracelet",
            finish_type="polished",
            has_stone_setting=False,
            actual_hours=11.0,
            activity_hours={1: 5.0, 2: 4.0},
        ),
        _corpus_order(
            503,
            order_type="bracelet",
            finish_type="polished",
            has_stone_setting=False,
            actual_hours=12.0,
            activity_hours={1: 6.0},
        ),
        _corpus_order(
            504,
            order_type="bracelet",
            finish_type="polished",
            has_stone_setting=False,
            actual_hours=13.0,
            activity_hours={1: 7.0, 2: 5.0},
        ),
        _corpus_order(
            505,
            order_type="bracelet",
            finish_type="polished",
            has_stone_setting=False,
            actual_hours=14.0,
            activity_hours={1: 8.0},
        ),
    ]
    features = EstimateFeatures(
        order_type="bracelet", finish_type="polished", has_stone_setting=False
    )

    estimate = LaborEstimator().estimate(features, corpus)

    # order 501 (hours=10.0) is below this set's P10 threshold and is
    # excluded, so its activity hours (1: 4.0, 2: 3.0) must not appear.
    assert estimate.excluded_orders == [501]
    assert estimate.suggested_activities == {1: 6.5, 2: 4.5}


def test_estimate_does_not_mutate_corpus_activity_hours() -> None:
    """CorpusOrder.activity_hours is a shared dict inside a frozen dataclass
    — estimate() must never mutate it in place."""
    order_with_activities = _corpus_order(
        601, actual_hours=6.0, activity_hours={1: 3.0, 2: 2.0}
    )
    corpus = [
        order_with_activities,
        _corpus_order(602, actual_hours=7.0, activity_hours={1: 4.0}),
        _corpus_order(603, actual_hours=8.0, activity_hours={1: 5.0}),
        _corpus_order(604, actual_hours=9.0, activity_hours={1: 6.0}),
        _corpus_order(605, actual_hours=10.0, activity_hours={1: 7.0}),
    ]
    original_activity_hours = dict(order_with_activities.activity_hours)
    features = EstimateFeatures(
        order_type="ring", finish_type="polished", has_stone_setting=True
    )

    estimate = LaborEstimator().estimate(features, corpus)

    assert order_with_activities.activity_hours == original_activity_hours
    # The returned dict must be a fresh object, not an alias of a corpus dict.
    assert estimate.suggested_activities is not order_with_activities.activity_hours
