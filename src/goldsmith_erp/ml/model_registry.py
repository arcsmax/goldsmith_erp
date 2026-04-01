"""
Model registry for tracking trained ML model versions.

Stores metadata (version, training date, metrics, training size) as a
JSON sidecar file alongside each model directory.  No database required:
the registry is intentionally lightweight and file-system based so it
works without a live database connection during background training jobs.

All file operations fail loudly — callers (background training tasks)
must handle errors explicitly.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Name of the JSON metadata file written next to each model directory.
_REGISTRY_FILENAME = "registry.json"


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


class ModelRegistry:
    """
    File-system backed registry for ML model versions.

    Layout
    ------
    <base_dir>/
        registry.json            — master registry (all versions, all models)
        duration_model/
            v1/
                duration_model.joblib
                label_encoders.joblib
            v2/
                duration_model.joblib
                label_encoders.joblib

    The master ``registry.json`` holds a dict keyed by model_name, each
    containing a list of version records sorted by ``trained_at`` ascending.
    """

    def __init__(self, base_dir: str) -> None:
        """
        Parameters
        ----------
        base_dir:
            Root directory that contains the registry.json file and all
            versioned model sub-directories.  Created if it does not exist.
        """
        self.base_dir = base_dir
        self._registry_path = os.path.join(base_dir, _REGISTRY_FILENAME)
        os.makedirs(base_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_registry(self) -> dict[str, list[dict[str, Any]]]:
        """Load and return the registry dict from disk."""
        if not os.path.exists(self._registry_path):
            return {}
        try:
            with open(self._registry_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError(
                    f"Registry file has unexpected format: {self._registry_path}"
                )
            return data  # type: ignore[return-value]
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Registry file is corrupted ({self._registry_path}): {exc}"
            ) from exc

    def _save_registry(self, data: dict[str, list[dict[str, Any]]]) -> None:
        """Persist the registry dict to disk atomically (write-then-rename)."""
        tmp_path = self._registry_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._registry_path)
        except Exception as exc:
            # Clean up temp file if possible.
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise RuntimeError(
                f"Failed to write registry to {self._registry_path}: {exc}"
            ) from exc

    def _next_version(
        self, registry: dict[str, list[dict[str, Any]]], model_name: str
    ) -> str:
        """Return the next version string (v1, v2, …) for a given model."""
        existing = registry.get(model_name, [])
        return f"v{len(existing) + 1}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_model(
        self,
        model_name: str,
        model_dir: str,
        metrics: dict[str, Any],
        training_data_size: int,
    ) -> str:
        """
        Register a newly trained model version in the registry.

        Parameters
        ----------
        model_name:
            Logical name, e.g. ``"duration_model"``.
        model_dir:
            Absolute path to the directory that contains the saved model
            files (the directory produced by ``DurationPredictor.save_model``).
        metrics:
            Training/evaluation metrics dict from ``DurationPredictor.train()``.
        training_data_size:
            Number of training samples used.

        Returns
        -------
        Version string (e.g. ``"v3"``).

        Raises
        ------
        RuntimeError — on I/O failure.
        """
        registry = self._load_registry()
        version = self._next_version(registry, model_name)

        record: dict[str, Any] = {
            "version": version,
            "trained_at": _utcnow_iso(),
            "model_dir": model_dir,
            "training_data_size": training_data_size,
            "metrics": {
                k: round(v, 6) if isinstance(v, float) else v
                for k, v in metrics.items()
            },
        }

        if model_name not in registry:
            registry[model_name] = []
        registry[model_name].append(record)

        self._save_registry(registry)
        logger.info(
            "Registered model '%s' version %s "
            "(n=%d, RMSE=%.2f, R²=%.3f)",
            model_name,
            version,
            training_data_size,
            float(metrics.get("rmse", 0.0)),
            float(metrics.get("r2", 0.0)),
        )
        return version

    def get_latest_model(self, model_name: str) -> str | None:
        """
        Return the directory path of the most recently trained model version.

        Returns ``None`` if no version has been registered for this model
        (caller must handle the cold-start case gracefully).

        Raises
        ------
        RuntimeError — on I/O failure or corrupted registry.
        """
        registry = self._load_registry()
        versions = registry.get(model_name, [])
        if not versions:
            logger.info(
                "No registered versions for model '%s' (cold-start).", model_name
            )
            return None
        # Versions are appended in chronological order; last is latest.
        latest = versions[-1]
        model_dir = latest["model_dir"]

        if not os.path.isdir(model_dir):
            raise RuntimeError(
                f"Registered model directory for '{model_name}' version "
                f"'{latest['version']}' does not exist on disk: {model_dir}. "
                "The model files may have been deleted. Re-train to recover."
            )
        return model_dir

    def list_versions(self, model_name: str) -> list[dict[str, Any]]:
        """
        Return all registered versions for a model, newest first.

        Each entry contains: version, trained_at, training_data_size, metrics.
        The ``model_dir`` field is intentionally excluded from this public
        view (internal path detail).

        Returns an empty list if no versions are registered.
        """
        registry = self._load_registry()
        versions = registry.get(model_name, [])
        # Return newest first, omit internal path.
        return [
            {
                "version": v["version"],
                "trained_at": v["trained_at"],
                "training_data_size": v["training_data_size"],
                "metrics": v["metrics"],
            }
            for v in reversed(versions)
        ]

    def get_version_dir(self, model_name: str, version: str) -> str | None:
        """
        Return the directory path for a specific named version.

        Returns ``None`` if the version is not found.
        """
        registry = self._load_registry()
        for record in registry.get(model_name, []):
            if record["version"] == version:
                return record["model_dir"]  # type: ignore[return-value]
        return None

    def model_dir_for_version(self, model_name: str, version: str) -> str:
        """
        Build the canonical directory path for a new model version.

        Does NOT create the directory — ``DurationPredictor.save_model``
        will do that.

        Example
        -------
        >>> registry.model_dir_for_version("duration_model", "v3")
        "/path/to/models/duration_model/v3"
        """
        return os.path.join(self.base_dir, model_name, version)
