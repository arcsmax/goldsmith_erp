"""Login rate limits key on the real client IP behind the proxy (SEC-04).

In production every request reaches the backend from the nginx container, so
keying on the TCP peer turned the per-(ip, username) limit into a global one:
one LAN device could lock an account out for the whole workshop. The test
client connects from 127.0.0.1 (a trusted proxy) and sets X-Forwarded-For the
way nginx does.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import User, UserRole

LOGIN_URL = "/api/v1/login/access-token"
PER_ACCOUNT_LIMIT = 5
ATTEMPTS_TO_TRIGGER_LIMIT = PER_ACCOUNT_LIMIT + 2


async def _make_user(db: AsyncSession, password: str) -> User:
    user = User(
        email=f"xff_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash(password),
        first_name="Xff",
        last_name="User",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _via_proxy(client_ip: str) -> dict[str, str]:
    return {"X-Forwarded-For": f"{client_ip}, 10.89.0.4"}


@pytest.mark.asyncio
async def test_attacker_device_cannot_lock_account_for_other_devices(
    client: AsyncClient, db_session: AsyncSession
):
    password = "realpass123"
    user = await _make_user(db_session, password)

    attacker_statuses = []
    for _ in range(ATTEMPTS_TO_TRIGGER_LIMIT):
        resp = await client.post(
            LOGIN_URL,
            data={"username": user.email, "password": "wrong"},
            headers=_via_proxy("192.168.1.66"),
        )
        attacker_statuses.append(resp.status_code)
    assert 429 in attacker_statuses, attacker_statuses

    # The account owner's own device (different real IP) still logs in.
    owner = await client.post(
        LOGIN_URL,
        data={"username": user.email, "password": password},
        headers=_via_proxy("192.168.1.20"),
    )
    assert owner.status_code == 200, owner.status_code
