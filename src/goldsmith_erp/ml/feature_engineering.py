"""
Feature engineering pipeline for ML-based duration prediction.

All public methods on FeatureEngineer are async and accept an AsyncSession
as their first argument so they compose naturally with the rest of the service
layer.  No pandas dependency at this layer — every method returns plain Python
dicts.  The caller (model training or prediction API) is responsible for
assembling dicts into a DataFrame.

Feature naming convention
--------------------------
All keys emitted by this module map 1-to-1 to column names defined in
constants.py.  One-hot columns produced by encoders.py are merged in as
``<prefix>_<value>`` keys.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Activity,
    Gemstone,
    Interruption,
    Order,
    OrderStatusEnum,
    TimeEntry,
)
from goldsmith_erp.ml.constants import (
    ORDER_TYPE_KEYWORDS,
    SEASONAL_FACTORS,
)
from goldsmith_erp.ml.encoders import (
    encode_finish_type,
    encode_metal_type,
    encode_order_type,
    encode_setting_type,
)

logger = logging.getLogger(__name__)

# Sentinel used wherever a numeric feature is genuinely unknown.
# Downstream model code should impute or drop rows with this marker.
MISSING_NUMERIC: float = float("nan")


# ── Internal helpers ──────────────────────────────────────────────────────────


def _infer_order_type(title: str | None, description: str | None) -> str:
    """
    Derive an order type from free-text title/description.

    Searches for keyword matches (case-insensitive) against
    ORDER_TYPE_KEYWORDS.  Returns the first matching type, or "custom"
    when no keyword matches.
    """
    text = " ".join(filter(None, [title, description])).lower()
    for order_type, keywords in ORDER_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return order_type
    return "custom"


def _detect_finish_type(description: str | None) -> str:
    """
    Heuristically detect surface finish from an order description.

    Returns a KNOWN_FINISH_TYPES value or "unknown".
    """
    if not description:
        return "unknown"
    desc = description.lower()
    if any(k in desc for k in ("hochglanz", "poliert", "polished", "glanz")):
        return "polished"
    if any(k in desc for k in ("matt", "matte", "seidenmatt")):
        return "matte"
    if any(k in desc for k in ("gebürstet", "brushed", "satiniert")):
        return "brushed"
    if any(k in desc for k in ("gehämmert", "hammered", "gehammer")):
        return "hammered"
    if any(k in desc for k in ("sandgestrahlt", "sandblasted")):
        return "sandblasted"
    if any(k in desc for k in ("rhodiniert", "rhodium", "weißgold-beschichtung")):
        return "rhodium_plated"
    if any(k in desc for k in ("oxidiert", "oxidized", "geschwärzt")):
        return "oxidized"
    return "unknown"


def _has_engraving(title: str | None, description: str | None) -> bool:
    """Return True when title or description mentions engraving."""
    text = " ".join(filter(None, [title, description])).lower()
    return bool(
        re.search(r"gravur|engraving|engrav|graviert|personali", text)
    )


def _dominant_setting_type(gemstones: list[Gemstone]) -> str | None:
    """Return the most common setting_type across a list of Gemstone rows."""
    if not gemstones:
        return None
    types = [
        g.setting_type.strip().lower()
        for g in gemstones
        if g.setting_type
    ]
    if not types:
        return None
    return Counter(types).most_common(1)[0][0]


def _safe_float(value: Any) -> float:
    """Convert to float, returning MISSING_NUMERIC on failure."""
    if value is None:
        return MISSING_NUMERIC
    try:
        return float(value)
    except (TypeError, ValueError):
        return MISSING_NUMERIC


class FeatureEngineer:
    """
    Extracts ML features from Order and related entities.

    All methods are stateless — instantiate once and reuse across requests.
    """

    # ── Order-level features ──────────────────────────────────────────────────

    async def extract_order_features(
        self,
        db: AsyncSession,
        order: Order,
    ) -> dict[str, Any]:
        """
        Extract features that describe the order's physical and categorical
        properties.

        The returned dict contains only scalar or one-hot encoded values;
        no nested structures.  One-hot columns from encoders are merged in
        so the dict is flat.

        Parameters
        ----------
        db:
            Active async SQLAlchemy session.
        order:
            Order ORM instance.  Gemstones and time_entries relationships
            are loaded inside this method via selectinload if not already
            present.

        Returns
        -------
        dict mapping feature name -> scalar value.
        """
        # ── Reload with eager relationships to guarantee access ───────────────
        result = await db.execute(
            select(Order)
            .where(Order.id == order.id)
            .options(
                selectinload(Order.gemstones),
                selectinload(Order.customer),
            )
        )
        order = result.scalar_one()

        # ── Inferred categoricals ─────────────────────────────────────────────
        order_type = _infer_order_type(order.title, order.description)
        finish_type = _detect_finish_type(order.description)
        dominant_setting = _dominant_setting_type(order.gemstones)

        # ── Gemstone aggregates ───────────────────────────────────────────────
        stone_count: int = sum(
            (g.quantity or 1) for g in order.gemstones
        )
        stone_total_carat: float = sum(
            (g.carat or 0.0) * (g.quantity or 1)
            for g in order.gemstones
        )

        # ── Temporal features from created_at ────────────────────────────────
        created_at: datetime = order.created_at or datetime.now(timezone.utc)
        weekday_name = created_at.strftime("%A").lower()   # monday … sunday
        month_name   = created_at.strftime("%B").lower()   # january … december

        # ── Deadline distance ─────────────────────────────────────────────────
        if order.deadline and order.created_at:
            deadline_in_days: float = max(
                0.0,
                (order.deadline - order.created_at).total_seconds() / 86400.0,
            )
        else:
            deadline_in_days = MISSING_NUMERIC

        # ── Interruption totals across all time entries ───────────────────────
        time_entries_result = await db.execute(
            select(TimeEntry)
            .where(TimeEntry.order_id == order.id)
            .options(selectinload(TimeEntry.interruptions))
        )
        time_entries = time_entries_result.scalars().all()

        total_interruption_minutes: int = sum(
            intr.duration_minutes
            for te in time_entries
            for intr in te.interruptions
            if intr.duration_minutes is not None
        )

        # ── Activity breakdown (name -> total minutes) ────────────────────────
        activity_breakdown: dict[str, float] = defaultdict(float)
        for te in time_entries:
            if te.activity and te.duration_minutes:
                activity_breakdown[te.activity.name] += te.duration_minutes
        activity_breakdown = dict(activity_breakdown)

        # ── Metal type value (string for encoder) ─────────────────────────────
        metal_type_value: str | None = (
            order.metal_type.value if order.metal_type else None
        )

        # ── Assemble flat dict ────────────────────────────────────────────────
        features: dict[str, Any] = {
            "order_id": order.id,
            # Raw categoricals (kept alongside one-hot for interpretability)
            "order_type":          order_type,
            "metal_type":          metal_type_value,
            "finish_type":         finish_type,
            "setting_type":        dominant_setting,
            "order_created_weekday": weekday_name,
            "order_created_month": month_name,
            # Numerics
            "complexity_rating":        _safe_float(order.labor_hours),  # best proxy available
            "metal_weight_grams":       _safe_float(order.estimated_weight_g),
            "stone_count":              float(stone_count),
            "stone_total_carat":        float(stone_total_carat),
            "deadline_in_days":         deadline_in_days,
            "total_interruption_minutes": float(total_interruption_minutes),
            # Booleans
            "has_engraving": _has_engraving(order.title, order.description),
            # Nested (for reference / downstream aggregation)
            "activity_breakdown": activity_breakdown,
        }

        # ── One-hot encode categoricals and merge ─────────────────────────────
        features.update(encode_order_type(order_type))
        features.update(encode_metal_type(metal_type_value))
        features.update(encode_finish_type(finish_type))
        features.update(encode_setting_type(dominant_setting))

        return features

    # ── Customer-level features ───────────────────────────────────────────────

    async def extract_customer_features(
        self,
        db: AsyncSession,
        customer_id: int,
    ) -> dict[str, Any]:
        """
        Derive features about the customer's order history.

        Parameters
        ----------
        db:
            Active async SQLAlchemy session.
        customer_id:
            Primary key of the Customer record.

        Returns
        -------
        dict with keys:
        - ``customer_previous_orders`` (int)
        - ``customer_avg_completion_hours`` (float or nan)
        - ``customer_is_repeat`` (bool)
        """
        # Count total past orders for this customer
        count_result = await db.execute(
            select(func.count(Order.id)).where(
                Order.customer_id == customer_id
            )
        )
        previous_orders_count: int = count_result.scalar_one() or 0

        # Average actual labor hours on completed orders
        completed_result = await db.execute(
            select(Order.labor_hours).where(
                Order.customer_id == customer_id,
                Order.status.in_([
                    OrderStatusEnum.COMPLETED,
                    OrderStatusEnum.DELIVERED,
                ]),
                Order.labor_hours.isnot(None),
            )
        )
        completed_hours = [row[0] for row in completed_result.fetchall()]

        if completed_hours:
            avg_completion_hours: float = sum(completed_hours) / len(completed_hours)
        else:
            avg_completion_hours = MISSING_NUMERIC

        return {
            "customer_previous_orders":    float(previous_orders_count),
            "customer_avg_completion_hours": avg_completion_hours,
            "customer_is_repeat":          previous_orders_count > 1,
        }

    # ── Historical / contextual features ─────────────────────────────────────

    async def extract_historical_features(
        self,
        db: AsyncSession,
        order: Order,
    ) -> dict[str, Any]:
        """
        Compute features that contextualise this order against historical data.

        Parameters
        ----------
        db:
            Active async SQLAlchemy session.
        order:
            The target Order instance.

        Returns
        -------
        dict with keys:
        - ``similar_orders_avg_hours`` — mean actual hours on orders of
          the same inferred type or same metal_type (excluding the current order).
        - ``user_avg_speed_ratio`` — ratio of this order's time-entry
          average to the workshop-wide average for the same activity types.
          1.0 = average speed, <1 = faster than average.
        - ``seasonal_factor`` — workshop load multiplier for the creation month.
        """
        order_type = _infer_order_type(order.title, order.description)
        created_month: int = (order.created_at or datetime.now(timezone.utc)).month

        # ── Similar orders average ────────────────────────────────────────────
        # "Similar" = same inferred order type keyword match in title, OR
        # same metal_type. We use labor_hours as the stored actuals proxy.
        similar_rows = await db.execute(
            select(Order.labor_hours).where(
                Order.id != order.id,
                Order.status.in_([
                    OrderStatusEnum.COMPLETED,
                    OrderStatusEnum.DELIVERED,
                ]),
                Order.metal_type == order.metal_type,
                Order.labor_hours.isnot(None),
            )
        )
        similar_hours = [row[0] for row in similar_rows.fetchall()]

        if similar_hours:
            similar_orders_avg_hours: float = sum(similar_hours) / len(similar_hours)
        else:
            similar_orders_avg_hours = MISSING_NUMERIC

        # ── User average speed ratio ──────────────────────────────────────────
        # Gather activity categories used in this order, then compute the
        # per-user average duration vs. workshop average for those categories.
        te_result = await db.execute(
            select(TimeEntry)
            .where(TimeEntry.order_id == order.id)
            .options(selectinload(TimeEntry.activity))
        )
        order_entries = te_result.scalars().all()

        if not order_entries:
            user_avg_speed_ratio: float = MISSING_NUMERIC
        else:
            # Determine the distinct goldsmith(s) who worked on this order
            user_ids = {te.user_id for te in order_entries if te.user_id}
            activity_categories = {
                te.activity.category
                for te in order_entries
                if te.activity and te.activity.category
            }

            if not user_ids or not activity_categories:
                user_avg_speed_ratio = MISSING_NUMERIC
            else:
                # Workshop-wide average duration for those activity categories
                global_result = await db.execute(
                    select(func.avg(TimeEntry.duration_minutes)).where(
                        TimeEntry.duration_minutes.isnot(None),
                        TimeEntry.activity_id.in_(
                            select(Activity.id).where(
                                Activity.category.in_(activity_categories)
                            )
                        ),
                    )
                )
                global_avg = global_result.scalar_one()

                # Average duration for those users & categories
                user_result = await db.execute(
                    select(func.avg(TimeEntry.duration_minutes)).where(
                        TimeEntry.user_id.in_(user_ids),
                        TimeEntry.duration_minutes.isnot(None),
                        TimeEntry.activity_id.in_(
                            select(Activity.id).where(
                                Activity.category.in_(activity_categories)
                            )
                        ),
                    )
                )
                user_avg = user_result.scalar_one()

                if global_avg and global_avg > 0 and user_avg is not None:
                    user_avg_speed_ratio = float(user_avg) / float(global_avg)
                else:
                    user_avg_speed_ratio = MISSING_NUMERIC

        seasonal_factor: float = SEASONAL_FACTORS.get(created_month, 1.0)

        return {
            "similar_orders_avg_hours": similar_orders_avg_hours,
            "user_avg_speed_ratio":     user_avg_speed_ratio,
            "seasonal_factor":          seasonal_factor,
        }

    # ── Combined feature vector ───────────────────────────────────────────────

    async def build_feature_vector(
        self,
        db: AsyncSession,
        order: Order,
    ) -> dict[str, Any]:
        """
        Merge all feature groups into a single flat dict for this order.

        Suitable for direct insertion into a list that will become a
        pandas DataFrame row.  The ``activity_breakdown`` key contains a
        nested dict and should be dropped before model training if a flat
        representation is required.

        Parameters
        ----------
        db:
            Active async SQLAlchemy session.
        order:
            Any Order instance — does not need to be completed.

        Returns
        -------
        Flat dict of all features, keyed by the names in constants.py.
        """
        order_feats    = await self.extract_order_features(db, order)
        customer_feats = await self.extract_customer_features(db, order.customer_id)
        history_feats  = await self.extract_historical_features(db, order)

        return {
            **order_feats,
            **customer_feats,
            **history_feats,
        }

    # ── Training dataset ─────────────────────────────────────────────────────

    async def build_training_dataset(
        self,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        Build a training dataset from ALL completed/delivered orders that
        have at least one time entry with a recorded duration.

        The target variable ``actual_hours`` is derived by summing all
        ``duration_minutes`` across the order's time entries and converting
        to hours.  ``labor_hours`` on the Order model is used as a fallback
        when no time entries exist (manual entry by goldsmith).

        Parameters
        ----------
        db:
            Active async SQLAlchemy session.

        Returns
        -------
        List of dicts, one per qualifying order.  Each dict contains all
        features plus the ``actual_hours`` target.  Ready for:

            import pandas as pd
            df = pd.DataFrame(rows)
        """
        # Fetch all completed orders with time entries that have durations
        completed_result = await db.execute(
            select(Order)
            .where(
                Order.status.in_([
                    OrderStatusEnum.COMPLETED,
                    OrderStatusEnum.DELIVERED,
                ])
            )
            .options(
                selectinload(Order.gemstones),
                selectinload(Order.customer),
            )
        )
        completed_orders = completed_result.scalars().all()

        rows: list[dict[str, Any]] = []

        for order in completed_orders:
            # Resolve actual hours from time entries
            te_result = await db.execute(
                select(TimeEntry)
                .where(
                    TimeEntry.order_id == order.id,
                    TimeEntry.duration_minutes.isnot(None),
                )
                .options(
                    selectinload(TimeEntry.activity),
                    selectinload(TimeEntry.interruptions),
                )
            )
            time_entries = te_result.scalars().all()

            if time_entries:
                total_minutes: float = sum(
                    te.duration_minutes for te in time_entries
                    if te.duration_minutes is not None
                )
                actual_hours: float = total_minutes / 60.0
            elif order.labor_hours is not None:
                # Fallback: goldsmith recorded hours manually on the order
                actual_hours = float(order.labor_hours)
            else:
                # No usable duration data — skip this order
                logger.debug(
                    "Skipping order %d: no time entries and no labor_hours",
                    order.id,
                )
                continue

            try:
                feature_vector = await self.build_feature_vector(db, order)
            except Exception:
                logger.exception(
                    "Failed to extract features for order %d — skipping",
                    order.id,
                )
                continue

            feature_vector["actual_hours"] = actual_hours
            rows.append(feature_vector)

        logger.info(
            "Training dataset built: %d qualifying orders from %d completed",
            len(rows),
            len(completed_orders),
        )
        return rows
