"""Unit tests for the retention sweep — pure logic + rule configuration.

Covers the date maths (year-end anchoring vs rolling window), the
retention-class map (which tables are swept, which excluded), and the
exit-code contract. DB-backed boundary tests live in
``tests/integration/test_retention_sweep.py``.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from goldsmith_erp.db.models import MaterialUsage, Order, ScanLog, TimeEntry
from goldsmith_erp.jobs.retention_sweep import (
    RETENTION_RULES,
    RetentionRule,
    RetentionSweepReport,
    TableResult,
    _report_exit_code,
    _subtract_months,
)

# ---------------------------------------------------------------------------
# _subtract_months
# ---------------------------------------------------------------------------


def test_subtract_months_simple():
    assert _subtract_months(datetime(2026, 7, 26), 24) == datetime(2024, 7, 26)


def test_subtract_months_crosses_year():
    assert _subtract_months(datetime(2026, 1, 15), 2) == datetime(2025, 11, 15)


def test_subtract_months_clamps_day_end_of_month():
    # 31 Mar − 1 month must clamp to the last day of February, not crash.
    assert _subtract_months(datetime(2027, 3, 31), 1) == datetime(2027, 2, 28)


# ---------------------------------------------------------------------------
# RetentionRule.cutoff
# ---------------------------------------------------------------------------


def test_financial_year_end_cutoff_is_jan_1_of_year_minus_n():
    rule = RetentionRule(
        label="t",
        model=TimeEntry,
        retention_class="financial_10y",
        anchor_attr="created_at",
        pk_attr="id",
        legal_basis="x",
        period_human="y",
        financial_year_end_years=10,
    )
    # now = mid-2026 → cutoff is 2016-01-01; only 2015-or-earlier rows expire.
    assert rule.cutoff(datetime(2026, 6, 15)) == datetime(2016, 1, 1)


def test_financial_year_end_is_conservative_across_the_boundary():
    rule = next(r for r in RETENTION_RULES if r.retention_class == "financial_10y")
    now = datetime(2026, 6, 15)
    cutoff = rule.cutoff(now)
    # A record from mid-2016 is still inside its statutory window (retained
    # through 2026-12-31) → NOT before the cutoff.
    assert not (datetime(2016, 6, 1) < cutoff)
    # A record from 2015 is fully past its 10-year window → before the cutoff.
    assert datetime(2015, 6, 1) < cutoff


def test_rolling_month_cutoff():
    rule = next(r for r in RETENTION_RULES if r.retention_class == "standard_24m")
    assert rule.cutoff(datetime(2026, 7, 26)) == datetime(2024, 7, 26)


# ---------------------------------------------------------------------------
# RETENTION_RULES map — which tables are swept, which are excluded
# ---------------------------------------------------------------------------


def test_rules_cover_exactly_the_three_swept_tables():
    labels = {r.label for r in RETENTION_RULES}
    assert labels == {"scan_logs", "time_entries", "material_usage"}


def test_orders_are_never_swept():
    # Orders (indefinite_business / hallmark_10y) are excluded + flagged.
    assert all(r.model is not Order for r in RETENTION_RULES)


@pytest.mark.parametrize(
    "label,model,retention_class,anchor",
    [
        ("scan_logs", ScanLog, "standard_24m", "scanned_at"),
        ("time_entries", TimeEntry, "financial_10y", "created_at"),
        ("material_usage", MaterialUsage, "financial_10y", "used_at"),
    ],
)
def test_rule_wiring(label, model, retention_class, anchor):
    rule = next(r for r in RETENTION_RULES if r.label == label)
    assert rule.model is model
    assert rule.retention_class == retention_class
    assert rule.anchor_attr == anchor
    # The anchor + pk attributes must actually exist on the model.
    assert hasattr(model, rule.anchor_attr)
    assert hasattr(model, rule.pk_attr)


def test_each_rule_has_exactly_one_anchoring_strategy():
    for rule in RETENTION_RULES:
        has_year_end = rule.financial_year_end_years is not None
        has_rolling = rule.rolling_months is not None
        assert has_year_end != has_rolling, rule.label


# ---------------------------------------------------------------------------
# _report_exit_code contract
# ---------------------------------------------------------------------------


def _report(*, executed: bool, results: list[TableResult]) -> RetentionSweepReport:
    return RetentionSweepReport(
        executed=executed, now=datetime(2026, 7, 26), results=results
    )


def test_dry_run_with_candidates_exits_zero():
    report = _report(
        executed=False,
        results=[TableResult("scan_logs", "standard_24m", candidates=5)],
    )
    assert report.total_candidates == 5
    assert not report.has_failures
    assert _report_exit_code(report) == 0


def test_execute_without_failures_exits_zero():
    report = _report(
        executed=True,
        results=[TableResult("scan_logs", "standard_24m", candidates=5, deleted=5)],
    )
    assert report.total_deleted == 5
    assert _report_exit_code(report) == 0


def test_any_failure_exits_one():
    report = _report(
        executed=True,
        results=[
            TableResult("scan_logs", "standard_24m", candidates=5, deleted=5),
            TableResult("time_entries", "financial_10y", error="OperationalError"),
        ],
    )
    assert report.has_failures
    assert [r.label for r in report.failures] == ["time_entries"]
    assert _report_exit_code(report) == 1
