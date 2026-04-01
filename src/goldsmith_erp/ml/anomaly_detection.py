"""
Two-tier anomaly detection for goldsmith time entries.

Tier 1 — Statistical (works from day 1, no training data needed):
  - For each activity, computes mean/std/median from historical entries.
  - Falls back to domain-knowledge defaults when history is thin.
  - Flags anomaly when: actual > mean + 2*std  OR  actual > 3 * median
    OR (actual > 120 min and activity typical < 60 min).

Tier 2 — Isolation Forest (activates automatically when >= 50 entries):
  - Trained per-activity on features: duration_minutes, complexity_rating,
    time_of_day (hour), day_of_week.
  - contamination=0.05 (expect ~5% anomalies in historical data).
  - Models cached in-process; retrain by calling update_baselines().

Both tiers are stateless from the caller's point of view: pass an activity_id
and a duration, get back an AnomalyResult.

Usage
-----
    detector = AnomalyDetector()
    await detector.update_baselines(db)          # on startup / weekly cron
    result = await detector.check_anomaly(
        db, activity_id=3, duration_minutes=120, complexity_rating=2
    )
    if result.is_anomaly:
        alert = AnomalyAlert(
            time_entry_id=entry.id,
            order_id=entry.order_id,
            activity_name=entry.activity.name,
            user_name=f"{entry.user.first_name} {entry.user.last_name}",
            **result.model_dump(include={
                "expected_duration_minutes", "actual_duration_minutes",
                "deviation_factor", "suggested_reasons"
            }),
            severity=result.severity,
        )
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Activity as ActivityModel,
    TimeEntry as TimeEntryModel,
    Order as OrderModel,
    User as UserModel,
)
from goldsmith_erp.ml.anomaly_alerts import (
    AlertSeverity,
    AnomalyResult,
    severity_from_factor,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimum entries required to upgrade from statistical to Isolation Forest
# ---------------------------------------------------------------------------
_ISOLATION_FOREST_MIN_ENTRIES: int = 50

# ---------------------------------------------------------------------------
# Domain-knowledge defaults (minutes) when no historical data exists yet.
# Keys match Activity.category values from the database.
# ---------------------------------------------------------------------------
CATEGORY_DEFAULT_DURATIONS: dict[str, float] = {
    "fabrication": 60.0,
    "stone_setting": 45.0,
    "polishing": 30.0,
    "engraving": 40.0,
    "repair": 45.0,
    "casting": 90.0,
    "administration": 20.0,
    "waiting": 15.0,
    "consultation": 30.0,
    "default": 45.0,
}

# ---------------------------------------------------------------------------
# German suggested-reason catalogue keyed by Activity.category
# ---------------------------------------------------------------------------
ANOMALY_REASONS: dict[str, list[str]] = {
    "fabrication": [
        "Komplikationen beim Material",
        "Werkzeug defekt",
        "Nacharbeit nötig",
        "Komplexer als erwartet",
    ],
    "stone_setting": [
        "Stein sitzt nicht richtig",
        "Fassung muss angepasst werden",
        "Qualitätsproblem beim Stein",
        "Ungewöhnliche Steinform",
    ],
    "polishing": [
        "Oberfläche erfordert Nacharbeit",
        "Kratzer müssen ausgebessert werden",
        "Oxidation stärker als erwartet",
    ],
    "engraving": [
        "Vorlage musste mehrfach angepasst werden",
        "Maschinenwechsel nötig",
    ],
    "repair": [
        "Schaden größer als erwartet",
        "Ersatzteil musste beschafft werden",
        "Mehrere Defekte entdeckt",
    ],
    "casting": [
        "Guss fehlgeschlagen, Wiederholung nötig",
        "Einschlüsse im Gussstück",
        "Metalllegierung nicht optimal",
    ],
    "default": [
        "Unterbrechungen nicht erfasst",
        "Aufgabe komplexer als erwartet",
        "Neue Technik verwendet",
        "Abstimmung mit Kunde nötig",
    ],
}


class ActivityBaseline:
    """
    Statistical summary for one activity, computed from historical entries.
    Optionally holds a trained Isolation Forest model.
    """

    __slots__ = (
        "activity_id",
        "category",
        "mean",
        "median",
        "std",
        "p25",
        "p75",
        "p95",
        "min_val",
        "max_val",
        "sample_count",
        "_iso_forest",
        "_iso_scaler",
    )

    def __init__(
        self,
        activity_id: int,
        category: str,
        durations: list[float],
    ) -> None:
        self.activity_id = activity_id
        self.category = category
        self.sample_count = len(durations)
        self._iso_forest = None
        self._iso_scaler = None

        if not durations:
            default = CATEGORY_DEFAULT_DURATIONS.get(category, CATEGORY_DEFAULT_DURATIONS["default"])
            self.mean = default
            self.median = default
            self.std = default * 0.3  # assume 30% CV as prior
            self.p25 = default * 0.7
            self.p75 = default * 1.3
            self.p95 = default * 2.0
            self.min_val = default * 0.3
            self.max_val = default * 3.0
        else:
            sorted_d = sorted(durations)
            n = len(sorted_d)
            self.mean = statistics.mean(sorted_d)
            self.median = statistics.median(sorted_d)
            self.std = statistics.stdev(sorted_d) if n > 1 else self.mean * 0.3
            self.p25 = sorted_d[max(0, int(n * 0.25) - 1)]
            self.p75 = sorted_d[min(n - 1, int(n * 0.75))]
            self.p95 = sorted_d[min(n - 1, int(n * 0.95))]
            self.min_val = sorted_d[0]
            self.max_val = sorted_d[-1]

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "category": self.category,
            "sample_count": self.sample_count,
            "mean": round(self.mean, 1),
            "median": round(self.median, 1),
            "std": round(self.std, 1),
            "p25": round(self.p25, 1),
            "p75": round(self.p75, 1),
            "p95": round(self.p95, 1),
            "min": round(self.min_val, 1),
            "max": round(self.max_val, 1),
        }


class AnomalyDetector:
    """
    Stateful anomaly detector for goldsmith time entries.

    Instance-level baseline cache:  _baselines[activity_id] -> ActivityBaseline
    Instance-level IF model cache:  stored on ActivityBaseline._iso_forest

    Call update_baselines(db) on startup and weekly to refresh.
    check_anomaly() is the primary method; it is non-blocking and thread-safe
    for reads because we only write during update_baselines().
    """

    def __init__(self) -> None:
        # activity_id -> ActivityBaseline
        self._baselines: dict[int, ActivityBaseline] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_anomaly(
        self,
        db: AsyncSession,
        activity_id: int,
        duration_minutes: int,
        complexity_rating: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> AnomalyResult:
        """
        Check whether a completed time entry is anomalous.

        Uses Isolation Forest when a trained model is available for this
        activity, otherwise falls back to statistical thresholds.

        Returns an AnomalyResult.  is_anomaly=False is the normal path.
        """
        baseline = await self._get_or_load_baseline(db, activity_id)

        # Try Isolation Forest first (Tier 2)
        if baseline._iso_forest is not None:
            result = self._check_isolation_forest(
                baseline, duration_minutes, complexity_rating
            )
            if result is not None:
                return result

        # Fall back to statistical thresholds (Tier 1)
        return self._check_statistical(baseline, duration_minutes)

    async def get_activity_statistics(
        self, db: AsyncSession, activity_id: int
    ) -> dict:
        """
        Return statistical summary for an activity.

        Triggers a lazy baseline load if not already in cache.
        """
        baseline = await self._get_or_load_baseline(db, activity_id)
        return baseline.to_dict()

    async def update_baselines(self, db: AsyncSession) -> None:
        """
        Recompute all activity baselines from historical TimeEntry data.

        Trains / retrains Isolation Forest models for activities that have
        >= _ISOLATION_FOREST_MIN_ENTRIES completed entries.

        Designed to be called once at startup and then weekly.
        """
        # Fetch all activities
        activities_result = await db.execute(select(ActivityModel))
        activities: list[ActivityModel] = activities_result.scalars().all()

        for activity in activities:
            await self._rebuild_baseline(db, activity)

        logger.info(
            "Anomaly detector baselines updated",
            extra={"activity_count": len(activities)},
        )

    async def get_active_alerts(self, db: AsyncSession) -> list[dict]:
        """
        Find all currently running time entries that already exceed their
        expected duration and return alert dicts ready for the API.

        Only entries without an end_time (still running) are checked.
        """
        result = await db.execute(
            select(TimeEntryModel)
            .options(
                selectinload(TimeEntryModel.activity),
                selectinload(TimeEntryModel.order),
                selectinload(TimeEntryModel.user),
            )
            .where(TimeEntryModel.end_time.is_(None))
        )
        running_entries: list[TimeEntryModel] = result.scalars().all()

        alerts = []
        now = datetime.utcnow()

        for entry in running_entries:
            elapsed = int((now - entry.start_time).total_seconds() / 60)
            if elapsed <= 0:
                continue

            baseline = await self._get_or_load_baseline(db, entry.activity_id)
            anomaly = self._check_statistical(baseline, elapsed)

            if not anomaly.is_anomaly:
                continue

            user_name = (
                f"{entry.user.first_name} {entry.user.last_name}"
                if entry.user
                else f"User #{entry.user_id}"
            )
            activity_name = entry.activity.name if entry.activity else f"Activity #{entry.activity_id}"

            alerts.append(
                {
                    "time_entry_id": entry.id,
                    "order_id": entry.order_id,
                    "order_title": entry.order.title if entry.order else None,
                    "activity_name": activity_name,
                    "user_name": user_name,
                    "elapsed_minutes": elapsed,
                    "expected_duration_minutes": anomaly.expected_duration_minutes,
                    "deviation_factor": anomaly.deviation_factor,
                    "severity": anomaly.severity.value if anomaly.severity else None,
                    "suggested_reasons": anomaly.suggested_reasons,
                }
            )

        return alerts

    # ------------------------------------------------------------------
    # Statistical detection (Tier 1)
    # ------------------------------------------------------------------

    def _check_statistical(
        self, baseline: ActivityBaseline, duration_minutes: int
    ) -> AnomalyResult:
        """
        Apply three complementary statistical rules.

        Rule A:  actual > mean + 2 * std
        Rule B:  actual > 3 * median
        Rule C:  actual > 120 min AND typical duration < 60 min

        Expected duration is mean (preferred) or median when std is unreliable.
        """
        expected = baseline.mean
        std = baseline.std

        # Guard against degenerate std values
        upper_bound_a = expected + 2.0 * max(std, expected * 0.15)
        upper_bound_b = 3.0 * baseline.median
        upper_bound_c = 120.0  # absolute threshold

        rule_a = duration_minutes > upper_bound_a
        rule_b = duration_minutes > upper_bound_b
        rule_c = (duration_minutes > upper_bound_c) and (baseline.median < 60.0)

        is_anomaly = rule_a or rule_b or rule_c

        if not is_anomaly:
            return AnomalyResult(
                is_anomaly=False,
                expected_duration_minutes=expected,
                actual_duration_minutes=duration_minutes,
                deviation_factor=round(duration_minutes / max(expected, 1.0), 2),
                detection_method="statistical",
            )

        deviation_factor = round(duration_minutes / max(expected, 1.0), 2)
        severity = severity_from_factor(deviation_factor)
        reasons = self._get_reasons(baseline.category)

        return AnomalyResult(
            is_anomaly=True,
            severity=severity,
            expected_duration_minutes=round(expected, 1),
            actual_duration_minutes=duration_minutes,
            deviation_factor=deviation_factor,
            suggested_reasons=reasons,
            detection_method="statistical",
        )

    # ------------------------------------------------------------------
    # Isolation Forest detection (Tier 2)
    # ------------------------------------------------------------------

    def _check_isolation_forest(
        self,
        baseline: ActivityBaseline,
        duration_minutes: int,
        complexity_rating: Optional[int],
    ) -> Optional[AnomalyResult]:
        """
        Score a single observation using the cached Isolation Forest model.

        Returns None if scoring fails so the caller can fall back to Tier 1.
        """
        try:
            import numpy as np

            now = datetime.utcnow()
            hour_of_day = now.hour
            day_of_week = now.weekday()
            complexity = complexity_rating if complexity_rating is not None else 3

            feature_vector = np.array(
                [[duration_minutes, complexity, hour_of_day, day_of_week]],
                dtype=float,
            )
            if baseline._iso_scaler is not None:
                feature_vector = baseline._iso_scaler.transform(feature_vector)

            # predict returns 1 (normal) or -1 (anomaly)
            prediction = baseline._iso_forest.predict(feature_vector)[0]
            score = baseline._iso_forest.score_samples(feature_vector)[0]
            # score < -0.1 is typical Isolation Forest anomaly territory

            is_anomaly = prediction == -1
            expected = baseline.mean
            deviation_factor = round(duration_minutes / max(expected, 1.0), 2)
            severity = severity_from_factor(deviation_factor) if is_anomaly else None
            reasons = self._get_reasons(baseline.category) if is_anomaly else []

            return AnomalyResult(
                is_anomaly=is_anomaly,
                severity=severity,
                expected_duration_minutes=round(expected, 1),
                actual_duration_minutes=duration_minutes,
                deviation_factor=deviation_factor,
                suggested_reasons=reasons,
                detection_method="isolation_forest",
            )
        except Exception as exc:
            logger.warning(
                "Isolation Forest scoring failed, falling back to statistical",
                extra={"error": str(exc)},
            )
            return None

    # ------------------------------------------------------------------
    # Baseline loading and training
    # ------------------------------------------------------------------

    async def _get_or_load_baseline(
        self, db: AsyncSession, activity_id: int
    ) -> ActivityBaseline:
        """Return cached baseline or load it lazily from the database."""
        if activity_id not in self._baselines:
            activity_result = await db.execute(
                select(ActivityModel).where(ActivityModel.id == activity_id)
            )
            activity = activity_result.scalar_one_or_none()
            if activity is None:
                # Unknown activity — create a generic baseline
                return ActivityBaseline(activity_id, "default", [])
            await self._rebuild_baseline(db, activity)

        return self._baselines[activity_id]

    async def _rebuild_baseline(
        self, db: AsyncSession, activity: ActivityModel
    ) -> None:
        """
        Fetch all completed entries for an activity, build ActivityBaseline,
        and (if enough data) train an Isolation Forest.
        """
        entries_result = await db.execute(
            select(TimeEntryModel).where(
                and_(
                    TimeEntryModel.activity_id == activity.id,
                    TimeEntryModel.duration_minutes.isnot(None),
                    TimeEntryModel.end_time.isnot(None),
                )
            )
        )
        entries: list[TimeEntryModel] = entries_result.scalars().all()

        durations = [float(e.duration_minutes) for e in entries if e.duration_minutes and e.duration_minutes > 0]

        baseline = ActivityBaseline(
            activity_id=activity.id,
            category=activity.category,
            durations=durations,
        )

        # Train Isolation Forest when there is enough data
        if len(entries) >= _ISOLATION_FOREST_MIN_ENTRIES:
            self._train_isolation_forest(baseline, entries)

        self._baselines[activity.id] = baseline
        logger.debug(
            "Rebuilt baseline for activity",
            extra={
                "activity_id": activity.id,
                "category": activity.category,
                "samples": len(durations),
                "model": "isolation_forest" if baseline._iso_forest else "statistical",
            },
        )

    @staticmethod
    def _train_isolation_forest(
        baseline: ActivityBaseline, entries: list[TimeEntryModel]
    ) -> None:
        """
        Build a feature matrix and train (or retrain) an Isolation Forest for
        the given activity.  Stores model and scaler on the baseline object.

        Features: duration_minutes, complexity_rating, hour_of_day, day_of_week
        """
        try:
            import numpy as np
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler

            rows = []
            for e in entries:
                if not e.duration_minutes or e.duration_minutes <= 0:
                    continue
                complexity = e.complexity_rating if e.complexity_rating is not None else 3
                hour = e.start_time.hour if e.start_time else 9
                dow = e.start_time.weekday() if e.start_time else 0
                rows.append([float(e.duration_minutes), float(complexity), float(hour), float(dow)])

            if len(rows) < _ISOLATION_FOREST_MIN_ENTRIES:
                return

            X = np.array(rows, dtype=float)
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            iso = IsolationForest(
                contamination=0.05,
                n_estimators=100,
                random_state=42,
                n_jobs=1,
            )
            iso.fit(X_scaled)

            baseline._iso_forest = iso
            baseline._iso_scaler = scaler

        except ImportError:
            logger.warning(
                "scikit-learn not available — Isolation Forest disabled, using statistical only"
            )
        except Exception as exc:
            logger.error(
                "Failed to train Isolation Forest",
                extra={"activity_id": baseline.activity_id, "error": str(exc)},
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _get_reasons(category: str) -> list[str]:
        """Return the German reason list for the given activity category."""
        return ANOMALY_REASONS.get(category, ANOMALY_REASONS["default"])
