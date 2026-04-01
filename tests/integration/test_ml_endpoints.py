"""
Integration tests for ML prediction and monitoring endpoints.

Endpoint coverage:
  POST /api/v1/ml/predict/duration      — heuristic fallback when no model
  GET  /api/v1/ml/predict/order/{id}    — 404 for non-existent order
  POST /api/v1/ml/train                 — ADMIN only (GOLDSMITH gets 403)
  GET  /api/v1/ml/status                — returns model status
  GET  /api/v1/ml/data-quality          — returns completeness metrics
  GET  /api/v1/ml/activity-stats        — returns activity statistics

Permission matrix:
  ML_PREDICT   — ADMIN, GOLDSMITH, VIEWER
  ML_VIEW_STATS — ADMIN, GOLDSMITH, VIEWER
  ML_TRAIN     — ADMIN only
"""
import pytest
from httpx import AsyncClient

ML_BASE = "/api/v1/ml"


# ---------------------------------------------------------------------------
# POST /api/v1/ml/predict/duration
# ---------------------------------------------------------------------------

class TestPredictDuration:
    """No trained model is present in integration tests — heuristic always fires."""

    @pytest.mark.asyncio
    async def test_predict_duration_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.post(f"{ML_BASE}/predict/duration", json={})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_predict_duration_returns_heuristic_when_no_model(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """With no trained model the router falls back to _heuristic_estimate."""
        payload = {
            "order_type": "ring",
            "complexity_rating": 3,
            "metal_type": "gold_18k",
            "estimated_weight_g": 10.0,
        }
        response = await client.post(
            f"{ML_BASE}/predict/duration",
            json=payload,
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_heuristic"] is True
        assert data["model_status"] == "not_trained"
        assert data["estimated_hours"] > 0
        assert data["confidence_interval_low"] < data["estimated_hours"]
        assert data["confidence_interval_high"] > data["estimated_hours"]
        assert data["confidence_level"] in ("low", "medium", "high")
        assert isinstance(data["similar_orders"], list)

    @pytest.mark.asyncio
    async def test_predict_duration_heuristic_with_minimal_fields(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        """Empty body still yields a heuristic estimate (uses defaults)."""
        response = await client.post(
            f"{ML_BASE}/predict/duration",
            json={},
            headers=viewer_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_heuristic"] is True
        # Empty payload → fewer than 2 features → confidence should be "low"
        assert data["confidence_level"] == "low"

    @pytest.mark.asyncio
    async def test_predict_duration_heuristic_confidence_scales_with_features(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """All four key features provided → confidence should be 'high'."""
        payload = {
            "order_type": "bracelet",
            "complexity_rating": 4,
            "metal_type": "silver_925",
            "estimated_weight_g": 20.0,
        }
        response = await client.post(
            f"{ML_BASE}/predict/duration",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["confidence_level"] == "high"

    @pytest.mark.asyncio
    async def test_predict_duration_gemstone_count_increases_estimate(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """Adding gemstones should increase the estimate vs no gemstones."""
        base_payload = {"order_type": "ring", "complexity_rating": 3}
        stone_payload = {**base_payload, "gemstone_count": 10}

        r_base = await client.post(
            f"{ML_BASE}/predict/duration",
            json=base_payload,
            headers=goldsmith_auth_headers,
        )
        r_stone = await client.post(
            f"{ML_BASE}/predict/duration",
            json=stone_payload,
            headers=goldsmith_auth_headers,
        )
        assert r_base.status_code == 200
        assert r_stone.status_code == 200
        assert r_stone.json()["estimated_hours"] > r_base.json()["estimated_hours"]


# ---------------------------------------------------------------------------
# GET /api/v1/ml/predict/order/{order_id}
# ---------------------------------------------------------------------------

class TestPredictDurationForOrder:

    @pytest.mark.asyncio
    async def test_predict_order_nonexistent_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        response = await client.get(
            f"{ML_BASE}/predict/order/99999",
            headers=admin_auth_headers,
        )
        assert response.status_code == 404
        assert "99999" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_predict_order_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.get(f"{ML_BASE}/predict/order/1")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/ml/train
# ---------------------------------------------------------------------------

class TestTrainModel:
    """ML_TRAIN permission is ADMIN-only."""

    @pytest.mark.asyncio
    async def test_train_as_goldsmith_returns_403(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """GOLDSMITH does not have ML_TRAIN permission."""
        response = await client.post(
            f"{ML_BASE}/train",
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_train_as_viewer_returns_403(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        response = await client.post(
            f"{ML_BASE}/train",
            headers=viewer_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_train_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.post(f"{ML_BASE}/train")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_train_as_admin_is_not_forbidden(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """
        ADMIN has ML_TRAIN permission so the request must never return 403.

        In test environments the ML modules may be partially available
        (503 — module unavailable) or may crash internally (500) if the
        MLDataService stub is present but incomplete.  Both are acceptable
        infrastructure outcomes; what is NOT acceptable is a 403 (auth error)
        or a 401 (unauthenticated).
        """
        response = await client.post(
            f"{ML_BASE}/train",
            headers=admin_auth_headers,
        )
        assert response.status_code not in (401, 403)
        # 200 (trained), 503 (module missing), 500 (ML stub incomplete) are all valid
        assert response.status_code in (200, 500, 503)


# ---------------------------------------------------------------------------
# GET /api/v1/ml/status
# ---------------------------------------------------------------------------

class TestModelStatus:

    @pytest.mark.asyncio
    async def test_model_status_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.get(f"{ML_BASE}/status")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_model_status_as_goldsmith_returns_200(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        response = await client.get(
            f"{ML_BASE}/status",
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "model_name" in data
        assert "is_ready" in data
        assert isinstance(data["is_ready"], bool)

    @pytest.mark.asyncio
    async def test_model_status_not_trained_when_no_model(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Without a trained model is_ready must be False."""
        response = await client.get(
            f"{ML_BASE}/status",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # No training has been done in the test environment
        assert data["is_ready"] is False
        assert data["model_name"] == "DurationPredictor"

    @pytest.mark.asyncio
    async def test_model_status_as_viewer_returns_200(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        response = await client.get(
            f"{ML_BASE}/status",
            headers=viewer_auth_headers,
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/ml/data-quality
# ---------------------------------------------------------------------------

class TestDataQuality:

    @pytest.mark.asyncio
    async def test_data_quality_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.get(f"{ML_BASE}/data-quality")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_data_quality_returns_completeness_metrics(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        response = await client.get(
            f"{ML_BASE}/data-quality",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Top-level counters
        assert "total_completed_orders" in data
        assert "orders_with_actual_hours" in data
        assert "orders_with_order_type" in data
        assert "orders_with_complexity_rating" in data
        assert "orders_with_metal_type" in data
        assert "orders_with_estimated_weight" in data

        # Readiness score is a float in [0, 1]
        assert 0.0 <= data["readiness_score"] <= 1.0

        # field_coverage is a list of coverage records
        coverage = data["field_coverage"]
        assert isinstance(coverage, list)
        assert len(coverage) == 5  # five ML feature fields
        field_names = {fc["field_name"] for fc in coverage}
        assert "actual_hours" in field_names
        assert "order_type" in field_names

    @pytest.mark.asyncio
    async def test_data_quality_empty_db_has_zero_completed_orders(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """With a fresh test DB there are no completed orders."""
        response = await client.get(
            f"{ML_BASE}/data-quality",
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_completed_orders"] == 0
        assert data["readiness_score"] == 0.0
        # Recommendation mentions minimum required orders
        assert data["recommendation"] is not None

    @pytest.mark.asyncio
    async def test_data_quality_as_viewer_returns_200(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        response = await client.get(
            f"{ML_BASE}/data-quality",
            headers=viewer_auth_headers,
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/ml/activity-stats
# ---------------------------------------------------------------------------

class TestActivityStats:

    @pytest.mark.asyncio
    async def test_activity_stats_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.get(f"{ML_BASE}/activity-stats")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_activity_stats_returns_list(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        response = await client.get(
            f"{ML_BASE}/activity-stats",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_activity_stats_empty_when_no_time_entries(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """With no completed time entries the list should be empty."""
        response = await client.get(
            f"{ML_BASE}/activity-stats",
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_activity_stats_as_viewer_returns_200(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        response = await client.get(
            f"{ML_BASE}/activity-stats",
            headers=viewer_auth_headers,
        )
        assert response.status_code == 200
