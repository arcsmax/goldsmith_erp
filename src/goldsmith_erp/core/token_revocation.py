# src/goldsmith_erp/core/token_revocation.py
"""Redis-backed JWT revocation for the workshop deployment (finding 2.1).

Two complementary mechanisms, chosen to stay minimal for a single-workshop LAN:

1. **Per-jti blocklist** — used on *logout*. We hold the exact token in hand, so
   we blocklist its ``jti`` for the remainder of its life. O(1) write, O(1) check.

2. **Per-user "invalid-before" mark** — used on *password change*. We do NOT
   track the set of outstanding jtis for a user, so enumerating them to blocklist
   each is impossible. Instead we stamp a single ``auth:user:invalid_before:{id}``
   timestamp; any token whose ``iat`` predates the mark is rejected. This revokes
   *all* of a user's tokens with one write, at the cost of one extra Redis read
   per authenticated request. That tradeoff is deliberately preferred over
   per-jti bookkeeping (which would require persisting every issued jti).

Availability: if Redis is unreachable the checks FAIL OPEN by default (accept the
token, log a structured warning) so an internal Redis blip cannot lock the whole
workshop out. Set ``AUTH_REVOCATION_FAIL_CLOSED=true`` to reject instead.
"""

import logging
from datetime import datetime, timezone

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.pubsub import get_redis_client
from goldsmith_erp.core.security import REFRESH_GRACE_SECONDS

logger = logging.getLogger(__name__)

_BLOCKLIST_PREFIX = "auth:jti:blocklist:"
_INVALID_BEFORE_PREFIX = "auth:user:invalid_before:"


def _blocklist_key(jti: str) -> str:
    return f"{_BLOCKLIST_PREFIX}{jti}"


def _invalid_before_key(user_id: str) -> str:
    return f"{_INVALID_BEFORE_PREFIX}{user_id}"


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def remaining_ttl_seconds(payload: dict) -> int:
    """Seconds a token stays usable, incl. the refresh grace window.

    The blocklist entry must outlive the token by the grace window; otherwise a
    token blocklisted at logout could still be exchanged at /refresh during the
    grace period after its own ``exp`` (and after its short blocklist TTL) lapsed.
    Falls back to the full configured lifetime when ``exp`` is absent.
    """
    exp = payload.get("exp")
    if exp is None:
        return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 + REFRESH_GRACE_SECONDS
    remaining = int(float(exp) - _now_ts()) + REFRESH_GRACE_SECONDS
    return max(remaining, 1)


async def blocklist_jti(jti: str, ttl_seconds: int) -> None:
    """Blocklist a single token id for ``ttl_seconds`` (best-effort).

    Never raises — a Redis outage must not break logout. On failure the token
    simply keeps its natural (short) lifetime.
    """
    if not jti:
        return
    try:
        async with get_redis_client() as redis:
            await redis.set(_blocklist_key(jti), "1", ex=max(ttl_seconds, 1))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Could not blocklist token jti in Redis",
            extra={"error": str(exc)},
        )


async def invalidate_user_tokens(user_id: str) -> None:
    """Revoke every outstanding token for ``user_id`` (password-change path).

    Stamps the invalid-before mark at *now*: any token with ``iat`` < now is
    rejected by :func:`is_token_revoked`. The mark self-expires after one token
    lifetime (+grace), by which point every pre-existing token has expired anyway.
    Never raises.
    """
    if not user_id:
        return
    ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 + REFRESH_GRACE_SECONDS
    try:
        async with get_redis_client() as redis:
            await redis.set(
                _invalid_before_key(str(user_id)), str(_now_ts()), ex=max(ttl, 1)
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Could not set invalid-before mark in Redis",
            extra={"error": str(exc), "user_id": str(user_id)},
        )


async def is_token_revoked(payload: dict) -> bool:
    """True if the token is blocklisted or predates its user's invalid-before mark.

    Fails OPEN (returns False) when Redis is unreachable unless
    ``AUTH_REVOCATION_FAIL_CLOSED`` is set — see module docstring.
    """
    jti = payload.get("jti")
    iat = payload.get("iat")
    sub = payload.get("sub")
    try:
        async with get_redis_client() as redis:
            if jti and await redis.exists(_blocklist_key(str(jti))):
                return True
            if sub is not None and iat is not None:
                raw = await redis.get(_invalid_before_key(str(sub)))
                if raw is not None:
                    try:
                        cutoff = float(raw)
                    except (TypeError, ValueError):
                        cutoff = 0.0
                    if float(iat) < cutoff:
                        return True
        return False
    except Exception as exc:
        fail_closed = settings.AUTH_REVOCATION_FAIL_CLOSED
        logger.warning(
            "Token revocation check could not reach Redis; failing %s",
            "CLOSED (rejecting token)" if fail_closed else "OPEN (accepting token)",
            extra={"error": str(exc), "fail_closed": fail_closed},
        )
        return fail_closed
