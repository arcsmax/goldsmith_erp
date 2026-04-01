# src/goldsmith_erp/services/ml_data_service.py
"""
ML Data Service — data quality monitoring and training-data retrieval.

Responsibilities:
1. Report how much clean, feature-complete data exists for ML training.
2. Retrieve completed orders (with time entries) as the raw training corpus.
3. Auto-calculate actual_hours from time entries when an order completes.
4. Validate whether a single time entry carries the fields ML models need.

All methods are static async, accepting AsyncSession as first parameter per
project conventions.  All queries use selectinload() to prevent N+1 queries.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Interruption as InterruptionModel,
    Order as OrderModel,
    OrderStatusEnum,
    TimeEntry as TimeEntryModel,
)
from goldsmith_erp.models.ml_data import (
    DataQualityReport,
    FieldCompleteness,
    MLReadinessStatus,
)

logger = logging.getLogger(__name__)

# Minimum number of feature-complete completed orders required before training.
MINIMUM_ORDERS_FOR_TRAINING = 100

# Order-level columns that the ML pipeline requires to be non-null.
# Format: (column_attr_name, display_name, is_required_for_ml)
_ORDER_ML_FIELDS: list[tuple[str, str, bool]] = [
    ("order_type", "Auftragstyp (ring, chain, …)", True),
    ("complexity_rating", "Komplexit\u00e4t (1-5 Sterne)", True),
    ("metal_type", "Metallsorte", True),
    ("finish_type", "Oberfl\u00e4chenfinish", False),
    ("estimated_weight_g", "Gesch\u00e4tztes Gewicht (g)", False),
    ("actual_weight_g", "Tats\u00e4chliches Gewicht (g)", False),
    ("actual_hours", "Tats\u00e4chliche Stunden (auto)", True),
    ("deadline", "Abgabetermin", False),
]

# Subset that must ALL be non-null for an order to count as "feature-complete".
_REQUIRED_FIELD_NAMES: frozenset[str] = frozenset(
    name for name, _, required in _ORDER_ML_FIELDS if required
)


class MLDataService:
    """Service for ML data pipeline — quality monitoring and training-data access."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    async def get_training_data_quality(db: AsyncSession) -> DataQualityReport:
        """
        Return a full data quality report for the ML training dashboard.

        Queries:
        - Count of completed/delivered orders.
        - How many of those have at least one closed time entry.
        - Per-field completeness across those qualifying orders.
        - Time-entry-level completeness (ratings, activity linkage).
        - Composite readiness score and verdict.

        This method is read-only and safe to call frequently.
        """
        completed_statuses = [OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED]

        # --- 1. Total completed orders ---
        total_completed_result = await db.execute(
            select(func.count(OrderModel.id)).where(
                OrderModel.status.in_(completed_statuses)
            )
        )
        total_completed = total_completed_result.scalar() or 0

        # --- 2. Completed orders that have at least one closed time entry ---
        # A subquery of order_ids that have closed entries
        orders_with_entries_subq = (
            select(TimeEntryModel.order_id)
            .where(TimeEntryModel.end_time.isnot(None))
            .distinct()
            .subquery()
        )
        orders_with_entries_result = await db.execute(
            select(func.count(OrderModel.id)).where(
                and_(
                    OrderModel.status.in_(completed_statuses),
                    OrderModel.id.in_(select(orders_with_entries_subq.c.order_id)),
                )
            )
        )
        orders_with_entries = orders_with_entries_result.scalar() or 0

        # --- 3. Load qualifying orders for per-field completeness ---
        qualifying_orders_result = await db.execute(
            select(OrderModel).where(
                and_(
                    OrderModel.status.in_(completed_statuses),
                    OrderModel.id.in_(select(orders_with_entries_subq.c.order_id)),
                )
            )
        )
        qualifying_orders: list[OrderModel] = list(qualifying_orders_result.scalars().all())
        n_qualifying = len(qualifying_orders)

        # --- 4. Per-field completeness ---
        field_completeness_list: list[FieldCompleteness] = []
        fully_complete_count = 0
        required_field_names = list(_REQUIRED_FIELD_NAMES)

        for field_name, display_name, is_required in _ORDER_ML_FIELDS:
            filled = sum(
                1 for o in qualifying_orders
                if getattr(o, field_name, None) is not None
            )
            pct = (filled / n_qualifying * 100.0) if n_qualifying else 0.0
            field_completeness_list.append(
                FieldCompleteness(
                    field_name=field_name,
                    display_name=display_name,
                    total_orders=n_qualifying,
                    filled_count=filled,
                    completeness_pct=round(pct, 1),
                    is_required_for_ml=is_required,
                )
            )

        # Count orders where ALL required fields are non-null
        for order in qualifying_orders:
            if all(
                getattr(order, fname, None) is not None
                for fname in required_field_names
            ):
                fully_complete_count += 1

        # --- 5. Time-entry level metrics ---
        # COUNT(col) skips NULLs — no need for CAST tricks.
        te_stats_result = await db.execute(
            select(
                func.count(TimeEntryModel.id).label("total_entries"),
                func.count(TimeEntryModel.complexity_rating).label("with_complexity"),
                func.count(TimeEntryModel.quality_rating).label("with_quality"),
                func.count(TimeEntryModel.activity_id).label("with_activity"),
            ).where(
                and_(
                    TimeEntryModel.end_time.isnot(None),
                    TimeEntryModel.order_id.in_(
                        select(orders_with_entries_subq.c.order_id)
                    ),
                )
            )
        )
        te_row = te_stats_result.first()

        # SQLAlchemy aggregate sums over booleans may return None when count is 0
        total_entries: int = te_row.total_entries or 0
        entries_with_complexity: int = te_row.with_complexity or 0
        entries_with_quality: int = te_row.with_quality or 0
        entries_with_activity: int = te_row.with_activity or 0

        def _pct(part: int, total: int) -> float:
            return round(part / total * 100.0, 1) if total else 0.0

        avg_entries = round(total_entries / orders_with_entries, 2) if orders_with_entries else 0.0

        # --- 6. Composite readiness score ---
        #
        # Score formula (0-100):
        #   40 pts — quantity: min(orders_with_all_features / 100, 1.0) * 40
        #   40 pts — required field completeness: mean completeness of required fields
        #   20 pts — time-entry quality: mean of complexity + quality completeness
        #
        required_pcts = [
            fc.completeness_pct
            for fc in field_completeness_list
            if fc.is_required_for_ml
        ]
        avg_required_completeness = (
            sum(required_pcts) / len(required_pcts) if required_pcts else 0.0
        )
        te_quality_score = _pct(
            entries_with_complexity + entries_with_quality,
            total_entries * 2 if total_entries else 1,
        )

        quantity_pts = min(fully_complete_count / MINIMUM_ORDERS_FOR_TRAINING, 1.0) * 40.0
        completeness_pts = avg_required_completeness * 0.40
        te_quality_pts = te_quality_score * 0.20

        data_readiness_score = round(quantity_pts + completeness_pts + te_quality_pts, 1)

        # --- 7. Readiness verdict and actionable message ---
        ready = (
            data_readiness_score >= 80.0
            and fully_complete_count >= MINIMUM_ORDERS_FOR_TRAINING
        )

        actionable_message = MLDataService._build_actionable_message(
            ready=ready,
            fully_complete_count=fully_complete_count,
            field_completeness_list=field_completeness_list,
            data_readiness_score=data_readiness_score,
        )

        readiness = MLReadinessStatus(
            ready=ready,
            data_readiness_score=data_readiness_score,
            orders_with_all_features=fully_complete_count,
            minimum_orders_for_training=MINIMUM_ORDERS_FOR_TRAINING,
            actionable_message=actionable_message,
        )

        return DataQualityReport(
            total_completed_orders=total_completed,
            orders_with_time_entries=orders_with_entries,
            orders_with_all_features=fully_complete_count,
            time_entries_count=total_entries,
            avg_entries_per_order=avg_entries,
            entries_with_complexity_rating_pct=_pct(entries_with_complexity, total_entries),
            entries_with_quality_rating_pct=_pct(entries_with_quality, total_entries),
            entries_with_activity_pct=_pct(entries_with_activity, total_entries),
            field_completeness=field_completeness_list,
            readiness=readiness,
        )

    @staticmethod
    async def get_completed_orders_with_entries(
        db: AsyncSession, min_entries: int = 1
    ) -> List[OrderModel]:
        """
        Return completed orders that have at least `min_entries` closed time entries.

        All relationships are eagerly loaded so callers can access
        order.time_entries[i].activity, .interruptions, etc. without
        additional queries.

        Used by the feature engineering service to build the training dataset.
        """
        # Subquery: order_ids with at least min_entries closed time entries
        entry_counts_subq = (
            select(
                TimeEntryModel.order_id,
                func.count(TimeEntryModel.id).label("entry_count"),
            )
            .where(TimeEntryModel.end_time.isnot(None))
            .group_by(TimeEntryModel.order_id)
            .having(func.count(TimeEntryModel.id) >= min_entries)
            .subquery()
        )

        result = await db.execute(
            select(OrderModel)
            .where(
                and_(
                    OrderModel.status.in_(
                        [OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED]
                    ),
                    OrderModel.id.in_(
                        select(entry_counts_subq.c.order_id)
                    ),
                )
            )
            .options(
                selectinload(OrderModel.time_entries).options(
                    selectinload(TimeEntryModel.activity),
                    selectinload(TimeEntryModel.interruptions),
                    selectinload(TimeEntryModel.user),
                ),
                selectinload(OrderModel.gemstones),
                selectinload(OrderModel.materials),
                selectinload(OrderModel.customer),
            )
            .order_by(OrderModel.completed_at.desc().nullslast())
        )
        return list(result.scalars().all())

    @staticmethod
    async def auto_calculate_actual_hours(
        db: AsyncSession, order_id: int
    ) -> Optional[float]:
        """
        Sum all closed time entry durations for an order, subtract interruptions,
        convert to hours, and store the result in order.actual_hours.

        Returns the calculated value, or None if the order has no closed entries.

        This is called automatically from OrderService when status transitions to
        COMPLETED or DELIVERED.  It is idempotent — safe to call multiple times.
        """
        # Sum closed time entry durations for this order
        duration_result = await db.execute(
            select(func.sum(TimeEntryModel.duration_minutes)).where(
                and_(
                    TimeEntryModel.order_id == order_id,
                    TimeEntryModel.end_time.isnot(None),
                    TimeEntryModel.duration_minutes.isnot(None),
                )
            )
        )
        total_entry_minutes: int = duration_result.scalar() or 0

        if total_entry_minutes == 0:
            logger.info(
                "auto_calculate_actual_hours: order_id=%d has no closed time entries, "
                "skipping actual_hours update",
                order_id,
            )
            return None

        # Sum interruption durations across all time entries for this order
        interruption_result = await db.execute(
            select(func.sum(InterruptionModel.duration_minutes)).join(
                TimeEntryModel,
                InterruptionModel.time_entry_id == TimeEntryModel.id,
            ).where(TimeEntryModel.order_id == order_id)
        )
        total_interruption_minutes: int = interruption_result.scalar() or 0

        net_minutes = max(total_entry_minutes - total_interruption_minutes, 0)
        actual_hours = round(net_minutes / 60.0, 2)

        # Persist to the Order row
        order_result = await db.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        order = order_result.scalar_one_or_none()
        if order is None:
            logger.warning(
                "auto_calculate_actual_hours: order_id=%d not found", order_id
            )
            return None

        order.actual_hours = actual_hours
        await db.flush()

        logger.info(
            "auto_calculate_actual_hours: order_id=%d => %.2f h "
            "(entry_min=%d, interruption_min=%d)",
            order_id,
            actual_hours,
            total_entry_minutes,
            total_interruption_minutes,
        )
        return actual_hours

    @staticmethod
    def validate_time_entry_ml_readiness(time_entry: TimeEntryModel) -> dict:
        """
        Check whether a single (closed) time entry has all fields required for ML.

        Returns a dict with:
          is_ready: bool
          missing_fields: list[str]  — empty when is_ready is True
          score: float  — 0.0-1.0 fraction of fields present

        This is a synchronous utility — it does not hit the database.
        """
        required_checks: list[tuple[str, bool]] = [
            ("activity_id", time_entry.activity_id is not None),
            ("duration_minutes", time_entry.duration_minutes is not None and time_entry.duration_minutes > 0),
            ("end_time", time_entry.end_time is not None),
            ("complexity_rating", time_entry.complexity_rating is not None),
            ("quality_rating", time_entry.quality_rating is not None),
        ]

        missing = [name for name, present in required_checks if not present]
        score = round((len(required_checks) - len(missing)) / len(required_checks), 2)

        return {
            "is_ready": len(missing) == 0,
            "missing_fields": missing,
            "score": score,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_actionable_message(
        ready: bool,
        fully_complete_count: int,
        field_completeness_list: list[FieldCompleteness],
        data_readiness_score: float,
    ) -> str:
        """Derive the single most impactful next action from the current data state."""
        if ready:
            return (
                f"Bereit zum Training: {fully_complete_count} vollstaendige Auftraege vorhanden. "
                "Starten Sie das Modell-Training ueber den ML-Trainingsbereich."
            )

        needed = MINIMUM_ORDERS_FOR_TRAINING - fully_complete_count
        if needed > 0:
            # Find the required field with the lowest completeness
            worst_required = min(
                (fc for fc in field_completeness_list if fc.is_required_for_ml),
                key=lambda fc: fc.completeness_pct,
                default=None,
            )
            if worst_required and worst_required.completeness_pct < 50.0:
                return (
                    f"Noch {needed} vollstaendige Auftraege benoetigt. "
                    f"Wichtigste Massnahme: '{worst_required.display_name}' bei der Auftragserfassung "
                    f"ausfuellen (aktuell nur {worst_required.completeness_pct:.0f}% belegt)."
                )
            return (
                f"Noch {needed} vollstaendige Auftraege benoetigt (Score: {data_readiness_score:.0f}/100). "
                "Tragen Sie Auftragstyp, Komplexit\u00e4t und Metallsorte bei jedem neuen Auftrag ein."
            )

        # Enough orders but score is too low — time-entry quality is the gap
        return (
            f"Datenmenge ausreichend ({fully_complete_count} Auftraege), aber Score zu niedrig "
            f"({data_readiness_score:.0f}/100). Ermuetigen Sie die Goldschmiede, Komplexit\u00e4ts- "
            "und Qualit\u00e4tsbewertung bei jeder Zeiterfassung einzutragen."
        )


