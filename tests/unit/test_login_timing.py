"""Login must not leak account existence via response timing (SEC-17).

Before this fix the handler returned 401 before any bcrypt call when the
submitted e-mail matched no user, while a known account's wrong-password
case paid bcrypt's ~250ms cost. That timing gap is an account-enumeration
side channel. The handler must now run `verify_password` against a fixed
dummy hash for the unknown-user branch too, so both cases cost the same.
"""

from unittest.mock import patch

import pytest

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.security import DUMMY_PASSWORD_HASH

LOGIN_URL = f"{settings.API_V1_STR}/login/access-token"


@pytest.mark.asyncio
async def test_unknown_email_runs_dummy_bcrypt_verify_exactly_once(client):
    with patch(
        "goldsmith_erp.api.routers.auth.verify_password", return_value=False
    ) as mock_verify:
        response = await client.post(
            LOGIN_URL,
            data={"username": "nobody-at-all@example.com", "password": "whatever123"},
        )

    assert response.status_code == 401
    mock_verify.assert_called_once()
    _called_password, called_hash = mock_verify.call_args.args
    assert called_hash == DUMMY_PASSWORD_HASH


@pytest.mark.asyncio
async def test_known_email_still_verifies_against_its_own_hash(
    client, sample_user, sample_user_password
):
    """Regression guard: the dummy-hash path must not swallow real logins."""
    with patch(
        "goldsmith_erp.api.routers.auth.verify_password", return_value=True
    ) as mock_verify:
        response = await client.post(
            LOGIN_URL,
            data={"username": sample_user.email, "password": sample_user_password},
        )

    assert response.status_code == 200
    mock_verify.assert_called_once()
    _called_password, called_hash = mock_verify.call_args.args
    assert called_hash == sample_user.hashed_password
    assert called_hash != DUMMY_PASSWORD_HASH
