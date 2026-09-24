"""
B3 — Adversarial tests for SEC-11 (current_password required to change
email/password via PUT /users/me).

tests/integration/test_users_me_reauth.py already covers /users/me itself
thoroughly (missing/wrong/correct current_password, name-only change,
unchanged-email no-op). This file targets what that coverage cannot see: a
DIFFERENT route — PUT /users/{user_id} (api/routers/users.py
update_user_by_admin) — that shares the same UserService.update_user() write
path but has NO current_password requirement at all (by design: it's meant
for an admin resetting *another* user's credentials). Because it is gated
only by Permission.USER_EDIT (which ADMIN holds unconditionally, including
against their OWN user_id), an ADMIN can change their OWN email/password
through this endpoint with zero re-authentication — completely bypassing
SEC-11 for the single highest-value account in the system.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.security import create_access_token, get_password_hash, verify_password
from goldsmith_erp.db.models import User, UserRole

USERS_URL = "/api/v1/users"


@pytest_asyncio.fixture
async def fresh_admin(db_session: AsyncSession) -> User:
    user = User(
        email=f"selfedit_admin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("OriginalPass123!"),
        first_name="Self",
        last_name="Edit",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def fresh_admin_headers(fresh_admin: User) -> dict:
    from datetime import timedelta

    token = create_access_token(
        data={"sub": str(fresh_admin.id)}, expires_delta=timedelta(hours=1)
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestAdminSelfEditBypassesSec11:
    async def test_admin_changes_own_password_via_admin_route_without_current_password(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        fresh_admin: User,
        fresh_admin_headers: dict,
    ):
        """/users/me would 400 this (no current_password supplied). The
        admin route accepts it outright because UserUpdate (its schema) has
        no current_password field and the router never checks one."""
        resp = await client.put(
            f"{USERS_URL}/{fresh_admin.id}",
            json={"password": "StolenSessionNewPass456!"},
            headers=fresh_admin_headers,
        )

        await db_session.refresh(fresh_admin)
        password_changed_without_reauth = verify_password(
            "StolenSessionNewPass456!", fresh_admin.hashed_password
        )
        assert not password_changed_without_reauth, (
            "SEC-11 bypass: an ADMIN changed their OWN password via "
            "PUT /users/{their_own_id} (api/routers/users.py "
            "update_user_by_admin, HTTP " + str(resp.status_code) + ") with "
            "NO current_password check at all — the exact re-authentication "
            "PUT /users/me enforces (SEC-11) is completely absent on this "
            "route whenever user_id == current_user.id. A hijacked/XSS'd "
            "ADMIN session (or an unattended unlocked session) can silently "
            "take over the account without ever knowing the current "
            "password."
        )

    async def test_admin_changes_own_email_via_admin_route_without_current_password(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        fresh_admin: User,
        fresh_admin_headers: dict,
    ):
        new_email = f"takeover_{uuid.uuid4().hex[:8]}@attacker.example.com"
        resp = await client.put(
            f"{USERS_URL}/{fresh_admin.id}",
            json={"email": new_email},
            headers=fresh_admin_headers,
        )

        await db_session.refresh(fresh_admin)
        assert fresh_admin.email != new_email, (
            "SEC-11 bypass: an ADMIN changed their OWN login email via the "
            f"admin route (HTTP {resp.status_code}) with no current_password "
            "check — an attacker with a stolen ADMIN session token can "
            "redirect password-reset flows to an email they control, "
            "without ever supplying the account's current password."
        )


@pytest.mark.asyncio
class TestConcurrentPasswordChangeRace:
    async def test_two_concurrent_correct_password_changes_leave_consistent_state(
        self,
        db_session: AsyncSession,
    ):
        """Two truly independent DB sessions (as two real concurrent HTTP
        requests would each get via Depends(get_db)) both re-authenticate
        with the CORRECT starting password and both write a different new
        password at the same time. Neither call should crash or corrupt the
        row; exactly one of the two new passwords must be the one that
        actually works afterwards (last-write-wins is acceptable — silent
        data corruption, a crash, or BOTH passwords working is not).

        Note: httpx's ASGITransport test client shares one AsyncSession
        across "concurrent" requests in this suite's fixtures, which
        SQLAlchemy itself refuses ("session is provisioning a new
        connection; concurrent operations are not permitted") — a test
        harness artifact, not a production code path (production issues one
        session per request). This test drives UserService.update_user
        directly through two independent sessions instead, which is what
        actually races in production.
        """
        from sqlalchemy.orm import sessionmaker

        from goldsmith_erp.core.security import verify_password
        from goldsmith_erp.models.user import UserUpdate
        from goldsmith_erp.services.user_service import UserService
        from tests.conftest import test_engine as _test_engine

        user = User(
            email=f"race_pw_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("StartPass123!"),
            first_name="Race",
            last_name="Condition",
            role=UserRole.GOLDSMITH,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        user_id = user.id

        SessionLocal = sessionmaker(
            bind=_test_engine, class_=AsyncSession, expire_on_commit=False
        )

        async def _change(new_password: str):
            async with SessionLocal() as session:
                try:
                    result = await UserService.update_user(
                        session, user_id, UserUpdate(password=new_password)
                    )
                    return "ok" if result is not None else "not_found"
                except Exception as exc:  # pragma: no cover - diagnostic
                    return f"error:{type(exc).__name__}:{exc}"

        results = await asyncio.gather(
            _change("RaceWinnerA123!"), _change("RaceWinnerB123!")
        )
        assert results == ["ok", "ok"], results

        await db_session.refresh(user)
        matches_a = verify_password("RaceWinnerA123!", user.hashed_password)
        matches_b = verify_password("RaceWinnerB123!", user.hashed_password)
        assert matches_a != matches_b, (
            "expected exactly one of the two concurrent password changes to "
            f"be the final state; matches_a={matches_a} matches_b={matches_b}"
        )
