# src/goldsmith_erp/services/estimate_accuracy_service.py
"""
Estimate accuracy / calibration service — V1.3 estimator, Phase 1, Task 4.

Persists estimate-vs-actual rows for the statistical labor estimator's
learning loop and computes calibration stats (rolling MAPE + per-order-type
bias) from them. This is the feedback half of the loop — it does not know
or care HOW an estimate was produced (`LaborEstimator`, Task 3) or WHERE a
prior estimate is stored on an order/quote (Task 5's job); it only persists
whatever estimated/actual values a caller supplies and reads them back.

Design notes
------------
* `record()` is a self-contained unit of work (opens its own
  `transactional()` block and commits) so it can be called either directly
  (as a top-level service call) or from `safe_record_on_completion` without
  either caller needing to manage a transaction around it.
* `calibration()` reads the most recent `limit` rows (optionally filtered
  to one `order_type`, joined through `Order` since `EstimateAccuracy`
  itself carries no `order_type` column — that would duplicate data already
  on the order and go stale if an order's type were ever corrected) and
  computes:
    - MAPE (mean absolute percentage error) of estimated_hours vs
      actual_hours. Rows with `actual_hours == 0` are excluded from MAPE
      (dividing by zero actual hours is undefined, not "0% error") —
      `CalibrationResult.rows_excluded_zero_actual` reports how many.
    - Per-order-type bias: mean SIGNED error (estimated_hours -
      actual_hours) grouped by order type. Positive = the estimator
      over-estimates that order type on average; negative = under-
      estimates. Bias is a plain difference (no division), so zero-actual
      rows ARE included here — only MAPE excludes them.
* `safe_record_on_completion()` is the defensive, fire-and-forget wrapper
  wired into `OrderService.update_order`'s completion hook (see that
  file). It mirrors `CostWatchService.safe_check`: never raises, so a bug
  here can never break order completion. It is a documented NO-OP today —
  see its docstring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import EstimateAccuracy
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.transaction import transactional

logger = logging.getLogger(__name__)

# Bucket key for EstimateAccuracy rows whose linked Order.order_type is
# NULL. Order.order_type is nullable on the ORM, so a real (if rare)
# completed order can still lack it; bucketing under a string key (rather
# than a `None` dict key) keeps `CalibrationResult.bias_by_order_type`
# uniformly `dict[str, float]`.
UNKNOWN_ORDER_TYPE = "unknown"


@dataclass(frozen=True)
class CalibrationResult:
    """Rolling calibration snapshot over the most recent EstimateAccuracy rows.

    See module docstring for the MAPE / bias formulas and the zero-actual
    exclusion rule.
    """

    rows_loaded: int
    rows_considered_for_mape: int
    rows_excluded_zero_actual: int
    mape: Optional[float]
    bias_by_order_type: dict[str, float] = field(default_factory=dict)


async def record(
    db: AsyncSession,
    order: OrderModel,
    *,
    estimated_hours: float,
    actual_hours: float,
    estimated_total: float,
    actual_total: float,
    estimator_version: str,
) -> EstimateAccuracy:
    """Persist one estimate-vs-actual row for the calibration feedback loop.

    Self-contained unit of work: opens its own `transactional()` block and
    commits. Callers with an in-flight transaction of their own should call
    this via `safe_record_on_completion` (post-commit) rather than nesting
    it inside their own `transactional()` block.

    Idempotent per `order_id` (Task-4 review carry-forward, ahead of V1.3
    Task 5 wiring real values through): if an `EstimateAccuracy` row
    already exists for this `order.id`, that existing row is returned
    unchanged and NO new row is written. This guards against an order
    that is completed, reopened, and completed again from double-counting
    into `calibration()` — without this guard a reopen->recomplete cycle
    would silently skew MAPE/bias with a duplicate observation of the
    same job. This is a plain check-then-insert (not a DB-level unique
    constraint) — acceptable here because the only caller is the single,
    sequential `OrderService.update_order` completion hook, not a
    high-concurrency write path.
    """
    existing = (
        await db.execute(
            select(EstimateAccuracy).where(EstimateAccuracy.order_id == order.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        logger.info(
            "EstimateAccuracyService.record: order %s already has an "
            "accuracy row (id=%s) — skipping duplicate write",
            order.id,
            existing.id,
            extra={"order_id": order.id, "existing_accuracy_id": existing.id},
        )
        return existing

    accuracy = EstimateAccuracy(
        order_id=order.id,
        estimated_hours=estimated_hours,
        actual_hours=actual_hours,
        estimated_total=estimated_total,
        actual_total=actual_total,
        estimator_version=estimator_version,
    )
    async with transactional(db):
        db.add(accuracy)
        await db.flush()
    await db.refresh(accuracy)
    return accuracy


async def calibration(
    db: AsyncSession,
    *,
    order_type: Optional[str] = None,
    limit: int = 100,
) -> CalibrationResult:
    """Compute rolling MAPE + per-order-type bias over the last `limit` rows.

    `order_type`, when given, restricts the window to accuracy rows whose
    linked order has that `order_type` — both the MAPE and the (then
    single-key) bias breakdown are scoped to it. `limit` bounds the window
    to the most recently created rows (newest-first), so calibration
    reflects recent estimator performance rather than the entire history.

    Read-only, no transaction required. Never raises for empty history —
    returns a `CalibrationResult` with `mape=None` and an empty
    `bias_by_order_type` when there are zero matching rows.
    """
    stmt = (
        select(EstimateAccuracy, OrderModel.order_type)
        .join(OrderModel, EstimateAccuracy.order_id == OrderModel.id)
        .order_by(EstimateAccuracy.created_at.desc(), EstimateAccuracy.id.desc())
    )
    if order_type is not None:
        stmt = stmt.where(OrderModel.order_type == order_type)
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    percentage_errors: list[float] = []
    excluded_zero_actual = 0
    signed_errors_by_type: dict[str, list[float]] = {}

    for accuracy, row_order_type in rows:
        type_key = row_order_type or UNKNOWN_ORDER_TYPE
        signed_errors_by_type.setdefault(type_key, []).append(
            accuracy.estimated_hours - accuracy.actual_hours
        )

        if accuracy.actual_hours == 0:
            excluded_zero_actual += 1
            continue
        percentage_errors.append(
            abs(accuracy.actual_hours - accuracy.estimated_hours)
            / accuracy.actual_hours
        )

    mape = (
        sum(percentage_errors) / len(percentage_errors) if percentage_errors else None
    )
    bias_by_order_type = {
        type_key: sum(errors) / len(errors)
        for type_key, errors in signed_errors_by_type.items()
    }

    return CalibrationResult(
        rows_loaded=len(rows),
        rows_considered_for_mape=len(percentage_errors),
        rows_excluded_zero_actual=excluded_zero_actual,
        mape=mape,
        bias_by_order_type=bias_by_order_type,
    )


async def safe_record_on_completion(
    db: AsyncSession,
    order: OrderModel,
    *,
    estimated_hours: Optional[float] = None,
    actual_hours: Optional[float] = None,
    estimated_total: Optional[float] = None,
    actual_total: Optional[float] = None,
    estimator_version: Optional[str] = None,
) -> None:
    """Defensive, fire-and-forget hook for order completion.

    Wired into `OrderService.update_order`, called AFTER that method's
    `transactional()` block has already committed the status change (same
    post-commit placement as `CostWatchService.safe_check` in
    `TimeTrackingService.stop_time_entry`) — a failure in here must never
    unwind or appear to unwind an already-committed order completion, and
    never raises, mirroring that precedent exactly.

    NO-OP whenever any estimate value is `None`, which is EVERY call site
    today: `Order` has no stored-estimate column yet (V1.3 Task 5 —
    `EstimatorService` — owns adding that storage and looking up a prior
    estimate). Wiring this hook now, ahead of Task 5, means Task 5 only
    has to change its call site to pass real values through; no new hook
    or call site is needed later. `estimated_hours`/`actual_hours`/
    `estimated_total`/`actual_total`/`estimator_version` are ALL required
    together — a partial estimate is not meaningful to record.
    """
    if (
        estimated_hours is None
        or actual_hours is None
        or estimated_total is None
        or actual_total is None
        or estimator_version is None
    ):
        return
    try:
        await record(
            db,
            order,
            estimated_hours=estimated_hours,
            actual_hours=actual_hours,
            estimated_total=estimated_total,
            actual_total=actual_total,
            estimator_version=estimator_version,
        )
    except Exception:
        # record() already rolls back internally (transactional()) on
        # failure — this is a belt-and-suspenders outer guard, identical
        # in spirit to CostWatchService.safe_check, so a bug in record()
        # itself can never propagate into OrderService.update_order.
        logger.error(
            "EstimateAccuracyService.safe_record_on_completion failed " "unexpectedly",
            extra={"order_id": order.id},
            exc_info=True,
        )
