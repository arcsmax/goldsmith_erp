"""
Integration tests for permission gating on `GET /api/v1/time-tracking/user/{user_id}`
and on the D-15 manual pause/resume endpoints.

Covers fix item D3 — the endpoint previously relied solely on an in-body
`check_ownership_or_permission` call. It now carries `@require_permission(
Permission.TIME_VIEW_OWN)` so that users with NO time-tracking permissions
at all are rejected by the decorator *before* the ownership ladder runs.

The decorator is the outer gate; the in-body check remains responsible for
"you have the own-view permission but are asking about someone else."
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.permissions import ROLE_PERMISSIONS, Permission
from goldsmith_erp.db.models import TimeEntry, UserRole

pytestmark = pytest.mark.asyncio


async def _running_entry(
    db_session: AsyncSession, order, user, activity, start=None
) -> TimeEntry:
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order.id,
        user_id=user.id,
        activity_id=activity.id,
        start_time=start or datetime.utcnow(),
        origin="manual",
        extra_metadata={},
    )
    db_session.add(entry)
    await db_session.commit()
    return entry


class TestTimeTrackingUserEndpointPermissions:
    """Permission-gate tests for `GET /time-tracking/user/{user_id}`."""

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        """No token at all -> 401 from auth middleware (not the decorator)."""
        resp = await client.get("/api/v1/time-tracking/user/1")
        assert resp.status_code == 401

    async def test_viewer_can_see_own_entries(
        self,
        client: AsyncClient,
        viewer_user,
        viewer_auth_headers,
    ):
        """VIEWER role has TIME_VIEW_OWN and is the resource owner -> 200."""
        resp = await client.get(
            f"/api/v1/time-tracking/user/{viewer_user.id}",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_viewer_cannot_see_other_user_entries(
        self,
        client: AsyncClient,
        viewer_auth_headers,
        admin_user,
    ):
        """
        VIEWER has TIME_VIEW_OWN but not TIME_VIEW_ALL. Requesting another
        user's entries must be rejected by the in-body ownership check
        with the distinctive ladder message.
        """
        resp = await client.get(
            f"/api/v1/time-tracking/user/{admin_user.id}",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403
        # In-body ladder message is distinct from the decorator's generic one.
        assert "TIME_VIEW_ALL" in resp.json()["detail"]

    async def test_admin_with_view_all_can_see_any_user_entries(
        self,
        client: AsyncClient,
        admin_auth_headers,
        viewer_user,
    ):
        """ADMIN has TIME_VIEW_ALL -> 200 for any user_id."""
        resp = await client.get(
            f"/api/v1/time-tracking/user/{viewer_user.id}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_user_without_time_view_own_gets_403_from_decorator(
        self,
        client: AsyncClient,
        viewer_user,
        viewer_auth_headers,
    ):
        """
        The decorator must gate access BEFORE the in-body ownership check.

        Every current role has TIME_VIEW_OWN, so to simulate a user lacking
        it we patch ROLE_PERMISSIONS for VIEWER to an empty list for the
        duration of this single request. Even though the viewer is the
        *owner* of the resource, the decorator must still 403 because
        the permission check runs first.

        This is the key regression test: without the decorator, this
        request would reach the in-body check, which would see
        `current_user.id == user_id` and return 200. With the decorator,
        the request is rejected upstream.
        """
        stripped = dict(ROLE_PERMISSIONS)
        stripped[UserRole.VIEWER] = []  # no permissions at all
        with patch(
            "goldsmith_erp.core.permissions.ROLE_PERMISSIONS",
            stripped,
        ):
            resp = await client.get(
                f"/api/v1/time-tracking/user/{viewer_user.id}",
                headers=viewer_auth_headers,
            )
        assert resp.status_code == 403
        # The decorator's message mentions the missing permission value.
        assert Permission.TIME_VIEW_OWN.value in resp.json()["detail"]


class TestManualPauseResumeEndpoints:
    """D-15: `POST /time-tracking/{id}/pause` and `/resume` (owner or ADMIN,
    409 if already paused / not running). Service-level state machine and
    duration arithmetic are covered in
    `tests/unit/test_interruption_arithmetic.py::TestManualPauseResume`.
    """

    async def test_owner_can_pause_and_gets_409_on_a_second_pause(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )

        resp = await client.post(
            f"/api/v1/time-tracking/{entry.id}/pause", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["is_paused"] is True

        again = await client.post(
            f"/api/v1/time-tracking/{entry.id}/pause", headers=auth_headers
        )
        assert again.status_code == 409
        assert again.json()["code"] == "time_entry.already_paused"

    async def test_admin_can_resume_someone_elses_paused_entry(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        sample_order,
        sample_activity,
        admin_auth_headers,
    ):
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        pause = await client.post(
            f"/api/v1/time-tracking/{entry.id}/pause", headers=admin_auth_headers
        )
        assert pause.status_code == 200

        resume = await client.post(
            f"/api/v1/time-tracking/{entry.id}/resume", headers=admin_auth_headers
        )
        assert resume.status_code == 200
        assert resume.json()["is_paused"] is False

    async def test_resume_without_a_pause_is_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        resp = await client.post(
            f"/api/v1/time-tracking/{entry.id}/resume", headers=auth_headers
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "time_entry.not_paused"

    async def test_pausing_a_stopped_entry_is_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        stop = await client.post(
            f"/api/v1/time-tracking/{entry.id}/stop", headers=auth_headers, json={}
        )
        assert stop.status_code == 200

        resp = await client.post(
            f"/api/v1/time-tracking/{entry.id}/pause", headers=auth_headers
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "time_entry.not_running"

    async def test_a_user_without_time_track_permission_cannot_pause(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        sample_order,
        sample_activity,
        viewer_user,
        viewer_auth_headers,
    ):
        """VIEWER lacks TIME_TRACK entirely, so this 403s at the decorator —
        it can never reach another user's entry, own or not."""
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        resp = await client.post(
            f"/api/v1/time-tracking/{entry.id}/pause", headers=viewer_auth_headers
        )
        assert resp.status_code == 403

    async def test_pause_unknown_entry_is_404(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/time-tracking/does-not-exist/pause", headers=auth_headers
        )
        assert resp.status_code == 404
