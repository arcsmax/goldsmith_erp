"""
Unit tests for the /auth/refresh endpoint and decode_token_allowing_grace_window.

Tests cover:
- Refresh with a valid (not-yet-expired) token returns a new token
- Refresh with a token expired within the 5-minute grace window succeeds
- Refresh with a token expired beyond the grace window returns 401
- Refresh with a structurally invalid / tampered token returns 401
- Refresh with no token provided returns 401
- Refresh for an inactive user returns 403
- decode_token_allowing_grace_window unit-level edge cases
"""
import pytest
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError

from goldsmith_erp.core.security import (
    create_access_token,
    decode_token_allowing_grace_window,
    ALGORITHM,
    REFRESH_GRACE_SECONDS,
)
from goldsmith_erp.core.config import settings


# ---------------------------------------------------------------------------
# Helper: manufacture tokens with arbitrary exp offsets
# ---------------------------------------------------------------------------


def _token_with_exp_offset(user_id: int, offset_seconds: int) -> str:
    """
    Create a JWT whose expiry is now + offset_seconds.

    A negative offset produces an already-expired token.
    """
    exp = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    payload = {"sub": str(user_id), "exp": exp}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def _valid_token(user_id: int) -> str:
    return create_access_token(
        data={"sub": str(user_id)},
        expires_delta=timedelta(hours=1),
    )


# ===========================================================================
# Tests: decode_token_allowing_grace_window (pure unit, no DB)
# ===========================================================================


class TestDecodeTokenAllowingGraceWindow:
    """Unit tests for the grace-window decode helper in security.py."""

    def test_valid_token_decodes_successfully(self):
        """A non-expired token must decode without error."""
        token = _valid_token(user_id=1)
        payload = decode_token_allowing_grace_window(token)
        assert payload["sub"] == "1"

    def test_token_expired_within_grace_window_succeeds(self):
        """Token expired 1 minute ago (well within 5-minute grace) must decode."""
        token = _token_with_exp_offset(user_id=42, offset_seconds=-60)
        payload = decode_token_allowing_grace_window(token)
        assert payload["sub"] == "42"

    def test_token_expired_at_grace_boundary_succeeds(self):
        """Token expired exactly at the grace window edge must still decode.

        REFRESH_GRACE_SECONDS is 300 (5 min). A token expired 299 s ago is
        within the window; we use 290 s for a small safety margin against
        clock drift inside the test run.
        """
        safe_margin = 10  # seconds
        token = _token_with_exp_offset(
            user_id=7, offset_seconds=-(REFRESH_GRACE_SECONDS - safe_margin)
        )
        payload = decode_token_allowing_grace_window(token)
        assert payload["sub"] == "7"

    def test_token_expired_beyond_grace_window_raises_jwt_error(self):
        """Token expired well beyond the grace window must raise JWTError."""
        beyond = REFRESH_GRACE_SECONDS + 60  # 6 minutes ago — outside the window
        token = _token_with_exp_offset(user_id=99, offset_seconds=-beyond)

        with pytest.raises(JWTError):
            decode_token_allowing_grace_window(token)

    def test_structurally_invalid_token_raises_jwt_error(self):
        """A garbage string must raise JWTError."""
        with pytest.raises(JWTError):
            decode_token_allowing_grace_window("not.a.real.token")

    def test_tampered_signature_raises_jwt_error(self):
        """Altering the signature portion must raise JWTError."""
        token = _valid_token(user_id=5)
        # Replace last 5 chars of the signature with 'XXXXX'
        tampered = token[:-5] + "XXXXX"

        with pytest.raises(JWTError):
            decode_token_allowing_grace_window(tampered)

    def test_token_signed_with_wrong_key_raises_jwt_error(self):
        """Token signed with a different secret must raise JWTError."""
        payload = {"sub": "10", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
        wrong_key_token = jwt.encode(payload, "completely-wrong-secret", algorithm=ALGORITHM)

        with pytest.raises(JWTError):
            decode_token_allowing_grace_window(wrong_key_token)

    def test_token_without_exp_claim_raises_jwt_error(self):
        """A token lacking the 'exp' claim must be rejected."""
        # jose does not add exp unless told to; encode raw payload without it
        no_exp_token = jwt.encode({"sub": "3"}, settings.SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(JWTError, match="no expiry"):
            decode_token_allowing_grace_window(no_exp_token)

    def test_decoded_payload_preserves_sub_claim(self):
        """The returned payload must carry the original 'sub' claim unchanged."""
        user_id = 123
        token = _valid_token(user_id=user_id)
        payload = decode_token_allowing_grace_window(token)
        assert payload.get("sub") == str(user_id)


# ===========================================================================
# Tests: /auth/refresh HTTP endpoint
# ===========================================================================


@pytest.mark.asyncio
class TestRefreshEndpoint:
    """Integration-style tests for POST /api/v1/auth/refresh via ASGI client."""

    async def test_refresh_with_valid_token_returns_new_token(
        self, client, sample_user
    ):
        """A currently valid token must be exchanged for a fresh access_token."""
        token = _valid_token(user_id=sample_user.id)

        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        # The new token must be a different string (fresh expiry)
        assert data["access_token"] != token

    async def test_refresh_returns_valid_jwt(self, client, sample_user):
        """The returned access_token must be a valid, decodable JWT."""
        token = _valid_token(user_id=sample_user.id)

        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        new_token = response.json()["access_token"]

        payload = jwt.decode(new_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == str(sample_user.id)

    async def test_refresh_sets_httponly_cookie(self, client, sample_user):
        """Successful refresh must set the HttpOnly access_token cookie."""
        token = _valid_token(user_id=sample_user.id)

        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert "access_token" in response.cookies

    async def test_refresh_within_grace_window_succeeds(self, client, sample_user):
        """Token expired 1 minute ago (inside 5-min grace) must refresh successfully."""
        expired_by_one_minute = _token_with_exp_offset(
            user_id=sample_user.id, offset_seconds=-60
        )

        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": f"Bearer {expired_by_one_minute}"},
        )

        assert response.status_code == 200
        assert "access_token" in response.json()

    async def test_refresh_beyond_grace_window_returns_401(self, client, sample_user):
        """Token expired 10 minutes ago (outside 5-min grace) must be rejected."""
        ten_minutes_ago = REFRESH_GRACE_SECONDS + 5 * 60  # 10 min total
        stale_token = _token_with_exp_offset(
            user_id=sample_user.id, offset_seconds=-ten_minutes_ago
        )

        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": f"Bearer {stale_token}"},
        )

        assert response.status_code == 401

    async def test_refresh_with_invalid_token_returns_401(self, client):
        """A structurally invalid token must be rejected with 401."""
        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": "Bearer this.is.garbage"},
        )

        assert response.status_code == 401

    async def test_refresh_with_tampered_token_returns_401(self, client, sample_user):
        """A token with a corrupted signature must return 401."""
        token = _valid_token(user_id=sample_user.id)
        tampered = token[:-5] + "ZZZZZ"

        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": f"Bearer {tampered}"},
        )

        assert response.status_code == 401

    async def test_refresh_with_no_token_returns_401(self, client):
        """Request with no Authorization header and no cookie must return 401."""
        response = await client.post(f"{settings.API_V1_STR}/refresh")

        assert response.status_code == 401

    async def test_refresh_with_wrong_key_token_returns_401(self, client, sample_user):
        """Token signed with a wrong secret key must be rejected."""
        payload = {
            "sub": str(sample_user.id),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        bad_key_token = jwt.encode(payload, "wrong-secret", algorithm=ALGORITHM)

        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": f"Bearer {bad_key_token}"},
        )

        assert response.status_code == 401

    async def test_refresh_with_inactive_user_returns_403(
        self, client, inactive_user
    ):
        """Valid token for a deactivated user account must return 403."""
        token = _valid_token(user_id=inactive_user.id)

        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    async def test_refresh_via_cookie_succeeds(self, client, sample_user):
        """Token supplied via the HttpOnly cookie path must also be accepted."""
        token = _valid_token(user_id=sample_user.id)

        # Set the cookie manually on the client
        client.cookies.set("access_token", token)

        response = await client.post(f"{settings.API_V1_STR}/refresh")

        assert response.status_code == 200
        assert "access_token" in response.json()

        # Clean up the cookie so it does not bleed into subsequent tests
        client.cookies.delete("access_token")

    async def test_refresh_new_token_has_future_expiry(self, client, sample_user):
        """The refreshed token's expiry must be in the future."""
        token = _valid_token(user_id=sample_user.id)

        response = await client.post(
            f"{settings.API_V1_STR}/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        new_token = response.json()["access_token"]

        payload = jwt.decode(new_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["exp"] > datetime.now(timezone.utc).timestamp()
