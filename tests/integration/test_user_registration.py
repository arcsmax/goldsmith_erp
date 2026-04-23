"""
Integration tests for the ADMIN-gated user registration endpoint.

Fix item A3 — ``/api/v1/users/register`` was previously listed in
``PUBLIC_PATHS`` and accepted any ``(email, password)`` from unauthenticated
callers, exposing an email-enumeration oracle via the 400 "Email already
registered" branch.

These tests assert the post-fix behaviour:

1. Unauthenticated callers get 401 regardless of whether the email exists
   (oracle closed — 401 is indistinguishable for known vs. unknown emails).
2. Authenticated non-ADMIN callers (e.g. GOLDSMITH) get 403.
3. ADMIN callers can still create users (201).
4. ADMIN callers hitting a duplicate email see the 400/409 signal we keep
   for legitimate admin awareness — this is acceptable because admins are
   already trusted with the user table.

TDD note: tests 1 + 5 MUST fail against HEAD pre-fix (the endpoint returns
201 or 400). After removing ``/api/v1/users/register`` from
``PUBLIC_PATHS`` and adding ``@require_permission(Permission.USER_CREATE)``
to ``register_user``, all tests pass.
"""
import pytest
from httpx import AsyncClient

from goldsmith_erp.db.models import User

pytestmark = pytest.mark.asyncio


REGISTER_PATH = "/api/v1/users/register"

_VALID_PAYLOAD = {
    "email": "new-admin-created@integration-test.example.com",
    "password": "S3cr3tp@ss!",
    "first_name": "Freshly",
    "last_name": "Created",
}


class TestUserRegistrationLockdown:
    """`/users/register` is ADMIN-invitation-only."""

    async def test_unauthenticated_cannot_register(self, client: AsyncClient):
        """Anonymous POST → 401 (no longer a public endpoint)."""
        resp = await client.post(REGISTER_PATH, json=_VALID_PAYLOAD)
        assert resp.status_code == 401, (
            f"Expected 401 (auth required), got {resp.status_code}: {resp.text}"
        )

    async def test_unauthenticated_duplicate_email_returns_401_not_400(
        self, client: AsyncClient, admin_user: User,
    ):
        """Fatal pre-fix bug: duplicate email returned 400 to unauthenticated
        callers, confirming the account exists. Post-fix it must be 401 — the
        auth middleware fires before the handler, so existence cannot leak.

        The ``admin_user`` fixture creates a user with a unique e-mail we can
        re-submit to trigger the pre-fix 'Email already registered' branch.
        """
        payload = {**_VALID_PAYLOAD, "email": admin_user.email}
        resp = await client.post(REGISTER_PATH, json=payload)
        assert resp.status_code == 401, (
            "Unauthenticated callers must see 401 regardless of whether the "
            "email exists — anything else re-opens the enumeration oracle. "
            f"Got {resp.status_code}: {resp.text}"
        )

    async def test_non_admin_cannot_register(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """GOLDSMITH does not have USER_CREATE — must get 403."""
        resp = await client.post(
            REGISTER_PATH,
            json=_VALID_PAYLOAD,
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 403, (
            f"Expected 403 (permission denied), got {resp.status_code}: {resp.text}"
        )

    async def test_admin_can_register(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """ADMIN with USER_CREATE — new email → 201 with the new user body."""
        resp = await client.post(
            REGISTER_PATH,
            json=_VALID_PAYLOAD,
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201, (
            f"Expected 201 (created), got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["email"] == _VALID_PAYLOAD["email"]
        assert body["first_name"] == _VALID_PAYLOAD["first_name"]
        assert body["last_name"] == _VALID_PAYLOAD["last_name"]

    async def test_admin_duplicate_email_returns_400(
        self,
        client: AsyncClient,
        admin_user: User,
        admin_auth_headers: dict,
    ):
        """Admin seeing 400 on duplicate email is acceptable — admins are
        already trusted with the full user table, so there is no oracle to
        protect against here. The only guarantee that matters is that
        unauthenticated callers cannot observe this signal (covered by
        ``test_unauthenticated_duplicate_email_returns_401_not_400``).
        """
        payload = {**_VALID_PAYLOAD, "email": admin_user.email}
        resp = await client.post(
            REGISTER_PATH,
            json=payload,
            headers=admin_auth_headers,
        )
        assert resp.status_code in (400, 409), (
            f"Expected 400/409 duplicate-email signal to admins, got "
            f"{resp.status_code}: {resp.text}"
        )
