"""
Duration prediction ML model for goldsmith orders.

Predicts total work hours for a new order using XGBoost regression.
Falls back to a heuristic estimate when no trained model is available
(cold-start case) so callers never receive an exception from the
prediction path.

Decision-Making: security > correctness > performance > convenience.
Fail loudly on training errors; be graceful on prediction cold-start.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional ML dependency guard.
# xgboost and scikit-learn live in [tool.poetry.extras] ml, not the core
# dependencies.  Import them lazily so the module can be imported even when
# the extras are not installed; training will raise ImportError loudly while
# prediction uses the cold-start heuristic path.
# ---------------------------------------------------------------------------
try:
    import joblib
    import pandas as pd
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import KFold, cross_val_score
    from sklearn.preprocessing import LabelEncoder
    from xgboost import XGBRegressor

    _ML_DEPS_AVAILABLE = True
except ImportError as _ml_import_err:
    _ML_DEPS_AVAILABLE = False
    _ML_IMPORT_ERR_MSG = str(_ml_import_err)
    logger.warning(
        "ML dependencies not available (%s). "
        "DurationPredictor will run in cold-start heuristic mode only. "
        "Install with: poetry install --extras ml",
        _ml_import_err,
    )


# ---------------------------------------------------------------------------
# Feature engineering helpers
# ---------------------------------------------------------------------------

# Categorical features that must be encoded before XGBoost training.
CATEGORICAL_FEATURES: list[str] = ["order_type", "metal_type", "complexity"]

# All feature columns used by the model (in order).
FEATURE_COLUMNS: list[str] = [
    "order_type",        # e.g. "ring", "necklace", "repair", "resize"
    "metal_type",        # MetalType enum value string
    "complexity",        # "low", "medium", "high", "very_high"
    "estimated_weight_g",
    "gemstone_count",
    "gemstone_total_carat",
    "has_engraving",
    "scrap_percentage",
    "customer_order_count",  # historical order count for this customer
    "deadline_days",         # days between order creation and deadline (or 0)
]

# Reasonable default when no model is trained and no historical data exists.
_DEFAULT_COLD_START_HOURS = 8.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert value to float, returning default on failure."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_feature_vector(features: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise a raw feature dict into the canonical FEATURE_COLUMNS schema.

    Missing keys are filled with safe defaults so partial feature dicts
    (common during early order creation) still produce a prediction.
    """
    return {
        "order_type": str(features.get("order_type", "unknown")),
        "metal_type": str(features.get("metal_type", "unknown")),
        "complexity": str(features.get("complexity", "medium")),
        "estimated_weight_g": _safe_float(features.get("estimated_weight_g"), 0.0),
        "gemstone_count": _safe_float(features.get("gemstone_count"), 0.0),
        "gemstone_total_carat": _safe_float(features.get("gemstone_total_carat"), 0.0),
        "has_engraving": float(bool(features.get("has_engraving", False))),
        "scrap_percentage": _safe_float(features.get("scrap_percentage"), 5.0),
        "customer_order_count": _safe_float(features.get("customer_order_count"), 0.0),
        "deadline_days": _safe_float(features.get("deadline_days"), 0.0),
    }


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Percentage Error, guarded against division by zero."""
    mask = y_true != 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class DurationPredictor:
    """
    XGBoost regressor for predicting total order work hours.

    Lifecycle
    ---------
    1. Instantiate — loads existing model from disk when model_path provided.
    2. train() — fit on completed orders; saves model + encoders to disk.
    3. predict() — fast (<100 ms) single-order inference.
    4. find_similar_orders() — nearest-neighbour lookup in feature space.

    Cold-start behaviour
    --------------------
    When no model has been trained yet, predict() returns a heuristic
    estimate derived from historical averages (if provided) or the
    _DEFAULT_COLD_START_HOURS constant.  This path NEVER raises.
    """

    MODEL_FILENAME = "duration_model.joblib"
    ENCODERS_FILENAME = "label_encoders.joblib"

    def __init__(self, model_path: str | None = None) -> None:
        self._model: Any | None = None  # XGBRegressor
        self._label_encoders: dict[str, Any] = {}  # LabelEncoder per cat feature
        self._training_metrics: dict[str, float] = {}
        self._training_data_size: int = 0
        self._cold_start_avg: float | None = None  # average from training set

        if model_path is not None:
            try:
                self.load_model(model_path)
                logger.info("DurationPredictor loaded from %s", model_path)
            except FileNotFoundError:
                logger.info(
                    "No existing model at %s — starting fresh (cold-start).",
                    model_path,
                )
            except Exception as exc:
                # Fail loudly: a corrupted model file is a real problem.
                raise RuntimeError(
                    f"Failed to load duration model from {model_path}: {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        features: list[dict[str, Any]],
        targets: list[float],
    ) -> dict[str, Any]:
        """
        Train the XGBoost regressor on completed orders.

        Parameters
        ----------
        features:
            List of feature dicts (one per completed order).  Each dict
            should contain the fields listed in FEATURE_COLUMNS, but
            partial dicts are tolerated via safe defaults.
        targets:
            Corresponding actual work hours per order.

        Returns
        -------
        dict with keys: rmse, mape, r2, cv_rmse_mean, cv_rmse_std,
        training_size, feature_importance.

        Raises
        ------
        ImportError   — ML extras not installed.
        ValueError    — fewer than 10 samples supplied.
        RuntimeError  — any other training failure (fail loudly).
        """
        if not _ML_DEPS_AVAILABLE:
            raise ImportError(
                f"ML dependencies are not installed: {_ML_IMPORT_ERR_MSG}. "
                "Run: poetry install --extras ml"
            )

        n_samples = len(features)
        if n_samples < 10:
            raise ValueError(
                f"Training requires at least 10 samples, got {n_samples}. "
                "At least 100 completed orders are recommended for reliable predictions."
            )

        if len(targets) != n_samples:
            raise ValueError(
                f"features length ({n_samples}) != targets length ({len(targets)})"
            )

        logger.info("Training DurationPredictor on %d samples …", n_samples)

        # Warn if below recommended threshold.
        if n_samples < 100:
            logger.warning(
                "Training on only %d completed orders. "
                "The spec recommends >= 100 for reliable predictions.",
                n_samples,
            )

        try:
            # Normalise feature dicts and build DataFrame.
            normalised = [_extract_feature_vector(f) for f in features]
            df = pd.DataFrame(normalised, columns=FEATURE_COLUMNS)
            y = np.array(targets, dtype=np.float64)

            # Encode categorical columns.
            encoders: dict[str, Any] = {}
            for col in CATEGORICAL_FEATURES:
                le = LabelEncoder()
                df[col] = le.fit_transform(df[col].astype(str))
                encoders[col] = le

            X = df.values.astype(np.float64)

            # Store cold-start average from training data.
            self._cold_start_avg = float(np.mean(y))

            # XGBoost hyperparameters (from spec + reasonable defaults).
            model = XGBRegressor(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                reg_alpha=0.1,
                reg_lambda=1.0,
                subsample=0.8,
                colsample_bytree=0.8,
                objective="reg:squarederror",
                random_state=42,
                n_jobs=-1,
            )

            # 5-fold cross-validation (spec requirement).
            n_folds = min(5, n_samples)
            kf = KFold(n_splits=n_folds, shuffle=True, random_state=42)
            cv_neg_mse = cross_val_score(
                model, X, y, cv=kf, scoring="neg_mean_squared_error"
            )
            cv_rmse = np.sqrt(-cv_neg_mse)

            # Final fit on full dataset.
            model.fit(X, y)

            # Compute training-set metrics.
            y_pred = model.predict(X)
            rmse = float(math.sqrt(mean_squared_error(y, y_pred)))
            mape_val = _mape(y, y_pred)
            r2 = float(r2_score(y, y_pred))

            # Feature importance mapping.
            importance_raw = model.feature_importances_
            feature_importance = {
                col: float(importance_raw[i])
                for i, col in enumerate(FEATURE_COLUMNS)
            }

            metrics: dict[str, Any] = {
                "rmse": rmse,
                "mape": mape_val,
                "r2": r2,
                "cv_rmse_mean": float(cv_rmse.mean()),
                "cv_rmse_std": float(cv_rmse.std()),
                "training_size": n_samples,
                "feature_importance": feature_importance,
            }

            self._model = model
            self._label_encoders = encoders
            self._training_metrics = {
                k: v for k, v in metrics.items() if isinstance(v, float)
            }
            self._training_data_size = n_samples

            logger.info(
                "Training complete — RMSE=%.2fh, MAPE=%.1f%%, R²=%.3f, "
                "CV-RMSE=%.2f±%.2f (n=%d)",
                rmse,
                mape_val,
                r2,
                cv_rmse.mean(),
                cv_rmse.std(),
                n_samples,
            )
            return metrics

        except Exception as exc:
            # Fail loudly — training errors must surface to the caller.
            raise RuntimeError(
                f"DurationPredictor training failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Predict work hours for a single order.

        Always returns a result even when no model is trained (cold-start).

        Returns
        -------
        dict with:
            estimated_hours        float  — point estimate
            confidence_interval    tuple[float, float]  — (lower, upper) 95 %
            confidence_level       float  — 0.0–1.0
            is_cold_start          bool   — True if heuristic was used
        """
        if self._model is None or not _ML_DEPS_AVAILABLE:
            return self._cold_start_predict(features)

        try:
            normalised = _extract_feature_vector(features)
            df = pd.DataFrame([normalised], columns=FEATURE_COLUMNS)

            for col, le in self._label_encoders.items():
                raw_val = str(df[col].iloc[0])
                if raw_val in le.classes_:
                    df[col] = le.transform([raw_val])
                else:
                    # Unseen category — use most common class (index 0).
                    logger.debug(
                        "Unseen category '%s' for feature '%s'; "
                        "defaulting to class index 0.",
                        raw_val,
                        col,
                    )
                    df[col] = 0

            X = df.values.astype(np.float64)

            # Point estimate.
            y_pred = float(self._model.predict(X)[0])
            # Clamp to a physically reasonable range (0.5 h – 500 h).
            y_pred = max(0.5, min(y_pred, 500.0))

            # Confidence interval via ensemble variance.
            # XGBRegressor exposes individual tree predictions via predict()
            # with output_margin is not enough; we use the std of per-tree
            # predictions via the booster's staged output approximation.
            # A simpler but reliable approach: use the CV RMSE as ±1 sigma.
            sigma = self._training_metrics.get("cv_rmse_mean", y_pred * 0.25)
            lower = max(0.5, y_pred - 1.96 * sigma)
            upper = y_pred + 1.96 * sigma

            # Confidence level: higher when CV RMSE is small relative to the
            # prediction and R² is good.
            r2 = self._training_metrics.get("r2", 0.5)
            relative_uncertainty = sigma / max(y_pred, 0.5)
            confidence_level = float(
                np.clip(r2 * (1.0 - min(relative_uncertainty, 1.0)), 0.0, 1.0)
            )

            return {
                "estimated_hours": round(y_pred, 2),
                "confidence_interval": (round(lower, 2), round(upper, 2)),
                "confidence_level": round(confidence_level, 3),
                "is_cold_start": False,
            }

        except Exception as exc:
            # Prediction must never crash the API.  Log loudly and fall back.
            logger.error(
                "DurationPredictor.predict() failed (%s); falling back to "
                "cold-start heuristic.",
                exc,
                exc_info=True,
            )
            result = self._cold_start_predict(features)
            result["prediction_error"] = str(exc)
            return result

    def _cold_start_predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Heuristic estimate when no trained model is available.

        Uses historical average if known, otherwise falls back to the
        default constant.  A wide confidence interval signals uncertainty.
        """
        base = (
            self._cold_start_avg
            if self._cold_start_avg is not None
            else _DEFAULT_COLD_START_HOURS
        )

        # Lightweight complexity adjustment from raw features.
        complexity_map = {"low": 0.6, "medium": 1.0, "high": 1.5, "very_high": 2.2}
        complexity = str(features.get("complexity", "medium")).lower()
        multiplier = complexity_map.get(complexity, 1.0)

        gemstones = _safe_float(features.get("gemstone_count"), 0.0)
        gemstone_bonus = gemstones * 0.5  # ~30 min per stone setting

        estimated = base * multiplier + gemstone_bonus
        estimated = max(0.5, round(estimated, 2))

        # Cold-start: wide interval (±50 %) to signal high uncertainty.
        lower = round(max(0.5, estimated * 0.5), 2)
        upper = round(estimated * 1.5, 2)

        return {
            "estimated_hours": estimated,
            "confidence_interval": (lower, upper),
            "confidence_level": 0.3,  # Low confidence — no trained model.
            "is_cold_start": True,
        }

    # ------------------------------------------------------------------
    # Similar order retrieval
    # ------------------------------------------------------------------

    def find_similar_orders(
        self,
        features: dict[str, Any],
        all_training_data: list[dict[str, Any]],
        top_n: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Return the top_n most similar completed orders by Euclidean feature
        distance, normalised to prevent high-magnitude features dominating.

        Parameters
        ----------
        features:
            Feature dict for the new order.
        all_training_data:
            List of dicts, each with ``features`` (dict) and ``order_id``
            and ``actual_hours`` keys.
        top_n:
            Number of similar orders to return.

        Returns
        -------
        List of dicts: order_id, actual_hours, similarity_score (0–1).
        """
        if not all_training_data:
            return []

        if not _ML_DEPS_AVAILABLE:
            logger.warning(
                "find_similar_orders requires ML deps; returning empty list."
            )
            return []

        try:
            query_vec = _extract_feature_vector(features)

            # Build numeric matrix for all training orders.
            rows = []
            meta = []
            for entry in all_training_data:
                order_features = entry.get("features", {})
                normalised = _extract_feature_vector(order_features)
                # Use only numeric features for distance calculation.
                numeric = [
                    float(normalised["estimated_weight_g"]),
                    float(normalised["gemstone_count"]),
                    float(normalised["gemstone_total_carat"]),
                    float(normalised["has_engraving"]),
                    float(normalised["scrap_percentage"]),
                    float(normalised["customer_order_count"]),
                    float(normalised["deadline_days"]),
                ]
                rows.append(numeric)
                meta.append(
                    {
                        "order_id": entry.get("order_id"),
                        "actual_hours": _safe_float(entry.get("actual_hours"), 0.0),
                    }
                )

            matrix = np.array(rows, dtype=np.float64)

            query_numeric = np.array(
                [
                    float(query_vec["estimated_weight_g"]),
                    float(query_vec["gemstone_count"]),
                    float(query_vec["gemstone_total_carat"]),
                    float(query_vec["has_engraving"]),
                    float(query_vec["scrap_percentage"]),
                    float(query_vec["customer_order_count"]),
                    float(query_vec["deadline_days"]),
                ],
                dtype=np.float64,
            )

            # Normalise columns by std-dev (skip zero-variance columns).
            stds = matrix.std(axis=0)
            stds[stds == 0] = 1.0
            matrix_norm = matrix / stds
            query_norm = query_numeric / stds

            # Euclidean distances.
            diffs = matrix_norm - query_norm
            distances = np.sqrt((diffs ** 2).sum(axis=1))

            # Convert distance to similarity score in [0, 1].
            max_dist = distances.max()
            if max_dist == 0:
                similarity_scores = np.ones(len(distances))
            else:
                similarity_scores = 1.0 - (distances / max_dist)

            # Rank and pick top_n.
            ranked_idx = np.argsort(distances)[:top_n]
            result = []
            for idx in ranked_idx:
                result.append(
                    {
                        "order_id": meta[idx]["order_id"],
                        "actual_hours": round(meta[idx]["actual_hours"], 2),
                        "similarity_score": round(float(similarity_scores[idx]), 3),
                    }
                )
            return result

        except Exception as exc:
            logger.error(
                "find_similar_orders failed: %s", exc, exc_info=True
            )
            raise RuntimeError(
                f"find_similar_orders failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_feature_importance(self) -> dict[str, float]:
        """
        Return feature importance ranking from the trained model.

        Raises RuntimeError if no model has been trained yet.
        """
        if self._model is None:
            raise RuntimeError(
                "No trained model available. Call train() first."
            )
        importance_raw = self._model.feature_importances_
        return {
            col: round(float(importance_raw[i]), 6)
            for i, col in enumerate(FEATURE_COLUMNS)
        }

    def get_model_metrics(self) -> dict[str, Any]:
        """
        Return the latest training metrics.

        Returns an empty dict if no training has occurred.
        """
        return dict(self._training_metrics)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_model(self, directory: str) -> None:
        """
        Persist the trained model and label encoders to ``directory``.

        Raises
        ------
        RuntimeError — if no model has been trained.
        RuntimeError — if the save fails for any I/O reason.
        """
        if self._model is None:
            raise RuntimeError(
                "No trained model to save. Call train() first."
            )
        if not _ML_DEPS_AVAILABLE:
            raise ImportError("joblib is required to save the model.")

        try:
            os.makedirs(directory, exist_ok=True)
            model_path = os.path.join(directory, self.MODEL_FILENAME)
            encoders_path = os.path.join(directory, self.ENCODERS_FILENAME)
            joblib.dump(self._model, model_path)
            joblib.dump(self._label_encoders, encoders_path)
            logger.info("Model saved to %s", directory)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to save model to {directory}: {exc}"
            ) from exc

    def load_model(self, directory: str) -> None:
        """
        Load a previously saved model and label encoders from ``directory``.

        Raises
        ------
        FileNotFoundError — model files not found.
        RuntimeError      — if loading fails for any other reason.
        """
        if not _ML_DEPS_AVAILABLE:
            raise ImportError("joblib is required to load the model.")

        model_path = os.path.join(directory, self.MODEL_FILENAME)
        encoders_path = os.path.join(directory, self.ENCODERS_FILENAME)

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Model file not found: {model_path}"
            )

        try:
            self._model = joblib.load(model_path)
            if os.path.exists(encoders_path):
                self._label_encoders = joblib.load(encoders_path)
            else:
                logger.warning(
                    "Label encoders file not found at %s; "
                    "categorical features will use unseen-category fallback.",
                    encoders_path,
                )
                self._label_encoders = {}
            logger.info("Model loaded from %s", directory)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load model from {directory}: {exc}"
            ) from exc
