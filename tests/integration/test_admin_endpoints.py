"""
Integration tests for admin backup/system endpoints and the health check.

Endpoint coverage:
  POST /api/v1/admin/trigger-backup  — ADMIN only; non-admin gets 403
  GET  /api/v1/admin/system-info     — ADMIN only; non-admin gets 403
  GET  /health                       — public; returns component-level status
  POST /api/v1/admin/notify-backup   — localhost-only; non-localhost is ignored

The health router is included at root level (no /api/v1 prefix), so health
endpoints are at /health, not /api/v1/health.
Admin endpoints bake settings.API_V1_STR into the path directly, so they live
at /api/v1/admin/... despite the router being mounted at root level.
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import User, UserRole


TRIGGER_BACKUP_URL = "/api/v1/admin/trigger-backup"
SYSTEM_INFO_URL = "/api/v1/admin/system-info"
HEALTH_URL = "/health"
NOTIFY_BACKUP_URL = "/api/v1/admin/notify-backup"


# ---------------------------------------------------------------------------
# POST /api/v1/admin/trigger-backup
# ---------------------------------------------------------------------------

class TestTriggerBackup:

    @pytest.mark.asyncio
    async def test_trigger_backup_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.post(TRIGGER_BACKUP_URL)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_trigger_backup_as_goldsmith_returns_403(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """GOLDSMITH is not an ADMIN — get_current_admin_user must reject with 403."""
        response = await client.post(
            TRIGGER_BACKUP_URL,
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_trigger_backup_as_viewer_returns_403(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        response = await client.post(
            TRIGGER_BACKUP_URL,
            headers=viewer_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_trigger_backup_as_admin_returns_202(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """
        ADMIN can trigger a backup.  The backup script will not exist in the
        test environment, so the endpoint returns {"status": "started", "note": ...}
        rather than actually running the script.
        """
        response = await client.post(
            TRIGGER_BACKUP_URL,
            headers=admin_auth_headers,
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "started"

    @pytest.mark.asyncio
    async def test_trigger_backup_response_has_status_field(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Response must always include the 'status' key."""
        response = await client.post(
            TRIGGER_BACKUP_URL,
            headers=admin_auth_headers,
        )
        assert "status" in response.json()


# ---------------------------------------------------------------------------
# GET /api/v1/admin/system-info
# ---------------------------------------------------------------------------

class TestSystemInfo:

    @pytest.mark.asyncio
    async def test_system_info_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.get(SYSTEM_INFO_URL)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_system_info_as_goldsmith_returns_403(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        response = await client.get(
            SYSTEM_INFO_URL,
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_system_info_as_viewer_returns_403(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        response = await client.get(
            SYSTEM_INFO_URL,
            headers=viewer_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_system_info_as_admin_returns_200(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        response = await client.get(
            SYSTEM_INFO_URL,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Top-level sections must be present
        assert "health" in data
        assert "business_metrics" in data
        assert "backup" in data
        assert "request_metrics" in data

    @pytest.mark.asyncio
    async def test_system_info_health_section_has_components(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        response = await client.get(
            SYSTEM_INFO_URL,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        health = response.json()["health"]
        assert "status" in health
        assert "components" in health
        components = health["components"]
        assert "database" in components
        assert "disk" in components
        # Redis may be down in test environment but the key must still be present
        assert "redis" in components


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_endpoint_is_public(self, client: AsyncClient):
        """The /health endpoint must not require authentication."""
        response = await client.get(HEALTH_URL)
        # 200 (healthy/degraded) or 503 (unhealthy) — both are valid outcomes
        assert response.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_health_returns_component_level_status(
        self, client: AsyncClient
    ):
        response = await client.get(HEALTH_URL)
        data = response.json()

        # Top-level fields
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")
        assert "components" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_health_components_include_database_redis_disk(
        self, client: AsyncClient
    ):
        response = await client.get(HEALTH_URL)
        components = response.json()["components"]

        assert "database" in components
        assert "redis" in components
        assert "disk" in components

    @pytest.mark.asyncio
    async def test_health_database_component_has_status_and_latency(
        self, client: AsyncClient
    ):
        response = await client.get(HEALTH_URL)
        db_component = response.json()["components"]["database"]

        assert "status" in db_component
        assert db_component["status"] in ("up", "down")
        assert "latency_ms" in db_component
        assert isinstance(db_component["latency_ms"], (int, float))

    @pytest.mark.asyncio
    async def test_health_disk_component_has_usage_fields(
        self, client: AsyncClient
    ):
        response = await client.get(HEALTH_URL)
        disk = response.json()["components"]["disk"]

        assert "status" in disk
        assert disk["status"] in ("ok", "warning", "critical")
        assert "free_gb" in disk
        assert "total_gb" in disk
        assert "used_percent" in disk

    @pytest.mark.asyncio
    async def test_health_returns_503_when_unhealthy(
        self, client: AsyncClient
    ):
        """
        When the database component is down, the overall status is 'unhealthy'
        and the HTTP response code must be 503.
        """
        from goldsmith_erp.services.system_health_service import SystemHealthService

        unhealthy_report = {
            "status": "unhealthy",
            "components": {
                "database": {"status": "down", "latency_ms": 0.0},
                "redis": {"status": "down", "latency_ms": 0.0, "used_memory_mb": 0.0},
                "disk": {"status": "ok", "free_gb": 10.0, "total_gb": 100.0, "used_percent": 10.0},
            },
            "version": "test",
            "uptime_seconds": 1.0,
            "timestamp": "2026-01-01T00:00:00",
        }

        with patch.object(
            SystemHealthService,
            "get_full_health",
            new=AsyncMock(return_value=unhealthy_report),
        ):
            response = await client.get(HEALTH_URL)

        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# POST /api/v1/admin/notify-backup
# ---------------------------------------------------------------------------

class TestNotifyBackup:
    """
    The notify-backup endpoint is designed to be called by backup.sh over
    localhost with no user authentication.  However, the global
    AuthRequiredMiddleware applies to all routes not in PUBLIC_PATHS or
    PUBLIC_PREFIXES, so requests without a JWT token receive 401 before the
    endpoint handler runs.

    These tests document the current behaviour and verify the intended logic
    (localhost check, notification creation) via an admin-authenticated request
    that passes the middleware.
    """

    @pytest.mark.asyncio
    async def test_notify_backup_without_token_returns_401(
        self, client: AsyncClient
    ):
        """
        The auth middleware blocks unauthenticated callers before the localhost
        check inside the handler fires.  This is the actual runtime behaviour.
        """
        body = {
            "status": "success",
            "filename": "backup_20260101.sql.gz",
            "size_mb": 12.5,
            "message": "Backup completed without errors",
        }
        response = await client.post(NOTIFY_BACKUP_URL, json=body)
        # AuthRequiredMiddleware rejects unauthenticated requests with 401
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_notify_backup_success_creates_notifications_for_admins(
        self, client: AsyncClient, admin_user: User, admin_auth_headers: dict
    ):
        """
        When called with a valid admin token, the handler processes the backup
        result and creates a SYSTEM notification for each active ADMIN user.

        Note: in a production deployment this endpoint would be called without
        a token by backup.sh; a whitelist entry in PUBLIC_PATHS is needed to
        enable true unauthenticated access.
        """
        body = {
            "status": "success",
            "filename": "goldsmith_backup_20260131.sql.gz",
            "size_mb": 8.3,
            "message": "",
        }
        response = await client.post(
            NOTIFY_BACKUP_URL,
            json=body,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        # One admin user exists — at least one notification must be created
        assert data["notifications_created"] >= 1

    @pytest.mark.asyncio
    async def test_notify_backup_failed_creates_warning_notification(
        self, client: AsyncClient, admin_user: User, admin_auth_headers: dict
    ):
        """A failed backup must still create a notification (severity WARNING)."""
        body = {
            "status": "failed",
            "filename": "goldsmith_backup_failed.sql.gz",
            "size_mb": 0.0,
            "message": "Disk full on backup server",
        }
        response = await client.post(
            NOTIFY_BACKUP_URL,
            json=body,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["notifications_created"] >= 1

    @pytest.mark.asyncio
    async def test_notify_backup_empty_body_does_not_crash(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Malformed or empty body must degrade gracefully, not 500."""
        response = await client.post(
            NOTIFY_BACKUP_URL,
            content=b"not-json",
            headers={**admin_auth_headers, "content-type": "application/json"},
        )
        # Endpoint catches JSON parse errors and treats them as empty body
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
