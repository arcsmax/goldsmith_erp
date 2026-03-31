# src/goldsmith_erp/core/cache.py
"""
Cache-aside helper backed by the shared Redis connection pool.

Design rules:
- Reuses _redis_pool from pubsub.py — no second connection pool.
- All cache keys are prefixed with "cache:" to separate them from
  pub/sub channel names.
- Serialisation is plain JSON; callers are responsible for providing
  a serialisable fetch result and a compatible deserialiser.
- Redis errors never bubble up to callers: the module logs the error
  and falls back to calling fetch_fn directly.
- Invalidation always happens AFTER a successful DB commit.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional, TypeVar

from goldsmith_erp.core.pubsub import get_redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL constants (seconds)
# ---------------------------------------------------------------------------
MATERIALS_TTL: int = 300   # 5 minutes
ACTIVITIES_TTL: int = 600  # 10 minutes

# ---------------------------------------------------------------------------
# Key prefix
# ---------------------------------------------------------------------------
_PREFIX = "cache:"

T = TypeVar("T")


def _full_key(key: str) -> str:
    """Return the fully-qualified Redis key with the cache prefix."""
    return f"{_PREFIX}{key}"


# ---------------------------------------------------------------------------
# Core cache-aside helper
# ---------------------------------------------------------------------------

async def get_cached(
    key: str,
    ttl: int,
    fetch_fn: Callable[[], Awaitable[T]],
    serialise: Callable[[T], str] = json.dumps,
    deserialise: Callable[[str], T] = json.loads,
) -> T:
    """
    Cache-aside read: return the cached value when present, otherwise call
    fetch_fn, store the result, and return it.

    Args:
        key:          Logical cache key (without the "cache:" prefix).
        ttl:          Time-to-live in seconds for new cache entries.
        fetch_fn:     Async callable that returns the authoritative value
                      when the cache is cold or unavailable.
        serialise:    Convert the fetched value to a JSON string for storage.
                      Defaults to json.dumps.
        deserialise:  Convert the stored JSON string back to the value type.
                      Defaults to json.loads.

    Returns:
        The cached or freshly fetched value.

    Raises:
        Any exception raised by fetch_fn is propagated to the caller.
        Redis errors are caught, logged, and the function falls back to
        fetch_fn transparently.
    """
    full_key = _full_key(key)

    # --- Try cache read -------------------------------------------------------
    try:
        async with get_redis_client() as redis:
            raw = await redis.get(full_key)
            if raw is not None:
                logger.debug("Cache hit", extra={"cache_key": key})
                return deserialise(raw)
            logger.debug("Cache miss", extra={"cache_key": key})
    except Exception as exc:
        logger.warning(
            "Redis cache read failed, falling back to DB",
            extra={"cache_key": key, "error": str(exc)},
        )

    # --- Fetch from source ----------------------------------------------------
    value = await fetch_fn()

    # --- Populate cache -------------------------------------------------------
    try:
        async with get_redis_client() as redis:
            await redis.setex(full_key, ttl, serialise(value))
            logger.debug("Cache populated", extra={"cache_key": key, "ttl": ttl})
    except Exception as exc:
        logger.warning(
            "Redis cache write failed, continuing without cache",
            extra={"cache_key": key, "error": str(exc)},
        )

    return value


# ---------------------------------------------------------------------------
# Invalidation helpers
# ---------------------------------------------------------------------------

async def invalidate(key: str) -> None:
    """
    Delete a single cache entry.

    Call this AFTER a successful DB commit so the cache is never cleared
    before the authoritative data is persisted.

    Args:
        key: Logical cache key (without the "cache:" prefix).
    """
    full_key = _full_key(key)
    try:
        async with get_redis_client() as redis:
            deleted = await redis.delete(full_key)
            logger.debug(
                "Cache invalidated",
                extra={"cache_key": key, "deleted": deleted},
            )
    except Exception as exc:
        logger.warning(
            "Redis cache invalidation failed",
            extra={"cache_key": key, "error": str(exc)},
        )


async def invalidate_prefix(prefix: str) -> None:
    """
    Delete all cache entries whose key starts with the given prefix.

    Uses SCAN to avoid blocking the Redis event loop on large keyspaces.
    The prefix is combined with the module-level "cache:" prefix so callers
    pass logical prefixes only (e.g. "materials").

    Args:
        prefix: Logical key prefix (without the "cache:" prefix).
    """
    full_prefix = _full_key(prefix)
    pattern = f"{full_prefix}*"
    deleted_count = 0

    try:
        async with get_redis_client() as redis:
            async for key in redis.scan_iter(match=pattern, count=100):
                await redis.delete(key)
                deleted_count += 1
        logger.debug(
            "Cache prefix invalidated",
            extra={"prefix": prefix, "deleted": deleted_count},
        )
    except Exception as exc:
        logger.warning(
            "Redis cache prefix invalidation failed",
            extra={"prefix": prefix, "error": str(exc)},
        )
