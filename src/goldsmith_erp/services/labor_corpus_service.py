# src/goldsmith_erp/services/labor_corpus_service.py
"""
Labor corpus query service — V1.3 estimator, Phase 1, Task 2.

Builds the statistical labor estimator's training corpus: completed orders
paired with their BILLABLE time-entry hours, aggregated in total and per
activity. Read-only — no writes, no migration, no new table. The corpus is
computed live from existing Order / TimeEntry / Activity / Interruption /
Gemstone rows (data volume is small enough that a cache table is not
justified — see the Phase 1 plan's Architecture note).

Consumed by ``LaborEstimator`` (Task 3), which groups ``CorpusOrder`` rows
by similarity tier and computes median/P20/P80 hours.

Design notes
------------
* "Completed" == the same status set ``MLDataService`` already treats as
  finished (``COMPLETED``, ``DELIVERED`` — see
  ``ml_data_service.get_completed_orders_with_entries``).
* Billable-only hours: ``duration_minutes`` is wall-clock elapsed time
  (``end_time - start_time``), NOT already net of interruptions — verified
  by reading ``TimeTrackingService.stop_timer`` / ``switch_timer``, both of
  which compute ``duration = int((now - start_time).total_seconds() / 60)``
  with no interruption subtraction. Interruptions are logged as separate
  rows tagging a pause on the *same* time entry, so this service nets them
  out itself: ``net_minutes = duration_minutes - sum(interruption minutes)``.
  ``MLDataService.auto_calculate_actual_hours`` also nets interruptions out,
  but at the ORDER level across ALL activities (billable + non-billable) to
  populate ``Order.actual_hours`` — that aggregate cannot be reused here,
  where the corpus needs a BILLABLE-only total *and* a per-activity split.
* ``has_stone_setting`` is derived from ``Order.gemstones`` (a Gemstone row
  exists for the order), not from matching an activity name/category. The
  seeded workshop activities do include a stone-setting entry ("Fassen
  (Steine)", category "fabrication"), but ``Activity`` rows are workshop-
  editable free text (``is_custom=True`` is a supported, expected state), so
  matching on activity name is brittle and locale-dependent. Gemstone rows
  are a structural fact tied directly to the order and require no string
  matching, so that is the signal used here.
* Orders without ``order_type`` set are excluded. The estimator's
  similarity tiers (Task 3) all key off ``order_type`` first, and the
  ``CorpusOrder.order_type`` field is a non-optional ``str`` per the Task 2
  interface — an order missing this field carries no usable similarity
  signal and would either violate the type contract or require fabricating
  a placeholder category, so it is dropped from the corpus instead (same
  "nothing to learn from" reasoning as the zero-billable-hours exclusion).
* Soft-deleted orders (``Order.is_deleted``) are excluded — they are not
  live business data and should not shape estimates.
* Single query pass: the corpus query eagerly loads
  ``Order.time_entries -> TimeEntry.activity`` and
  ``Order.time_entries -> TimeEntry.interruptions`` via ``selectinload``, so
  regardless of how many orders/entries match, this executes a constant
  number of queries (the main SELECT plus one batched SELECT per
  ``selectinload`` level) — no N+1.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.models import OrderStatusEnum
from goldsmith_erp.db.models import TimeEntry as TimeEntryModel

logger = logging.getLogger(__name__)

# Orders in these statuses are considered "finished" for corpus purposes —
# mirrors MLDataService.get_completed_orders_with_entries /
# auto_calculate_actual_hours.
_COMPLETED_STATUSES = (OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED)


@dataclass(frozen=True)
class CorpusOrder:
    """One completed order's billable-hours signature for the labor estimator."""

    order_id: int
    order_type: str
    finish_type: str | None
    complexity_rating: int | None
    has_stone_setting: bool
    alloy: str | None
    actual_hours: float  # billable only
    activity_hours: dict[int, float] = field(default_factory=dict)  # activity_id -> h


async def load_corpus(db: AsyncSession) -> list[CorpusOrder]:
    """
    Build the labor corpus: completed/delivered orders x billable TimeEntry x Activity.

    Read-only, no transaction required. Returns one ``CorpusOrder`` per
    qualifying order, sorted by ``order_id`` for deterministic output.
    Excludes: non-completed orders, soft-deleted orders, orders without
    ``order_type`` set, and orders with zero total billable hours (nothing
    for the estimator to learn from).
    """
    result = await db.execute(
        select(OrderModel)
        .where(
            OrderModel.status.in_(_COMPLETED_STATUSES),
            OrderModel.is_deleted.is_(False),
            OrderModel.order_type.isnot(None),
        )
        .options(
            selectinload(OrderModel.time_entries).options(
                selectinload(TimeEntryModel.activity),
                selectinload(TimeEntryModel.interruptions),
            ),
            selectinload(OrderModel.gemstones),
        )
        .order_by(OrderModel.id)
    )
    orders = list(result.scalars().all())

    corpus: list[CorpusOrder] = []
    skipped_zero_hours = 0

    for order in orders:
        activity_hours: dict[int, float] = {}

        for entry in order.time_entries:
            activity = entry.activity
            # Unbillable activities (administration, waiting, ...) don't
            # count toward labor estimation. An entry with no linked
            # activity is a data-integrity gap we skip rather than guess.
            if activity is None or not activity.is_billable:
                continue
            # Only closed entries have a settled duration; a still-running
            # timer has duration_minutes=None and cannot contribute hours.
            if entry.end_time is None or entry.duration_minutes is None:
                continue

            interruption_minutes = sum(
                (interruption.duration_minutes or 0)
                for interruption in entry.interruptions
            )
            net_minutes = max(entry.duration_minutes - interruption_minutes, 0)
            hours = net_minutes / 60.0

            activity_id = cast(int, activity.id)
            activity_hours[activity_id] = activity_hours.get(activity_id, 0.0) + hours

        actual_hours = round(sum(activity_hours.values()), 2)
        if actual_hours <= 0:
            skipped_zero_hours += 1
            continue

        corpus.append(
            CorpusOrder(
                order_id=cast(int, order.id),
                order_type=cast(str, order.order_type),
                finish_type=cast("str | None", order.finish_type),
                complexity_rating=cast("int | None", order.complexity_rating),
                has_stone_setting=len(order.gemstones) > 0,
                alloy=cast("str | None", order.alloy),
                actual_hours=actual_hours,
                activity_hours={
                    activity_id: round(hours, 2)
                    for activity_id, hours in activity_hours.items()
                },
            )
        )

    logger.debug(
        "load_corpus: %d orders in corpus, %d completed orders skipped "
        "(zero billable hours)",
        len(corpus),
        skipped_zero_hours,
    )

    return corpus
