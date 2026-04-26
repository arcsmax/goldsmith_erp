"""
Integration test for Bug #6 — GET /api/v1/users/ must exclude the GDPR
anonymisation sentinel user (``deleted@sentinel.invalid``).

The sentinel was inserted by migration ``20260417_anonymize_user`` so that
anonymised records can keep a non-NULL FK target. It is *infrastructure
data*, not a real workshop user, and its synthetic PII (e-mail
``deleted@sentinel.invalid`` — RFC 2606 reserved; first name ``<deleted>``
— deliberately violates the standard ``Name`` regex) makes Pydantic
``ResponseValidationError`` blow up on serialisation if it leaks into the
list endpoint. Pre-fix this caused a 500 on every admin's first page load.

Post-fix expectation:
    * ``GET /api/v1/users/`` returns 200 and a JSON list.
    * The sentinel row (id=0 / e-mail ``deleted@sentinel.invalid``) is
      filtered out at the service layer so it never reaches the response
      validator.
    * Real users are still listed.

Validators stay strict — the bug is "list contains data that should never
reach the response model", not "the validator is too tight".
"""
from datetime import datetime

import pytest
from httpx import AsyncClient

from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.models import UserRole
from goldsmith_erp.services.user_service import (
    SENTINEL_EMAIL,
    SENTINEL_FIRST_NAME,
    SENTINEL_PASSWORD_HASH,
)

pytestmark = pytest.mark.asyncio


USERS_PATH = "/api/v1/users/"


async def _seed_sentinel(db_session) -> UserModel:
    """Insert the GDPR sentinel directly so tests don't depend on the migration."""
    sentinel = UserModel(
        email=SENTINEL_EMAIL,
        hashed_password=SENTINEL_PASSWORD_HASH,
        first_name=SENTINEL_FIRST_NAME,
        last_name=None,
        role=UserRole.VIEWER,
        is_active=False,
        is_deleted=True,
        deleted_at=datetime.utcnow(),
        tenant_id=None,
        created_at=datetime.utcnow(),
    )
    db_session.add(sentinel)
    await db_session.commit()
    await db_session.refresh(sentinel)
    return sentinel


class TestUsersListExcludesSentinel:
    """``GET /users/`` must hide the GDPR anonymisation sentinel."""

    async def test_list_returns_200_when_sentinel_present(
        self,
        authenticated_client: AsyncClient,
        db_session,
        admin_user: UserModel,
    ):
        """Pre-fix: response validator chokes on the sentinel and returns 500.
        Post-fix: list returns 200 even when the sentinel exists in the DB."""
        await _seed_sentinel(db_session)

        resp = await authenticated_client.get(USERS_PATH)

        assert resp.status_code == 200, (
            f"Expected 200 (sentinel excluded from list), got "
            f"{resp.status_code}: {resp.text}"
        )

    async def test_sentinel_not_in_response_payload(
        self,
        authenticated_client: AsyncClient,
        db_session,
        admin_user: UserModel,
    ):
        """The sentinel email/name must never appear in the response."""
        sentinel = await _seed_sentinel(db_session)

        resp = await authenticated_client.get(USERS_PATH)
        assert resp.status_code == 200
        payload = resp.json()

        emails = {user["email"] for user in payload}
        ids = {user["id"] for user in payload}

        assert SENTINEL_EMAIL not in emails, (
            f"Sentinel email leaked into response: {payload}"
        )
        assert sentinel.id not in ids, (
            f"Sentinel user id {sentinel.id} leaked into response: {payload}"
        )

    async def test_real_users_still_listed_with_sentinel_present(
        self,
        authenticated_client: AsyncClient,
        db_session,
        admin_user: UserModel,
        goldsmith_user: UserModel,
    ):
        """Filtering the sentinel must not hide legitimate users."""
        await _seed_sentinel(db_session)

        resp = await authenticated_client.get(USERS_PATH)
        assert resp.status_code == 200
        payload = resp.json()
        ids = {user["id"] for user in payload}

        assert admin_user.id in ids, "admin user missing from list"
        assert goldsmith_user.id in ids, "goldsmith user missing from list"
