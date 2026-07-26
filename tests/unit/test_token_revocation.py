"""Unit tests for JWT revocation (finding 2.1).

Covers:
- jti/iat presence and uniqueness on issued access tokens
- remaining_ttl_seconds (includes the refresh grace window)
- blocklist_jti  -> is_token_revoked True
- invalidate_user_tokens (per-user invalid-before mark) semantics
- Redis-down behaviour: fail-open by default, fail-closed when configured

Redis is replaced by the in-memory ``fake_redis`` fixture (see conftest.py);
no fakeredis dependency and no live Redis are involved.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from goldsmith_erp.core import token_revocation as tr
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.security import (
    ALGORITHM,
    REFRESH_GRACE_SECONDS,
    create_access_token,
)


def _decode(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# Token issuance carries jti + iat
# ---------------------------------------------------------------------------


class TestTokenClaims:
    def test_access_token_contains_jti_and_iat(self):
        payload = _decode(create_access_token({"sub": "1"}))
        assert "jti" in payload and "iat" in payload
        assert isinstance(payload["jti"], str) and len(payload["jti"]) == 32
        # Sub-second iat (RFC 7519 permits fractional NumericDate).
        assert isinstance(payload["iat"], (int, float))

    def test_two_tokens_have_distinct_jti(self):
        a = _decode(create_access_token({"sub": "1"}))
        b = _decode(create_access_token({"sub": "1"}))
        assert a["jti"] != b["jti"]

    def test_iat_precedes_exp(self):
        payload = _decode(create_access_token({"sub": "1"}))
        assert payload["iat"] < payload["exp"]


# ---------------------------------------------------------------------------
# remaining_ttl_seconds
# ---------------------------------------------------------------------------


class TestRemainingTtl:
    def test_includes_grace_window(self):
        exp = datetime.now(timezone.utc).timestamp() + 1800  # 30 min out
        ttl = tr.remaining_ttl_seconds({"exp": exp})
        # ~1800s remaining plus the 5-min refresh grace, minus a second of drift
        assert ttl >= 1800 + REFRESH_GRACE_SECONDS - 2

    def test_missing_exp_falls_back_to_full_lifetime(self):
        ttl = tr.remaining_ttl_seconds({})
        assert ttl == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 + REFRESH_GRACE_SECONDS

    def test_never_returns_below_one(self):
        past = datetime.now(timezone.utc).timestamp() - 10_000
        assert tr.remaining_ttl_seconds({"exp": past}) >= 1


# ---------------------------------------------------------------------------
# jti blocklist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestJtiBlocklist:
    async def test_clean_token_not_revoked(self, fake_redis):
        payload = _decode(create_access_token({"sub": "1"}))
        assert await tr.is_token_revoked(payload) is False

    async def test_blocklisted_jti_is_revoked(self, fake_redis):
        payload = _decode(create_access_token({"sub": "1"}))
        await tr.blocklist_jti(payload["jti"], 60)
        assert await tr.is_token_revoked(payload) is True

    async def test_other_jti_unaffected(self, fake_redis):
        revoked = _decode(create_access_token({"sub": "1"}))
        other = _decode(create_access_token({"sub": "1"}))
        await tr.blocklist_jti(revoked["jti"], 60)
        assert await tr.is_token_revoked(other) is False

    async def test_blocklist_empty_jti_is_noop(self, fake_redis):
        await tr.blocklist_jti("", 60)  # must not raise
        assert fake_redis._data == {}


# ---------------------------------------------------------------------------
# per-user invalid-before mark (password change)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInvalidBefore:
    async def test_token_issued_before_mark_is_revoked(self, fake_redis):
        now = datetime.now(timezone.utc).timestamp()
        old_payload = {"sub": "7", "iat": int(now - 60), "jti": "x"}
        await tr.invalidate_user_tokens("7")
        assert await tr.is_token_revoked(old_payload) is True

    async def test_token_issued_after_mark_is_valid(self, fake_redis):
        await tr.invalidate_user_tokens("7")
        future = datetime.now(timezone.utc).timestamp() + 120
        fresh_payload = {"sub": "7", "iat": int(future), "jti": "y"}
        assert await tr.is_token_revoked(fresh_payload) is False

    async def test_mark_scoped_to_single_user(self, fake_redis):
        now = datetime.now(timezone.utc).timestamp()
        await tr.invalidate_user_tokens("7")
        other_user = {"sub": "8", "iat": int(now - 60), "jti": "z"}
        assert await tr.is_token_revoked(other_user) is False


# ---------------------------------------------------------------------------
# Redis-down availability tradeoff
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _dead_redis():
    raise ConnectionError("redis unreachable")
    yield  # pragma: no cover - unreachable, marks this an async generator


@pytest.mark.asyncio
class TestRedisDownBehaviour:
    async def test_fails_open_by_default(self, monkeypatch):
        monkeypatch.setattr(tr, "get_redis_client", _dead_redis)
        monkeypatch.setattr(settings, "AUTH_REVOCATION_FAIL_CLOSED", False)
        payload = _decode(create_access_token({"sub": "1"}))
        # Redis down + fail-open => token accepted (not revoked)
        assert await tr.is_token_revoked(payload) is False

    async def test_fails_closed_when_configured(self, monkeypatch):
        monkeypatch.setattr(tr, "get_redis_client", _dead_redis)
        monkeypatch.setattr(settings, "AUTH_REVOCATION_FAIL_CLOSED", True)
        payload = _decode(create_access_token({"sub": "1"}))
        # Redis down + fail-closed => token rejected (treated as revoked)
        assert await tr.is_token_revoked(payload) is True
