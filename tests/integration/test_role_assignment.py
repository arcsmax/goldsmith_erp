"""ADMIN-only role assignment; the last active ADMIN cannot be demoted (SEC-F6).

Before this fix there was no API to assign or change a user's role at all —
new users defaulted to VIEWER and only direct SQL could promote or demote
anyone (FINDINGS-REGISTER SEC-F6). `PUT /users/{id}` now accepts an
ADMIN-only `role` field; the write is audit-logged by the existing
`AuditLoggingMiddleware` "users" family (see `services/user_service.py`
`_guard_last_admin_role_change` for the last-admin guard).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import CustomerAuditLog, User, UserRole

USERS_URL = "/api/v1/users"


@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch, db_session):
    """Point AuditLoggingMiddleware's own session factory at the test DB.

    The middleware opens its own ``AsyncSessionLocal()`` (BaseHTTPMiddleware
    cannot take FastAPI `Depends`); without this it would try the production
    Postgres URL and silently swallow the failure. See
    test_audit_logging_middleware.py for the full rationale.
    """
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from sqlalchemy.orm import sessionmaker

    from goldsmith_erp.middleware import audit_logging

    factory = sessionmaker(
        bind=db_session.bind, class_=_AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(audit_logging, "AsyncSessionLocal", factory)


@pytest.mark.asyncio
class TestRoleAssignment:
    async def test_admin_can_change_role_and_it_is_audit_logged(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        goldsmith_user: User,
        db_session: AsyncSession,
    ):
        response = await client.put(
            f"{USERS_URL}/{goldsmith_user.id}",
            json={"role": "viewer"},
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["role"] == "viewer"

        audit_rows = await db_session.execute(
            select(CustomerAuditLog)
            .filter(CustomerAuditLog.entity == "user")
            .filter(CustomerAuditLog.entity_id == goldsmith_user.id)
            .filter(CustomerAuditLog.action == "updated")
        )
        assert audit_rows.scalars().first() is not None

    async def test_goldsmith_cannot_change_role(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_user: User,
    ):
        response = await client.put(
            f"{USERS_URL}/{viewer_user.id}",
            json={"role": "admin"},
            headers=goldsmith_auth_headers,
        )

        assert response.status_code == 403

    async def test_viewer_cannot_change_role(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        goldsmith_user: User,
    ):
        response = await client.put(
            f"{USERS_URL}/{goldsmith_user.id}",
            json={"role": "admin"},
            headers=viewer_auth_headers,
        )

        assert response.status_code == 403

    async def test_cannot_demote_the_last_active_admin(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        admin_user: User,
    ):
        response = await client.put(
            f"{USERS_URL}/{admin_user.id}",
            json={"role": "goldsmith"},
            headers=admin_auth_headers,
        )

        assert response.status_code == 409

    async def test_demoting_an_admin_succeeds_when_another_admin_remains(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        admin_user: User,
        db_session: AsyncSession,
    ):
        second_admin = User(
            email=f"second_admin_{admin_user.id}@integration-test.example.com",
            hashed_password=get_password_hash("SecondAdmin123!"),
            first_name="Second",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db_session.add(second_admin)
        await db_session.commit()

        response = await client.put(
            f"{USERS_URL}/{admin_user.id}",
            json={"role": "goldsmith"},
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["role"] == "goldsmith"

    async def test_role_unset_leaves_role_unchanged(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        goldsmith_user: User,
    ):
        """A plain profile edit (no `role` key) must not touch the role."""
        response = await client.put(
            f"{USERS_URL}/{goldsmith_user.id}",
            json={"first_name": "Renamed"},
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["role"] == "goldsmith"
        assert response.json()["first_name"] == "Renamed"
