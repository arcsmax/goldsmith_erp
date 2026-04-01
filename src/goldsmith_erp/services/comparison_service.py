# src/goldsmith_erp/services/comparison_service.py
"""
Soll/Ist-Vergleich service — quote vs. actual comparison for goldsmith orders.

Calculates estimation accuracy across hours, material weight, material cost and
final price. Aggregates deviations at workshop level and per goldsmith.

Financial data — per CLAUDE.md all callers must audit-log access.
All DB queries use selectinload() to prevent N+1.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Activity,
    Order as OrderModel,
    OrderStatusEnum,
    TimeEntry,
    User,
)
from goldsmith_erp.models.comparison import (
    SIGNIFICANT_DEVIATION_THRESHOLD,
    ActivityBreakdown,
    ActivityDeviation,
    ComparisonMetric,
    OrderComparison,
    OrderTypeDeviation,
    TrendPoint,
    UserAccuracy,
    WorkshopStats,
)

logger = logging.getLogger(__name__)

# Statuses that represent a finished order with measurable actuals
_FINISHED_STATUSES = {OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _calc_deviation(soll: Optional[float], ist: Optional[float]) -> ComparisonMetric:
    """
    Build a ComparisonMetric from a Soll and Ist value.

    Returns a metric with None deviations when either value is missing or
    the Soll is zero (division by zero guard).
    """
    metric = ComparisonMetric(soll=soll, ist=ist)

    if soll is None or ist is None:
        return metric

    deviation_abs = ist - soll
    metric.deviation_abs = round(deviation_abs, 4)

    if soll != 0.0:
        deviation_pct = (deviation_abs / abs(soll)) * 100.0
        metric.deviation_percent = round(deviation_pct, 2)
        metric.is_significant = abs(deviation_pct) >= SIGNIFICANT_DEVIATION_THRESHOLD

    return metric


def _accuracy_score(metrics: List[ComparisonMetric]) -> Optional[float]:
    """
    Compute a composite accuracy score 0-100 from a list of metrics.

    Score = 100 - mean(|deviation_percent|) clamped to [0, 100].
    Returns None when no deviation data is available.
    """
    deviations = [
        abs(m.deviation_percent)
        for m in metrics
        if m.deviation_percent is not None
    ]
    if not deviations:
        return None
    mean_abs = sum(deviations) / len(deviations)
    return round(max(0.0, 100.0 - mean_abs), 1)


def _deviation_direction(avg_pct: Optional[float]) -> str:
    """Label a deviation percentage as over / under / accurate."""
    if avg_pct is None:
        return "accurate"
    if avg_pct >= SIGNIFICANT_DEVIATION_THRESHOLD:
        return "over"
    if avg_pct <= -SIGNIFICANT_DEVIATION_THRESHOLD:
        return "under"
    return "accurate"


def _trend_direction(trend_points: List[TrendPoint], field: str) -> Optional[str]:
    """
    Compute overall accuracy trend from a list of TrendPoints.

    Compares the average of the first half of the period to the second half.
    Returns 'improving', 'worsening', 'stable', or None if too few data points.

    field must be one of: 'avg_hours_deviation_percent',
    'avg_material_deviation_percent', 'avg_cost_deviation_percent'.
    """
    valid = [p for p in trend_points if getattr(p, field) is not None]
    if len(valid) < 4:  # Need at least 4 periods for a meaningful trend
        return None

    mid = len(valid) // 2
    first_half = [abs(getattr(p, field)) for p in valid[:mid]]
    second_half = [abs(getattr(p, field)) for p in valid[mid:]]

    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)

    diff = avg_second - avg_first
    if abs(diff) < 2.0:  # Less than 2 percentage points change = stable
        return "stable"
    return "worsening" if diff > 0 else "improving"


# ---------------------------------------------------------------------------
# Order-level activity breakdown
# ---------------------------------------------------------------------------


async def _build_activity_breakdown(
    order: OrderModel,
) -> List[ActivityBreakdown]:
    """
    Build per-activity time breakdowns from an order's time_entries.

    Relies on time_entries and their activity relationships already being
    loaded (called after get_order_with_time_entries).
    """
    # Group time entries by activity
    by_activity: Dict[int, List[TimeEntry]] = defaultdict(list)
    for entry in order.time_entries:
        if entry.activity_id:
            by_activity[entry.activity_id].append(entry)

    breakdowns: List[ActivityBreakdown] = []
    for activity_id, entries in by_activity.items():
        activity: Optional[Activity] = entries[0].activity if entries else None
        if not activity:
            continue

        actual_minutes = sum(
            (e.duration_minutes or 0) for e in entries
        )

        # Soll: activity average_duration_minutes (if set) multiplied by entry count
        # Rationale: each time entry represents one work session for this activity.
        # Using the average as the per-session Soll gives a fair comparison.
        estimated_minutes: Optional[float] = None
        deviation_minutes: Optional[float] = None
        deviation_percent: Optional[float] = None
        is_significant = False

        if activity.average_duration_minutes and activity.average_duration_minutes > 0:
            estimated_minutes = activity.average_duration_minutes * len(entries)
            deviation_minutes = actual_minutes - estimated_minutes
            if estimated_minutes != 0:
                deviation_percent = round(
                    (deviation_minutes / abs(estimated_minutes)) * 100.0, 2
                )
                is_significant = abs(deviation_percent) >= SIGNIFICANT_DEVIATION_THRESHOLD

        breakdowns.append(
            ActivityBreakdown(
                activity_id=activity_id,
                activity_name=activity.name,
                activity_category=activity.category,
                actual_minutes=actual_minutes,
                estimated_minutes=estimated_minutes,
                deviation_minutes=round(deviation_minutes, 2) if deviation_minutes is not None else None,
                deviation_percent=deviation_percent,
                is_significant=is_significant,
                entry_count=len(entries),
            )
        )

    # Sort: largest absolute deviation first so the most problematic activities surface first
    breakdowns.sort(
        key=lambda b: abs(b.deviation_minutes or 0),
        reverse=True,
    )
    return breakdowns


# ---------------------------------------------------------------------------
# ComparisonService
# ---------------------------------------------------------------------------


class ComparisonService:
    """
    Soll/Ist-Vergleich business logic.

    All methods are static async and accept AsyncSession as first parameter,
    consistent with the project service layer pattern.
    """

    @staticmethod
    async def get_order_comparison(
        db: AsyncSession,
        order_id: int,
    ) -> Optional[OrderComparison]:
        """
        Soll/Ist-Vergleich fuer einen einzelnen Auftrag.

        Returns None if the order does not exist.
        Logs a warning (not an error) when order has no time entries — the
        comparison is still returned with None deviations for time metrics.

        Financial data — callers must audit-log access.
        """
        result = await db.execute(
            select(OrderModel)
            .options(
                selectinload(OrderModel.time_entries).selectinload(TimeEntry.activity),
                selectinload(OrderModel.material_usage_records),
                selectinload(OrderModel.customer),
            )
            .where(OrderModel.id == order_id)
            .where(OrderModel.is_deleted.is_(False))
        )
        order: Optional[OrderModel] = result.scalar_one_or_none()

        if not order:
            return None

        # -- Hours comparison --
        # Soll: labor_hours (estimated at order intake)
        # Ist:  actual_hours (auto-calculated from time entries on completion)
        hours_metric = _calc_deviation(order.labor_hours, order.actual_hours)

        # -- Material weight comparison --
        weight_metric = _calc_deviation(order.estimated_weight_g, order.actual_weight_g)

        # -- Material cost comparison --
        # Soll: material_cost_calculated (system calculation at order creation)
        # Ist:  sum of cost_at_time from MaterialUsage records (actual spend)
        actual_material_cost: Optional[float] = None
        if order.material_usage_records:
            actual_material_cost = sum(
                r.cost_at_time for r in order.material_usage_records
            )
        elif order.material_cost_override is not None:
            # Fall back to manual override when no usage records exist
            actual_material_cost = order.material_cost_override

        cost_metric = _calc_deviation(order.material_cost_calculated, actual_material_cost)

        # -- Total price comparison --
        # Soll: calculated_price (what the system computed from costs + margin)
        # Ist:  price (the final price charged to the customer)
        price_metric = _calc_deviation(order.calculated_price, order.price)

        # -- Activity breakdown from time entries --
        if not order.time_entries:
            logger.warning(
                "Order has no time entries — activity breakdown will be empty",
                extra={"order_id": order_id},
            )
        activity_breakdown = await _build_activity_breakdown(order)

        # -- Overall accuracy score --
        core_metrics = [hours_metric, weight_metric, cost_metric, price_metric]
        accuracy_score = _accuracy_score(core_metrics)

        has_significant = any(m.is_significant for m in core_metrics) or any(
            b.is_significant for b in activity_breakdown
        )

        return OrderComparison(
            order_id=order.id,
            order_title=order.title,
            order_type=order.order_type,
            status=order.status.value if hasattr(order.status, "value") else order.status,
            completed_at=order.completed_at,
            hours=hours_metric,
            material_weight=weight_metric,
            material_cost=cost_metric,
            total_price=price_metric,
            activity_breakdown=activity_breakdown,
            overall_accuracy_score=accuracy_score,
            has_significant_deviation=has_significant,
        )

    @staticmethod
    async def get_workshop_statistics(
        db: AsyncSession,
        date_from: datetime,
        date_to: datetime,
    ) -> WorkshopStats:
        """
        Aggregated Soll/Ist statistics for all completed orders in the period.

        Only orders with status COMPLETED or DELIVERED are included.
        Orders without actual_hours or actual_weight_g still count towards
        total_completed_orders but contribute None values to averages.

        Financial data — callers must audit-log access.
        """
        result = await db.execute(
            select(OrderModel)
            .options(
                selectinload(OrderModel.time_entries).selectinload(TimeEntry.activity),
                selectinload(OrderModel.material_usage_records),
            )
            .where(
                OrderModel.status.in_(_FINISHED_STATUSES),
                OrderModel.completed_at >= date_from,
                OrderModel.completed_at <= date_to,
                OrderModel.is_deleted.is_(False),
            )
            .order_by(OrderModel.completed_at)
        )
        orders: List[OrderModel] = list(result.scalars().all())

        total = len(orders)

        if total == 0:
            return WorkshopStats(
                date_from=date_from,
                date_to=date_to,
                total_completed_orders=0,
            )

        # Collect per-order deviations
        hours_devs: List[float] = []
        material_devs: List[float] = []
        cost_devs: List[float] = []
        significant_count = 0

        # For breakdown by order_type
        type_hours: Dict[str, List[float]] = defaultdict(list)
        type_material: Dict[str, List[float]] = defaultdict(list)
        type_cost: Dict[str, List[float]] = defaultdict(list)

        # For breakdown by activity
        act_deviations: Dict[str, List[float]] = defaultdict(list)
        act_categories: Dict[str, str] = {}

        # For trend: bucket by ISO week
        trend_buckets: Dict[str, List[OrderModel]] = defaultdict(list)

        for order in orders:
            order_key = order.order_type or "unknown"

            # Actual material cost
            actual_material_cost: Optional[float] = None
            if order.material_usage_records:
                actual_material_cost = sum(r.cost_at_time for r in order.material_usage_records)
            elif order.material_cost_override is not None:
                actual_material_cost = order.material_cost_override

            h_metric = _calc_deviation(order.labor_hours, order.actual_hours)
            m_metric = _calc_deviation(order.estimated_weight_g, order.actual_weight_g)
            c_metric = _calc_deviation(order.material_cost_calculated, actual_material_cost)

            if h_metric.deviation_percent is not None:
                hours_devs.append(h_metric.deviation_percent)
                type_hours[order_key].append(h_metric.deviation_percent)
            if m_metric.deviation_percent is not None:
                material_devs.append(m_metric.deviation_percent)
                type_material[order_key].append(m_metric.deviation_percent)
            if c_metric.deviation_percent is not None:
                cost_devs.append(c_metric.deviation_percent)
                type_cost[order_key].append(c_metric.deviation_percent)

            if any(m.is_significant for m in [h_metric, m_metric, c_metric]):
                significant_count += 1

            # Activity-level deviations
            act_breakdown = await _build_activity_breakdown(order)
            for ab in act_breakdown:
                if ab.deviation_percent is not None:
                    act_deviations[ab.activity_name].append(ab.deviation_percent)
                    act_categories[ab.activity_name] = ab.activity_category

            # Trend bucket
            if order.completed_at:
                iso = order.completed_at.isocalendar()
                bucket_key = f"{iso[0]}-KW{iso[1]:02d}"
                trend_buckets[bucket_key].append(order)

        # Aggregate averages
        def _avg(vals: List[float]) -> Optional[float]:
            return round(sum(vals) / len(vals), 2) if vals else None

        avg_hours = _avg(hours_devs)
        avg_material = _avg(material_devs)
        avg_cost = _avg(cost_devs)

        sig_pct = round(significant_count / total * 100, 1) if total else None

        # Build order-type deviation objects
        def _build_type_deviations(
            types: List[str],
        ) -> List[OrderTypeDeviation]:
            out = []
            for t in types:
                h_avg = _avg(type_hours.get(t, []))
                m_avg = _avg(type_material.get(t, []))
                c_avg = _avg(type_cost.get(t, []))
                count = max(
                    len(type_hours.get(t, [])),
                    len(type_material.get(t, [])),
                    len(type_cost.get(t, [])),
                )
                # Direction driven by hours (primary metric)
                direction = _deviation_direction(h_avg)
                out.append(
                    OrderTypeDeviation(
                        order_type=t,
                        order_count=count,
                        avg_hours_deviation_percent=h_avg,
                        avg_material_deviation_percent=m_avg,
                        avg_cost_deviation_percent=c_avg,
                        direction=direction,
                    )
                )
            return out

        all_types = list(set(type_hours) | set(type_material) | set(type_cost))
        all_type_devs = _build_type_deviations(all_types)
        # Sort: most under-estimated (highest positive avg hours deviation) first
        under_types = sorted(
            [t for t in all_type_devs if t.direction == "over"],
            key=lambda t: (t.avg_hours_deviation_percent or 0),
            reverse=True,
        )[:5]
        over_types = sorted(
            [t for t in all_type_devs if t.direction == "under"],
            key=lambda t: (t.avg_hours_deviation_percent or 0),
        )[:5]

        # Build activity deviation objects
        def _build_act_deviations(
            names: List[str],
        ) -> List[ActivityDeviation]:
            out = []
            for name in names:
                devs = act_deviations[name]
                avg_d = _avg(devs)
                direction = _deviation_direction(avg_d)
                out.append(
                    ActivityDeviation(
                        activity_name=name,
                        activity_category=act_categories.get(name, ""),
                        order_count=len(devs),
                        avg_deviation_percent=avg_d,
                        avg_deviation_minutes=None,  # Not aggregated at this level
                        direction=direction,
                    )
                )
            return out

        all_act_names = list(act_deviations.keys())
        all_act_devs = _build_act_deviations(all_act_names)
        under_acts = sorted(
            [a for a in all_act_devs if a.direction == "over"],
            key=lambda a: (a.avg_deviation_percent or 0),
            reverse=True,
        )[:5]
        over_acts = sorted(
            [a for a in all_act_devs if a.direction == "under"],
            key=lambda a: (a.avg_deviation_percent or 0),
        )[:5]

        # Build trend
        trend_points: List[TrendPoint] = []
        for bucket_key in sorted(trend_buckets.keys()):
            bucket_orders = trend_buckets[bucket_key]
            b_hours = [
                _calc_deviation(o.labor_hours, o.actual_hours).deviation_percent
                for o in bucket_orders
            ]
            b_material = [
                _calc_deviation(o.estimated_weight_g, o.actual_weight_g).deviation_percent
                for o in bucket_orders
            ]

            # Actual cost per bucket order
            b_cost_devs: List[Optional[float]] = []
            for o in bucket_orders:
                ac: Optional[float] = None
                if o.material_usage_records:
                    ac = sum(r.cost_at_time for r in o.material_usage_records)
                elif o.material_cost_override is not None:
                    ac = o.material_cost_override
                b_cost_devs.append(
                    _calc_deviation(o.material_cost_calculated, ac).deviation_percent
                )

            # Period start = earliest completed_at in bucket
            period_start = min(
                (o.completed_at for o in bucket_orders if o.completed_at),
                default=date_from,
            )

            trend_points.append(
                TrendPoint(
                    period_label=bucket_key,
                    period_start=period_start,
                    order_count=len(bucket_orders),
                    avg_hours_deviation_percent=_avg([v for v in b_hours if v is not None]),
                    avg_material_deviation_percent=_avg([v for v in b_material if v is not None]),
                    avg_cost_deviation_percent=_avg([v for v in b_cost_devs if v is not None]),
                )
            )

        overall_trend = _trend_direction(trend_points, "avg_hours_deviation_percent")

        return WorkshopStats(
            date_from=date_from,
            date_to=date_to,
            total_completed_orders=total,
            avg_hours_deviation_percent=avg_hours,
            avg_material_deviation_percent=avg_material,
            avg_cost_deviation_percent=avg_cost,
            significant_deviation_count=significant_count,
            significant_deviation_percent=sig_pct,
            most_underestimated_order_types=under_types,
            most_overestimated_order_types=over_types,
            most_underestimated_activities=under_acts,
            most_overestimated_activities=over_acts,
            trend=trend_points,
            trend_direction=overall_trend,
        )

    @staticmethod
    async def get_goldsmith_accuracy(
        db: AsyncSession,
        user_id: int,
        workshop_stats: Optional[WorkshopStats] = None,
    ) -> Optional[UserAccuracy]:
        """
        Per-goldsmith Soll/Ist accuracy.

        Fetches all completed orders where the user has time entries,
        calculates their personal deviation averages, and compares them to the
        workshop averages from workshop_stats (if provided).

        Returns None if no completed orders found for this user.
        Financial data — callers must audit-log access.
        """
        # Resolve user display name
        user_result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user: Optional[User] = user_result.scalar_one_or_none()
        if not user:
            return None

        # Display name: first name + last name initial (privacy-conscious)
        user_name = f"{user.first_name} {user.last_name[0]}." if user.last_name else user.first_name

        # Find all orders with time entries by this user that are completed
        te_result = await db.execute(
            select(TimeEntry.order_id)
            .where(TimeEntry.user_id == user_id)
            .distinct()
        )
        order_ids = [row[0] for row in te_result.fetchall()]

        if not order_ids:
            return UserAccuracy(
                user_id=user_id,
                user_name=user_name,
                total_orders=0,
            )

        orders_result = await db.execute(
            select(OrderModel)
            .options(
                selectinload(OrderModel.time_entries).selectinload(TimeEntry.activity),
                selectinload(OrderModel.material_usage_records),
            )
            .where(
                OrderModel.id.in_(order_ids),
                OrderModel.status.in_(_FINISHED_STATUSES),
                OrderModel.is_deleted.is_(False),
            )
            .order_by(OrderModel.completed_at)
        )
        orders: List[OrderModel] = list(orders_result.scalars().all())

        if not orders:
            return UserAccuracy(
                user_id=user_id,
                user_name=user_name,
                total_orders=0,
            )

        # Deviation tracking
        hours_devs: List[float] = []
        material_devs: List[float] = []

        type_hours: Dict[str, List[float]] = defaultdict(list)
        type_material: Dict[str, List[float]] = defaultdict(list)

        date_from = orders[0].completed_at
        date_to = orders[-1].completed_at

        for order in orders:
            h_metric = _calc_deviation(order.labor_hours, order.actual_hours)
            m_metric = _calc_deviation(order.estimated_weight_g, order.actual_weight_g)

            order_key = order.order_type or "unknown"

            if h_metric.deviation_percent is not None:
                hours_devs.append(h_metric.deviation_percent)
                type_hours[order_key].append(h_metric.deviation_percent)
            if m_metric.deviation_percent is not None:
                material_devs.append(m_metric.deviation_percent)
                type_material[order_key].append(m_metric.deviation_percent)

        def _avg(vals: List[float]) -> Optional[float]:
            return round(sum(vals) / len(vals), 2) if vals else None

        user_hours_avg = _avg(hours_devs)
        user_material_avg = _avg(material_devs)

        # Comparison to workshop average
        hours_vs_ws: Optional[float] = None
        material_vs_ws: Optional[float] = None
        if workshop_stats:
            if user_hours_avg is not None and workshop_stats.avg_hours_deviation_percent is not None:
                hours_vs_ws = round(user_hours_avg - workshop_stats.avg_hours_deviation_percent, 2)
            if user_material_avg is not None and workshop_stats.avg_material_deviation_percent is not None:
                material_vs_ws = round(user_material_avg - workshop_stats.avg_material_deviation_percent, 2)

        # Build order type breakdowns
        def _build_user_type_devs(order_type: str) -> OrderTypeDeviation:
            h_avg = _avg(type_hours.get(order_type, []))
            m_avg = _avg(type_material.get(order_type, []))
            count = max(
                len(type_hours.get(order_type, [])),
                len(type_material.get(order_type, [])),
            )
            return OrderTypeDeviation(
                order_type=order_type,
                order_count=count,
                avg_hours_deviation_percent=h_avg,
                avg_material_deviation_percent=m_avg,
                direction=_deviation_direction(h_avg),
            )

        all_types = list(set(type_hours) | set(type_material))
        all_type_devs = [_build_user_type_devs(t) for t in all_types]

        # Best = smallest absolute average deviation
        best_types = sorted(
            all_type_devs,
            key=lambda t: abs(t.avg_hours_deviation_percent or 0),
        )[:3]
        worst_types = sorted(
            all_type_devs,
            key=lambda t: abs(t.avg_hours_deviation_percent or 0),
            reverse=True,
        )[:3]

        # Simple trend: compare first half vs second half of orders (chronological)
        improvement_trend: Optional[str] = None
        if len(orders) >= 4:
            mid = len(orders) // 2
            first_devs = [
                _calc_deviation(o.labor_hours, o.actual_hours).deviation_percent
                for o in orders[:mid]
            ]
            second_devs = [
                _calc_deviation(o.labor_hours, o.actual_hours).deviation_percent
                for o in orders[mid:]
            ]
            f_avg = _avg([v for v in first_devs if v is not None])
            s_avg = _avg([v for v in second_devs if v is not None])
            if f_avg is not None and s_avg is not None:
                diff = abs(s_avg) - abs(f_avg)
                if abs(diff) < 2.0:
                    improvement_trend = "stable"
                else:
                    improvement_trend = "worsening" if diff > 0 else "improving"

        return UserAccuracy(
            user_id=user_id,
            user_name=user_name,
            total_orders=len(orders),
            date_from=date_from,
            date_to=date_to,
            avg_hours_deviation_percent=user_hours_avg,
            avg_material_deviation_percent=user_material_avg,
            hours_vs_workshop_avg=hours_vs_ws,
            material_vs_workshop_avg=material_vs_ws,
            best_order_types=best_types,
            worst_order_types=worst_types,
            improvement_trend=improvement_trend,
        )
