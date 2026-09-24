"""PUT /users/me must re-authenticate before changing credentials (SEC-11).

A session left open on a shared bench tablet must not be enough to change the
account's email or password (and so take the account over permanently).
Name-only profile edits stay possible without the current password.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import User, UserRole

LOGIN_URL = "/api/v1/login/access-token"
ME_URL = "/api/v1/users/me"
PASSWORD = "currentpass123"
NEW_PASSWORD = "brandnew456"


async def _logged_in_user(client: AsyncClient, db: AsyncSession) -> User:
    user = User(
        email=f"me_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash(PASSWORD),
        first_name="Anne",
        last_name="Goldschmied",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    login = await client.post(
        LOGIN_URL, data={"username": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200
    return user


async def _can_login(client: AsyncClient, email: str, password: str) -> bool:
    resp = await client.post(LOGIN_URL, data={"username": email, "password": password})
    return resp.status_code == 200


@pytest.mark.asyncio
class TestCredentialChangeRequiresCurrentPassword:
    async def test_password_change_without_current_password_is_rejected(
        self, client: AsyncClient, fake_redis, db_session: AsyncSession
    ):
        user = await _logged_in_user(client, db_session)

        resp = await client.put(ME_URL, json={"password": NEW_PASSWORD})

        assert resp.status_code == 400
        assert "current_password" in resp.json()["detail"]
        client.cookies.clear()
        assert await _can_login(client, user.email, PASSWORD)

    async def test_password_change_with_wrong_current_password_is_rejected(
        self, client: AsyncClient, fake_redis, db_session: AsyncSession
    ):
        user = await _logged_in_user(client, db_session)

        resp = await client.put(
            ME_URL,
            json={"password": NEW_PASSWORD, "current_password": "wrongpass999"},
        )

        assert resp.status_code == 403
        client.cookies.clear()
        assert await _can_login(client, user.email, PASSWORD)

    async def test_email_change_without_current_password_is_rejected(
        self, client: AsyncClient, fake_redis, db_session: AsyncSession
    ):
        await _logged_in_user(client, db_session)

        resp = await client.put(
            ME_URL, json={"email": f"taken_{uuid.uuid4().hex[:6]}@example.com"}
        )

        assert resp.status_code == 400

    async def test_password_change_with_correct_current_password_succeeds(
        self, client: AsyncClient, fake_redis, db_session: AsyncSession
    ):
        user = await _logged_in_user(client, db_session)

        resp = await client.put(
            ME_URL, json={"password": NEW_PASSWORD, "current_password": PASSWORD}
        )

        assert resp.status_code == 200
        assert "current_password" not in resp.json()
        client.cookies.clear()
        assert await _can_login(client, user.email, NEW_PASSWORD)

    async def test_email_change_with_correct_current_password_succeeds(
        self, client: AsyncClient, fake_redis, db_session: AsyncSession
    ):
        await _logged_in_user(client, db_session)
        new_email = f"new_{uuid.uuid4().hex[:6]}@example.com"

        resp = await client.put(
            ME_URL, json={"email": new_email, "current_password": PASSWORD}
        )

        assert resp.status_code == 200
        assert resp.json()["email"] == new_email

    async def test_name_change_does_not_need_current_password(
        self, client: AsyncClient, fake_redis, db_session: AsyncSession
    ):
        await _logged_in_user(client, db_session)

        resp = await client.put(ME_URL, json={"first_name": "Annegret"})

        assert resp.status_code == 200
        assert resp.json()["first_name"] == "Annegret"

    async def test_unchanged_email_does_not_need_current_password(
        self, client: AsyncClient, fake_redis, db_session: AsyncSession
    ):
        user = await _logged_in_user(client, db_session)

        resp = await client.put(ME_URL, json={"email": user.email, "last_name": "Neu"})

        assert resp.status_code == 200
