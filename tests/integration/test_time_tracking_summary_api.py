"""Integration tests for GET /api/v1/time-tracking/summary."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

PARAMS = "start_date=2026-05-12T00:00:00&end_date=2026-05-19T00:00:00"


class TestTimeTrackingSummaryEndpoint:
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/time-tracking/summary?{PARAMS}")
        assert resp.status_code == 401

    async def test_viewer_gets_own_summary_shape(
        self, client: AsyncClient, viewer_auth_headers
    ):
        resp = await client.get(
            f"/api/v1/time-tracking/summary?{PARAMS}", headers=viewer_auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {
            "total_hours", "billable_hours", "entries_count",
            "average_session_minutes", "most_used_activity",
            "comparison_previous_period",
        }
        assert body["entries_count"] == 0  # viewer has no entries

    async def test_viewer_cannot_query_other_user(
        self, client: AsyncClient, viewer_auth_headers, admin_user
    ):
        resp = await client.get(
            f"/api/v1/time-tracking/summary?{PARAMS}&user_id={admin_user.id}",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_admin_can_query_other_user(
        self, client: AsyncClient, admin_auth_headers, viewer_user
    ):
        resp = await client.get(
            f"/api/v1/time-tracking/summary?{PARAMS}&user_id={viewer_user.id}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200

    async def test_invalid_date_range_returns_422(
        self, client: AsyncClient, viewer_auth_headers
    ):
        resp = await client.get(
            "/api/v1/time-tracking/summary"
            "?start_date=2026-05-19T00:00:00&end_date=2026-05-12T00:00:00",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 422
