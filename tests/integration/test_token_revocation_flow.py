"""Integration tests for token revocation + login rate limiting (findings 2.1, 2.10).

- Logout blocklists the token: a captured Bearer replay is rejected afterwards.
- Password change sets the invalid-before mark: the old token is rejected, a
  fresh login still works.
- Login rate limiting is keyed on (ip, username): one account being throttled
  behind a shared NAT IP does not throttle a colleague on the same IP.

Redis is the in-memory ``fake_redis`` fixture (conftest.py); the rate limiter is
slowapi's in-memory storage, reset per test by the autouse ``reset_rate_limiters``
fixture. No live Redis and no fakeredis dependency are involved.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import User, UserRole

LOGIN_URL = "/api/v1/login/access-token"
LOGOUT_URL = "/api/v1/logout"
ME_URL = "/api/v1/users/me"


async def _make_user(db: AsyncSession, password: str) -> User:
    user = User(
        email=f"rev_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash(password),
        first_name="Rev",
        last_name="User",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
class TestLogoutRevocation:
    async def test_logout_rejects_bearer_replay(
        self, client: AsyncClient, fake_redis, db_session: AsyncSession
    ):
        password = "loginpass123"
        user = await _make_user(db_session, password)

        login = await client.post(
            LOGIN_URL, data={"username": user.email, "password": password}
        )
        assert login.status_code == 200
        token = login.cookies["access_token"]

        # The captured Bearer token works before logout.
        pre = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        assert pre.status_code == 200

        # Logout blocklists the token's jti (cookie auto-sent by the client).
        logout = await client.post(LOGOUT_URL)
        assert logout.status_code == 200

        # Replaying the still-unexpired token over the header is now rejected.
        client.cookies.clear()
        replay = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        assert replay.status_code == 401


@pytest.mark.asyncio
class TestPasswordChangeRevocation:
    async def test_old_token_rejected_new_login_works(
        self, client: AsyncClient, fake_redis, db_session: AsyncSession
    ):
        old_password = "oldpass123"
        new_password = "newpass456"
        user = await _make_user(db_session, old_password)

        login1 = await client.post(
            LOGIN_URL, data={"username": user.email, "password": old_password}
        )
        assert login1.status_code == 200
        old_token = login1.cookies["access_token"]
        assert (
            await client.get(ME_URL, headers={"Authorization": f"Bearer {old_token}"})
        ).status_code == 200

        # Change the password (authenticated via the auto-sent cookie).
        change = await client.put(ME_URL, json={"password": new_password})
        assert change.status_code == 200

        # The pre-change token is now rejected (iat < invalid-before mark).
        client.cookies.clear()
        replay = await client.get(
            ME_URL, headers={"Authorization": f"Bearer {old_token}"}
        )
        assert replay.status_code == 401

        # A fresh login with the new password succeeds and its token is accepted.
        login2 = await client.post(
            LOGIN_URL, data={"username": user.email, "password": new_password}
        )
        assert login2.status_code == 200
        new_token = login2.cookies["access_token"]
        assert (
            await client.get(ME_URL, headers={"Authorization": f"Bearer {new_token}"})
        ).status_code == 200


@pytest.mark.asyncio
class TestLoginRateLimitPerUser:
    async def test_one_account_throttle_does_not_block_colleague(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        # Two accounts reached from the SAME test-client IP (shared-NAT model).
        password = "sharedpass123"
        user_a = await _make_user(db_session, password)
        user_b = await _make_user(db_session, password)

        # Hammer account A with wrong passwords until it is throttled.
        statuses_a = []
        for _ in range(7):
            resp = await client.post(
                LOGIN_URL, data={"username": user_a.email, "password": "wrong"}
            )
            statuses_a.append(resp.status_code)

        assert 429 in statuses_a, f"account A should be throttled: {statuses_a}"
        # The per-account cap is 5/min, so the first few attempts are real 401s.
        first_throttle = statuses_a.index(429)
        assert first_throttle >= 5, (
            f"account A throttled too early ({first_throttle}); "
            f"the per-account limit should allow 5 attempts: {statuses_a}"
        )
        assert statuses_a[:5] == [401] * 5, statuses_a

        # Account B, same IP, is NOT collateral-damaged by A's throttle: it still
        # gets a real credential check (401 for wrong password, not 429).
        resp_b = await client.post(
            LOGIN_URL, data={"username": user_b.email, "password": "wrong"}
        )
        assert resp_b.status_code == 401, (
            "account B behind the same IP must still get login attempts, "
            f"got {resp_b.status_code}"
        )

        # And a correct password for B logs in successfully.
        ok_b = await client.post(
            LOGIN_URL, data={"username": user_b.email, "password": password}
        )
        assert ok_b.status_code == 200
