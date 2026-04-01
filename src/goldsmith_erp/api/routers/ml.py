# src/goldsmith_erp/api/routers/ml.py
"""
ML prediction and monitoring API router.

All ML modules are imported with try/except guards so the application starts
cleanly even when the ML dependencies are not yet installed or the models have
not been trained.  Endpoints that require an unavailable module return HTTP 503
with a German error message rather than crashing.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import Activity, Order, TimeEntry, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.ml import (
    ActivityDetailResponse,
    ActivityDurationStats,
    AnomalyAlertResponse,
    ComplexityBreakdown,
    DataQualityResponse,
    DurationPredictionRequest,
    DurationPredictionResponse,
    FieldCoverage,
    ModelStatusResponse,
    SimilarOrder,
    TrainResponse,
    TrainingMetrics,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Optional ML module imports — never crash on missing dependencies
# ---------------------------------------------------------------------------

try:
    from goldsmith_erp.ml.feature_engineering import FeatureEngineer  # type: ignore[import]

    _feature_engineer: Optional[Any] = FeatureEngineer()
except Exception as exc:  # noqa: BLE001
    logger.warning("FeatureEngineer nicht verfügbar: %s", exc)
    _feature_engineer = None

try:
    from goldsmith_erp.ml.duration_model import DurationPredictor  # type: ignore[import]

    _duration_predictor: Optional[Any] = DurationPredictor()
except Exception as exc:  # noqa: BLE001
    logger.warning("DurationPredictor nicht verfügbar: %s", exc)
    _duration_predictor = None

try:
    from goldsmith_erp.ml.anomaly_detection import AnomalyDetector  # type: ignore[import]

    _anomaly_detector: Optional[Any] = AnomalyDetector()
except Exception as exc:  # noqa: BLE001
    logger.warning("AnomalyDetector nicht verfügbar: %s", exc)
    _anomaly_detector = None

try:
    from goldsmith_erp.services.ml_data_service import MLDataService  # type: ignore[import]

    _ml_data_service: Optional[Any] = MLDataService()
except Exception as exc:  # noqa: BLE001
    logger.warning("MLDataService nicht verfügbar: %s", exc)
    _ml_data_service = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ML_UNAVAILABLE_DETAIL = "ML-Modul nicht verfügbar. Bitte wenden Sie sich an den Administrator."


def _require_ml_module(module: Optional[Any], name: str) -> Any:
    """Raise 503 when an optional ML module failed to load."""
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{_ML_UNAVAILABLE_DETAIL} (Modul: {name})",
        )
    return module


def _safe_float(value: Any) -> float:
    """Convert numpy/decimal/other numeric types to plain Python float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _heuristic_estimate(request: DurationPredictionRequest) -> DurationPredictionResponse:
    """
    Rule-based duration estimate when no trained model is available.

    Base times are drawn from workshop experience; complexity and weight are
    used as simple multipliers.  Returns is_heuristic=True so the caller can
    display an appropriate disclaimer.
    """
    base_hours: dict[str, float] = {
        "ring": 3.0,
        "chain": 5.0,
        "pendant": 2.5,
        "earrings": 4.0,
        "bracelet": 6.0,
        "brooch": 4.5,
        "repair": 1.5,
        "custom": 8.0,
    }
    base = base_hours.get(request.order_type or "custom", 4.0)

    # Complexity multiplier: 1→0.7×, 3→1.0×, 5→1.8×
    complexity = request.complexity_rating or 3
    complexity_multiplier = 0.5 + (complexity - 1) * 0.325

    # Weight factor: heavy pieces take longer (diminishing returns)
    weight_factor = 1.0
    if request.estimated_weight_g:
        weight_factor = 1.0 + min(request.estimated_weight_g / 50.0, 0.5)

    # Gemstone setting adds time proportionally
    stone_factor = 1.0 + (request.gemstone_count or 0) * 0.15

    estimated = base * complexity_multiplier * weight_factor * stone_factor
    ci_low = estimated * 0.75
    ci_high = estimated * 1.40

    # Confidence depends on how many features were provided
    filled = sum(
        1
        for f in [
            request.order_type,
            request.complexity_rating,
            request.estimated_weight_g,
            request.metal_type,
        ]
        if f is not None
    )
    confidence_level = "low" if filled < 2 else ("medium" if filled < 4 else "high")

    return DurationPredictionResponse(
        estimated_hours=round(estimated, 2),
        confidence_interval_low=round(ci_low, 2),
        confidence_interval_high=round(ci_high, 2),
        confidence_level=confidence_level,
        similar_orders=[],
        model_status="not_trained",
        is_heuristic=True,
    )


# ---------------------------------------------------------------------------
# Prediction endpoints
# ---------------------------------------------------------------------------


async def _run_prediction(request: DurationPredictionRequest) -> DurationPredictionResponse:
    """
    Core prediction logic shared by both prediction endpoints.

    When the model has not been trained yet, a rule-based heuristic estimate
    is returned with `model_status: "not_trained"` and `is_heuristic: true`.
    """
    if _duration_predictor is None or not getattr(_duration_predictor, "is_ready", False):
        return _heuristic_estimate(request)

    try:
        if _feature_engineer is not None:
            features = _feature_engineer.extract_from_request(request.model_dump())
        else:
            features = request.model_dump(exclude_none=True)

        result = _duration_predictor.predict(features)

        similar_orders = [
            SimilarOrder(
                order_id=int(s["order_id"]),
                actual_hours=_safe_float(s["actual_hours"]),
                order_type=s.get("order_type"),
                complexity_rating=s.get("complexity_rating"),
                similarity_score=_safe_float(s["similarity_score"]),
            )
            for s in result.get("similar_orders", [])[:5]
        ]

        return DurationPredictionResponse(
            estimated_hours=_safe_float(result["estimated_hours"]),
            confidence_interval_low=_safe_float(result["ci_low"]),
            confidence_interval_high=_safe_float(result["ci_high"]),
            confidence_level=result.get("confidence_level", "medium"),
            similar_orders=similar_orders,
            model_status="trained",
            is_heuristic=False,
        )
    except Exception as exc:
        logger.error("Fehler bei Dauervorhersage: %s", exc, exc_info=True)
        # Graceful fallback to heuristic rather than a 500
        return _heuristic_estimate(request)


@router.post(
    "/predict/duration",
    response_model=DurationPredictionResponse,
    summary="Auftragsdauer vorhersagen (neuer Auftrag)",
)
@require_permission(Permission.ML_PREDICT)
async def predict_duration(
    body: DurationPredictionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DurationPredictionResponse:
    """
    Predict how many hours a new order will require.

    When the model has not been trained yet, a rule-based heuristic estimate
    is returned with `model_status: "not_trained"` and `is_heuristic: true`.
    """
    return await _run_prediction(body)


@router.get(
    "/predict/order/{order_id}",
    response_model=DurationPredictionResponse,
    summary="Auftragsdauer für bestehenden Auftrag vorhersagen",
)
@require_permission(Permission.ML_PREDICT)
async def predict_duration_for_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DurationPredictionResponse:
    """Predict duration for an existing order by extracting its stored features."""
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.gemstones))
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail=f"Auftrag {order_id} nicht gefunden.")

    gemstone_count = len(order.gemstones) if order.gemstones else 0
    primary_stone = order.gemstones[0] if order.gemstones else None

    prediction_request = DurationPredictionRequest(
        order_type=order.order_type,
        complexity_rating=order.complexity_rating,
        metal_type=order.metal_type.value if order.metal_type else None,
        estimated_weight_g=order.estimated_weight_g,
        finish_type=order.finish_type if hasattr(order, "finish_type") else None,
        gemstone_count=gemstone_count,
        gemstone_type=primary_stone.type if primary_stone else None,
        gemstone_carat=_safe_float(primary_stone.carat) if primary_stone and primary_stone.carat else None,
    )
    return await _run_prediction(prediction_request)


# ---------------------------------------------------------------------------
# Anomaly endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/anomalies/active",
    response_model=list[AnomalyAlertResponse],
    summary="Aktive Anomalie-Warnungen (laufende Zeiteinträge)",
)
@require_permission(Permission.ML_VIEW_STATS)
async def get_active_anomalies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AnomalyAlertResponse]:
    """
    Return time entries that are currently running and exceed their expected duration.

    Falls back to a threshold-based heuristic (200% of activity average) when
    the AnomalyDetector module is not loaded.
    """
    now = datetime.utcnow()

    running_result = await db.execute(
        select(TimeEntry)
        .where(TimeEntry.end_time.is_(None))
        .options(
            selectinload(TimeEntry.activity),
            selectinload(TimeEntry.order),
        )
    )
    running_entries = running_result.scalars().all()

    if not running_entries:
        return []

    alerts: list[AnomalyAlertResponse] = []

    for entry in running_entries:
        elapsed_minutes = (now - entry.start_time).total_seconds() / 60.0

        # Determine expected duration
        expected_minutes: float
        if (
            _anomaly_detector is not None
            and hasattr(_anomaly_detector, "expected_duration")
        ):
            try:
                expected_minutes = _safe_float(
                    _anomaly_detector.expected_duration(
                        activity_id=entry.activity_id,
                        complexity_rating=entry.complexity_rating,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("AnomalyDetector.expected_duration fehlgeschlagen: %s", exc)
                expected_minutes = _safe_float(
                    entry.activity.average_duration_minutes or 60.0
                )
        else:
            expected_minutes = _safe_float(
                entry.activity.average_duration_minutes if entry.activity else 60.0
            ) or 60.0

        if elapsed_minutes <= expected_minutes * 1.5:
            # Not yet anomalous
            continue

        anomaly_score = (elapsed_minutes - expected_minutes) / max(expected_minutes, 1.0)
        severity = "critical" if anomaly_score > 1.0 else "warning"

        alerts.append(
            AnomalyAlertResponse(
                time_entry_id=str(entry.id),
                order_id=entry.order_id,
                order_title=entry.order.title if entry.order else None,
                activity_id=entry.activity_id,
                activity_name=entry.activity.name if entry.activity else None,
                user_id=entry.user_id,
                elapsed_minutes=round(elapsed_minutes, 1),
                expected_minutes=round(expected_minutes, 1),
                anomaly_score=round(anomaly_score, 3),
                severity=severity,
                started_at=entry.start_time,
                detected_at=now,
            )
        )

    return alerts


@router.get(
    "/anomalies/history",
    response_model=list[AnomalyAlertResponse],
    summary="Anomalie-Verlauf der letzten 7 Tage",
)
@require_permission(Permission.ML_VIEW_STATS)
async def get_anomaly_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AnomalyAlertResponse]:
    """
    Return completed time entries from the last 7 days that exceeded their
    expected duration by more than 50%.
    """
    cutoff = datetime.utcnow() - timedelta(days=7)

    result = await db.execute(
        select(TimeEntry)
        .where(
            TimeEntry.end_time.is_not(None),
            TimeEntry.start_time >= cutoff,
        )
        .options(
            selectinload(TimeEntry.activity),
            selectinload(TimeEntry.order),
        )
    )
    completed_entries = result.scalars().all()

    alerts: list[AnomalyAlertResponse] = []
    for entry in completed_entries:
        if entry.duration_minutes is None:
            continue

        elapsed = _safe_float(entry.duration_minutes)
        expected = _safe_float(
            entry.activity.average_duration_minutes if entry.activity else 60.0
        ) or 60.0

        if elapsed <= expected * 1.5:
            continue

        anomaly_score = (elapsed - expected) / max(expected, 1.0)
        severity = "critical" if anomaly_score > 1.0 else "warning"

        alerts.append(
            AnomalyAlertResponse(
                time_entry_id=str(entry.id),
                order_id=entry.order_id,
                order_title=entry.order.title if entry.order else None,
                activity_id=entry.activity_id,
                activity_name=entry.activity.name if entry.activity else None,
                user_id=entry.user_id,
                elapsed_minutes=round(elapsed, 1),
                expected_minutes=round(expected, 1),
                anomaly_score=round(anomaly_score, 3),
                severity=severity,
                started_at=entry.start_time,
                detected_at=entry.end_time or entry.start_time,
            )
        )

    return sorted(alerts, key=lambda a: a.anomaly_score, reverse=True)


# ---------------------------------------------------------------------------
# Model management endpoints (ADMIN only)
# ---------------------------------------------------------------------------


@router.post(
    "/train",
    response_model=TrainResponse,
    summary="Modelltraining auslösen (nur ADMIN)",
)
@require_permission(Permission.ML_TRAIN)
async def train_model(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrainResponse:
    """
    Trigger a full feature extraction and model training run.

    CPU-bound training is offloaded to a thread via asyncio.to_thread so the
    event loop is not blocked.  Returns training metrics on success.
    """
    if _ml_data_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{_ML_UNAVAILABLE_DETAIL} (Modul: MLDataService)",
        )
    if _feature_engineer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{_ML_UNAVAILABLE_DETAIL} (Modul: FeatureEngineer)",
        )
    if _duration_predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{_ML_UNAVAILABLE_DETAIL} (Modul: DurationPredictor)",
        )

    logger.info(
        "Modelltraining gestartet",
        extra={"triggered_by_user_id": current_user.id},
    )

    start_ts = time.monotonic()

    try:
        # Data extraction (async DB calls must stay on the event loop)
        raw_data = await _ml_data_service.get_training_data(db)

        if not raw_data:
            return TrainResponse(
                success=False,
                message="Nicht genügend Trainingsdaten. Mindestens 20 abgeschlossene Aufträge mit tatsächlichen Stunden erforderlich.",
            )

        # Feature engineering + model fit are CPU-bound — run in thread pool
        def _fit() -> dict:
            features = _feature_engineer.transform(raw_data)  # type: ignore[union-attr]
            return _duration_predictor.fit(features)  # type: ignore[union-attr]

        metrics_raw: dict = await asyncio.to_thread(_fit)

        elapsed = time.monotonic() - start_ts

        metrics = TrainingMetrics(
            rmse=_safe_float(metrics_raw.get("rmse", 0)),
            mape=_safe_float(metrics_raw.get("mape", 0)),
            r2=_safe_float(metrics_raw.get("r2", 0)),
            data_size=int(metrics_raw.get("data_size", len(raw_data))),
        )

        logger.info(
            "Modelltraining abgeschlossen",
            extra={
                "rmse": metrics.rmse,
                "mape": metrics.mape,
                "r2": metrics.r2,
                "data_size": metrics.data_size,
                "duration_seconds": round(elapsed, 2),
            },
        )

        return TrainResponse(
            success=True,
            message=f"Training erfolgreich. {metrics.data_size} Datensätze verwendet.",
            metrics=metrics,
            duration_seconds=round(elapsed, 2),
        )

    except Exception as exc:
        elapsed = time.monotonic() - start_ts
        logger.error("Modelltraining fehlgeschlagen: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Training fehlgeschlagen: {exc}",
        ) from exc


@router.get(
    "/status",
    response_model=ModelStatusResponse,
    summary="Modellstatus abrufen",
)
@require_permission(Permission.ML_VIEW_STATS)
async def get_model_status(
    current_user: User = Depends(get_current_user),
) -> ModelStatusResponse:
    """Return the current training state and metrics of the duration predictor."""
    if _duration_predictor is None:
        return ModelStatusResponse(
            model_name="DurationPredictor",
            is_ready=False,
            message="ML-Modul nicht verfügbar",
        )

    is_ready = getattr(_duration_predictor, "is_ready", False)
    metadata: dict = {}
    if hasattr(_duration_predictor, "get_metadata"):
        try:
            metadata = _duration_predictor.get_metadata() or {}
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_metadata fehlgeschlagen: %s", exc)

    metrics: Optional[TrainingMetrics] = None
    if "metrics" in metadata:
        m = metadata["metrics"]
        metrics = TrainingMetrics(
            rmse=_safe_float(m.get("rmse")) if m.get("rmse") is not None else None,
            mape=_safe_float(m.get("mape")) if m.get("mape") is not None else None,
            r2=_safe_float(m.get("r2")) if m.get("r2") is not None else None,
            data_size=int(m.get("data_size", 0)),
        )

    return ModelStatusResponse(
        model_name=metadata.get("model_name", "DurationPredictor"),
        version=metadata.get("version"),
        trained_at=metadata.get("trained_at"),
        metrics=metrics,
        training_data_size=int(metadata.get("data_size", 0)),
        is_ready=is_ready,
        message=None if is_ready else "Modell noch nicht trainiert. POST /api/v1/ml/train ausführen.",
    )


# ---------------------------------------------------------------------------
# Data quality dashboard
# ---------------------------------------------------------------------------


@router.get(
    "/data-quality",
    response_model=DataQualityResponse,
    summary="Datenqualitäts-Dashboard für ML-Training",
)
@require_permission(Permission.ML_VIEW_STATS)
async def get_data_quality(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataQualityResponse:
    """
    Analyse the completeness of ML-relevant fields across completed orders.

    The readiness_score is a weighted average of field coverage rates:
    - actual_hours: 40%
    - order_type:   20%
    - complexity:   20%
    - metal_type:   10%
    - weight:       10%
    """
    # Only completed/delivered orders are training candidates
    completed_stmt = select(func.count(Order.id)).where(
        Order.status.in_(["completed", "delivered"])
    )
    total_completed = (await db.execute(completed_stmt)).scalar_one() or 0

    async def _count_not_null(column) -> int:  # type: ignore[type-arg]
        stmt = select(func.count(Order.id)).where(
            Order.status.in_(["completed", "delivered"]),
            column.is_not(None),
        )
        return (await db.execute(stmt)).scalar_one() or 0

    with_hours = await _count_not_null(Order.actual_hours)
    with_order_type = await _count_not_null(Order.order_type)
    with_complexity = await _count_not_null(Order.complexity_rating)
    with_metal_type = await _count_not_null(Order.metal_type)
    with_weight = await _count_not_null(Order.estimated_weight_g)

    def _pct(n: int) -> float:
        return round(n / total_completed, 4) if total_completed else 0.0

    # Weighted readiness score
    readiness = (
        _pct(with_hours) * 0.40
        + _pct(with_order_type) * 0.20
        + _pct(with_complexity) * 0.20
        + _pct(with_metal_type) * 0.10
        + _pct(with_weight) * 0.10
    )

    field_coverage = [
        FieldCoverage(
            field_name="actual_hours",
            total_records=total_completed,
            populated_records=with_hours,
            coverage_pct=round(_pct(with_hours) * 100, 1),
        ),
        FieldCoverage(
            field_name="order_type",
            total_records=total_completed,
            populated_records=with_order_type,
            coverage_pct=round(_pct(with_order_type) * 100, 1),
        ),
        FieldCoverage(
            field_name="complexity_rating",
            total_records=total_completed,
            populated_records=with_complexity,
            coverage_pct=round(_pct(with_complexity) * 100, 1),
        ),
        FieldCoverage(
            field_name="metal_type",
            total_records=total_completed,
            populated_records=with_metal_type,
            coverage_pct=round(_pct(with_metal_type) * 100, 1),
        ),
        FieldCoverage(
            field_name="estimated_weight_g",
            total_records=total_completed,
            populated_records=with_weight,
            coverage_pct=round(_pct(with_weight) * 100, 1),
        ),
    ]

    recommendation: Optional[str] = None
    if total_completed < 20:
        recommendation = (
            f"Erst {total_completed} abgeschlossene Aufträge vorhanden. "
            "Mindestens 20 werden für ein zuverlässiges Training empfohlen."
        )
    elif _pct(with_hours) < 0.5:
        recommendation = (
            "Weniger als 50 % der abgeschlossenen Aufträge haben tatsächliche Stunden "
            "(actual_hours). Bitte Zeiterfassung konsequent abschließen."
        )
    elif readiness < 0.6:
        recommendation = (
            "Datenqualität noch nicht ausreichend für zuverlässige Vorhersagen. "
            "Auftragstyp und Komplexität bei der Auftragserfassung angeben."
        )

    return DataQualityResponse(
        total_completed_orders=total_completed,
        orders_with_actual_hours=with_hours,
        orders_with_order_type=with_order_type,
        orders_with_complexity_rating=with_complexity,
        orders_with_metal_type=with_metal_type,
        orders_with_estimated_weight=with_weight,
        readiness_score=round(readiness, 4),
        field_coverage=field_coverage,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Activity statistics
# ---------------------------------------------------------------------------


@router.get(
    "/activity-stats",
    response_model=list[ActivityDurationStats],
    summary="Zeitstatistiken pro Aktivität",
)
@require_permission(Permission.ML_VIEW_STATS)
async def get_activity_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityDurationStats]:
    """Return mean, median, std and P95 duration in minutes per activity type."""
    # Pull all completed time entries with a recorded duration
    result = await db.execute(
        select(TimeEntry)
        .where(TimeEntry.duration_minutes.is_not(None))
        .options(selectinload(TimeEntry.activity))
    )
    entries = result.scalars().all()

    # Group by activity_id
    from collections import defaultdict
    import statistics

    by_activity: dict[int, dict] = defaultdict(lambda: {"durations": [], "activity": None})
    for entry in entries:
        aid = entry.activity_id
        by_activity[aid]["durations"].append(_safe_float(entry.duration_minutes))
        if entry.activity and by_activity[aid]["activity"] is None:
            by_activity[aid]["activity"] = entry.activity

    stats_list: list[ActivityDurationStats] = []
    for aid, data in by_activity.items():
        durations = data["durations"]
        activity = data["activity"]
        if not durations:
            continue

        sorted_d = sorted(durations)
        n = len(sorted_d)
        mean = statistics.mean(sorted_d)
        median = statistics.median(sorted_d)
        std = statistics.stdev(sorted_d) if n > 1 else 0.0
        p95_idx = max(0, int(n * 0.95) - 1)
        p95 = sorted_d[p95_idx]

        stats_list.append(
            ActivityDurationStats(
                activity_id=aid,
                activity_name=activity.name if activity else f"Aktivität {aid}",
                activity_category=activity.category if activity else None,
                sample_count=n,
                mean_minutes=round(mean, 1),
                median_minutes=round(median, 1),
                std_minutes=round(std, 1),
                p95_minutes=round(p95, 1),
                min_minutes=round(sorted_d[0], 1),
                max_minutes=round(sorted_d[-1], 1),
            )
        )

    return sorted(stats_list, key=lambda s: s.sample_count, reverse=True)


@router.get(
    "/activity-stats/{activity_id}",
    response_model=ActivityDetailResponse,
    summary="Detaillierte Statistiken für eine Aktivität",
)
@require_permission(Permission.ML_VIEW_STATS)
async def get_activity_stats_detail(
    activity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActivityDetailResponse:
    """Detailed statistics for a single activity including per-complexity breakdown."""
    import statistics

    # Check activity exists
    act_result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = act_result.scalar_one_or_none()
    if activity is None:
        raise HTTPException(status_code=404, detail=f"Aktivität {activity_id} nicht gefunden.")

    # Fetch all completed entries for this activity
    entries_result = await db.execute(
        select(TimeEntry).where(
            TimeEntry.activity_id == activity_id,
            TimeEntry.duration_minutes.is_not(None),
        )
    )
    entries = entries_result.scalars().all()

    durations = [_safe_float(e.duration_minutes) for e in entries]

    if not durations:
        return ActivityDetailResponse(
            activity_id=activity_id,
            activity_name=activity.name,
            activity_category=activity.category,
            sample_count=0,
            mean_minutes=0.0,
            median_minutes=0.0,
            std_minutes=0.0,
            p95_minutes=0.0,
            min_minutes=0.0,
            max_minutes=0.0,
            per_complexity=[],
        )

    sorted_d = sorted(durations)
    n = len(sorted_d)
    p95_idx = max(0, int(n * 0.95) - 1)

    # Per-complexity breakdown
    from collections import defaultdict

    by_complexity: dict[int, list[float]] = defaultdict(list)
    for entry in entries:
        if entry.complexity_rating is not None:
            by_complexity[entry.complexity_rating].append(
                _safe_float(entry.duration_minutes)
            )

    per_complexity = []
    for rating in sorted(by_complexity.keys()):
        d = by_complexity[rating]
        per_complexity.append(
            ComplexityBreakdown(
                complexity_rating=rating,
                sample_count=len(d),
                mean_minutes=round(statistics.mean(d), 1),
                median_minutes=round(statistics.median(d), 1),
            )
        )

    return ActivityDetailResponse(
        activity_id=activity_id,
        activity_name=activity.name,
        activity_category=activity.category,
        sample_count=n,
        mean_minutes=round(statistics.mean(sorted_d), 1),
        median_minutes=round(statistics.median(sorted_d), 1),
        std_minutes=round(statistics.stdev(sorted_d) if n > 1 else 0.0, 1),
        p95_minutes=round(sorted_d[p95_idx], 1),
        min_minutes=round(sorted_d[0], 1),
        max_minutes=round(sorted_d[-1], 1),
        per_complexity=per_complexity,
    )
