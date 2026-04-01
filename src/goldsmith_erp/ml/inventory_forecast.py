# src/goldsmith_erp/ml/inventory_forecast.py
"""
Inventory depletion forecaster for metal stock.

Uses simple linear regression over weekly consumption to predict:
  - When a metal type will run out (depletion date)
  - When to reorder (depletion date minus supplier lead time)

This deliberately avoids heavy ML libraries.  Consumption patterns in a
small goldsmith workshop are largely linear: a shop that uses 50 g/week of
18K gold this quarter will use approximately the same next week.  XGBoost
would add noise without adding accuracy given typical dataset sizes (< 200
consumption events per year per metal type).

The forecaster degrades gracefully:
  - < 4 weeks of history: returns a low-confidence estimate with a clear
    explanation in the `confidence_note` field.
  - 0 usage records: returns None — the caller should surface "no data" to
    the user rather than an invented date.

Financial data rules (CLAUDE.md): material cost figures are accessed but
NOT returned in API responses; only weight-based rates and dates are exposed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import MaterialUsage, MetalPurchase, MetalType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# Minimum number of weeks with non-zero usage before we trust the forecast.
_MIN_WEEKS_FOR_HIGH_CONFIDENCE = 4

# Days to look back when calculating consumption rate.
_LOOKBACK_DAYS = 90

# Seconds per week — used for unit conversion.
_SECONDS_PER_WEEK = 7 * 24 * 3600


@dataclass
class DepletionForecast:
    """
    Result of predict_depletion_date() for one metal type.

    All date fields are naive UTC-aligned dates (no timezone) because the
    goldsmith workflow operates within a single local timezone and the
    reorder decision is driven by calendar days, not timestamps.
    """

    metal_type: MetalType

    # Weekly consumption rate derived from the last 90 days.
    weekly_consumption_g: float

    # Remaining stock at the time of calculation (grams).
    remaining_stock_g: float

    # Predicted date the stock hits zero.  None when weekly_consumption_g == 0
    # (metal in stock but not currently being consumed).
    depletion_date: Optional[date]

    # Weeks until depletion from today (may be None).
    weeks_until_depletion: Optional[float]

    # Qualitative confidence rating: "high", "medium", or "low".
    confidence: str

    # Human-readable explanation of the confidence rating.
    confidence_note: str


@dataclass
class ReorderRecommendation:
    """
    Reorder recommendation derived from a DepletionForecast.

    A separate dataclass keeps the API boundary clean: the forecast is
    purely analytical while the recommendation is actionable.
    """

    metal_type: MetalType

    # Date by which a purchase order should be placed.
    reorder_by: Optional[date]

    # Whether the reorder is already overdue as of today.
    is_overdue: bool

    # Human-readable message for the UI (German, workshop-ready).
    message: str

    # Weekly consumption rate passed through for display.
    weekly_consumption_g: float

    # The underlying depletion forecast.
    depletion_date: Optional[date]

    # Confidence level from the underlying forecast.
    confidence: str


class InventoryForecaster:
    """
    Predicts metal inventory depletion and generates reorder recommendations.

    All public methods are static and async; they accept an AsyncSession so
    they integrate cleanly with the existing service layer pattern.
    """

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    @staticmethod
    async def predict_depletion_date(
        db: AsyncSession,
        metal_type: MetalType,
        lookback_days: int = _LOOKBACK_DAYS,
    ) -> Optional[DepletionForecast]:
        """
        Calculate predicted depletion date for a single metal type.

        Returns None if there are no inventory records (i.e., the workshop
        has never purchased this metal type and we have nothing to forecast).

        Args:
            db: Active AsyncSession.
            metal_type: Which metal to forecast.
            lookback_days: How many past days of MaterialUsage to consider.

        Returns:
            DepletionForecast or None.
        """
        # --- Current remaining stock ---
        remaining_g = await InventoryForecaster._get_remaining_stock(db, metal_type)
        if remaining_g is None:
            # No purchases on record — nothing to forecast.
            logger.debug(
                "No purchase history for metal type, skipping forecast",
                extra={"metal_type": metal_type.value},
            )
            return None

        # --- Weekly consumption rate from MaterialUsage ---
        weekly_rate, weeks_of_data = await InventoryForecaster._get_weekly_consumption(
            db, metal_type, lookback_days
        )

        # --- Confidence assessment ---
        confidence, confidence_note = InventoryForecaster._assess_confidence(
            weekly_rate, weeks_of_data
        )

        # --- Depletion date ---
        if weekly_rate <= 0.0:
            depletion_date = None
            weeks_until = None
        else:
            weeks_until = remaining_g / weekly_rate
            depletion_date = (
                datetime.utcnow() + timedelta(weeks=weeks_until)
            ).date()

        logger.info(
            "Inventory depletion forecast computed",
            extra={
                "metal_type": metal_type.value,
                "remaining_g": remaining_g,
                "weekly_rate_g": weekly_rate,
                "weeks_until_depletion": weeks_until,
                "confidence": confidence,
            },
        )

        return DepletionForecast(
            metal_type=metal_type,
            weekly_consumption_g=round(weekly_rate, 3),
            remaining_stock_g=round(remaining_g, 3),
            depletion_date=depletion_date,
            weeks_until_depletion=round(weeks_until, 2) if weeks_until is not None else None,
            confidence=confidence,
            confidence_note=confidence_note,
        )

    @staticmethod
    async def predict_reorder_point(
        db: AsyncSession,
        metal_type: MetalType,
        lead_time_days: int = 7,
    ) -> Optional[ReorderRecommendation]:
        """
        Calculate when a reorder should be placed for a metal type.

        The reorder date = depletion_date - lead_time_days.
        If reorder_date < today, the message flags the order as overdue.

        Args:
            db: Active AsyncSession.
            metal_type: Which metal to check.
            lead_time_days: Supplier lead time in calendar days (default 7).

        Returns:
            ReorderRecommendation or None if no inventory data exists.
        """
        forecast = await InventoryForecaster.predict_depletion_date(db, metal_type)
        if forecast is None:
            return None

        today = datetime.utcnow().date()

        if forecast.depletion_date is None:
            # Stock exists but consumption is zero — no reorder needed yet.
            return ReorderRecommendation(
                metal_type=metal_type,
                reorder_by=None,
                is_overdue=False,
                message=(
                    f"Kein Verbrauch in den letzten {_LOOKBACK_DAYS} Tagen erfasst. "
                    "Bestand vorhanden, aber kein Bestelldatum ableitbar."
                ),
                weekly_consumption_g=forecast.weekly_consumption_g,
                depletion_date=None,
                confidence=forecast.confidence,
            )

        reorder_date = forecast.depletion_date - timedelta(days=lead_time_days)
        is_overdue = reorder_date < today

        if is_overdue:
            message = (
                f"Nachbestellung uberfaellig! "
                f"Reichweite aufgebraucht am {forecast.depletion_date.strftime('%d.%m.%Y')} "
                f"(Verbrauch: {forecast.weekly_consumption_g:.1f} g/Woche). "
                f"Sofort bestellen."
            )
        else:
            days_until_reorder = (reorder_date - today).days
            message = (
                f"Nachbestellung bis {reorder_date.strftime('%d.%m.%Y')} "
                f"(in {days_until_reorder} Tagen). "
                f"Aufgebraucht ca. {forecast.depletion_date.strftime('%d.%m.%Y')} "
                f"bei {forecast.weekly_consumption_g:.1f} g/Woche."
            )

        return ReorderRecommendation(
            metal_type=metal_type,
            reorder_by=reorder_date,
            is_overdue=is_overdue,
            message=message,
            weekly_consumption_g=forecast.weekly_consumption_g,
            depletion_date=forecast.depletion_date,
            confidence=forecast.confidence,
        )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    async def _get_remaining_stock(
        db: AsyncSession, metal_type: MetalType
    ) -> Optional[float]:
        """
        Sum remaining_weight_g across all active (non-depleted) purchases
        for a given metal type.

        Returns None if no purchases exist at all (distinct from 0 remaining).
        """
        stmt = select(func.sum(MetalPurchase.remaining_weight_g)).where(
            MetalPurchase.metal_type == metal_type
        )
        result = await db.execute(stmt)
        total = result.scalar_one_or_none()

        # Distinguish "no rows" (None) from "rows but sum is zero" (0.0).
        if total is None:
            # Check whether any purchases exist at all.
            count_stmt = select(func.count(MetalPurchase.id)).where(
                MetalPurchase.metal_type == metal_type
            )
            count_result = await db.execute(count_stmt)
            count = count_result.scalar_one()
            if count == 0:
                return None
            return 0.0

        return float(total)

    @staticmethod
    async def _get_weekly_consumption(
        db: AsyncSession,
        metal_type: MetalType,
        lookback_days: int,
    ) -> tuple[float, int]:
        """
        Calculate average weekly consumption rate for a metal type.

        Queries MaterialUsage joined to MetalPurchase (to filter by metal_type)
        over the past `lookback_days`.  Returns (weekly_rate_g, weeks_of_data).

        The "weeks_of_data" count is the number of calendar weeks in the
        lookback window that had at least one usage event — used for
        confidence scoring.
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        # Total weight consumed in the lookback window.
        stmt = (
            select(func.sum(MaterialUsage.weight_used_g))
            .join(MetalPurchase, MaterialUsage.metal_purchase_id == MetalPurchase.id)
            .where(
                MetalPurchase.metal_type == metal_type,
                MaterialUsage.used_at >= cutoff,
            )
        )
        result = await db.execute(stmt)
        total_consumed_g: float = float(result.scalar_one() or 0.0)

        # Count distinct ISO weeks with usage (proxy for "active weeks").
        # SQLAlchemy-agnostic: fetch individual used_at timestamps and
        # compute distinct weeks in Python — simpler than a cross-DB
        # date_trunc expression and the dataset is small.
        weeks_stmt = (
            select(MaterialUsage.used_at)
            .join(MetalPurchase, MaterialUsage.metal_purchase_id == MetalPurchase.id)
            .where(
                MetalPurchase.metal_type == metal_type,
                MaterialUsage.used_at >= cutoff,
            )
        )
        ts_result = await db.execute(weeks_stmt)
        timestamps = ts_result.scalars().all()

        distinct_weeks: set[tuple[int, int]] = set()
        for ts in timestamps:
            # isocalendar() returns (ISO year, ISO week number, weekday)
            iso = ts.isocalendar()
            distinct_weeks.add((iso[0], iso[1]))

        weeks_of_data = len(distinct_weeks)

        # Normalise: total consumed divided by actual lookback weeks
        lookback_weeks = lookback_days / 7.0
        weekly_rate = total_consumed_g / lookback_weeks if lookback_weeks > 0 else 0.0

        return weekly_rate, weeks_of_data

    @staticmethod
    def _assess_confidence(weekly_rate: float, weeks_of_data: int) -> tuple[str, str]:
        """
        Return (confidence_level, human_readable_note).

        "high"   — at least 4 weeks of usage data, meaningful consumption rate.
        "medium" — 1–3 weeks of data, or very low rate.
        "low"    — no usage data in the lookback window.
        """
        if weeks_of_data == 0 or weekly_rate == 0.0:
            return (
                "low",
                "Kein Verbrauch im Auswertungszeitraum — Prognose nicht zuverlassig.",
            )
        if weeks_of_data < _MIN_WEEKS_FOR_HIGH_CONFIDENCE:
            return (
                "medium",
                f"Nur {weeks_of_data} Woche(n) mit Verbrauchsdaten — "
                "Prognose als Richtwert verwenden.",
            )
        return (
            "high",
            f"Basierend auf {weeks_of_data} Wochen Verbrauchsdaten.",
        )
