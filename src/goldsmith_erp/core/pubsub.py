# src/goldsmith_erp/core/pubsub.py
"""Redis connection pool and event publishing.

Subscribing and WebSocket fan-out live in ``core/ws_manager.py`` (one
subscriber per process, role-safe hints). This module only publishes.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as redis

from goldsmith_erp.core.config import settings

logger = logging.getLogger(__name__)

# BE-20: without timeouts a packet-dropping Redis makes every request hang
# on connect (token revocation runs on every authenticated request).
REDIS_CONNECT_TIMEOUT_SECONDS = 0.5
REDIS_SOCKET_TIMEOUT_SECONDS = 1.0
PUBLISH_ATTEMPTS = 3
PUBLISH_BACKOFF_SECONDS = 0.5

# Create a shared Redis pool from URL in settings
# Build Redis URL if not provided
redis_url = (
    str(settings.REDIS_URL)
    if settings.REDIS_URL
    else f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
)

_redis_pool = redis.ConnectionPool.from_url(
    redis_url,
    decode_responses=True,
    socket_connect_timeout=REDIS_CONNECT_TIMEOUT_SECONDS,
    socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
)


@asynccontextmanager
async def get_redis_client() -> AsyncIterator[redis.Redis]:
    """
    Acquire a Redis client instance from the connection pool with proper cleanup.

    Usage:
        async with get_redis_client() as client:
            await client.publish("channel", "message")
    """
    client = redis.Redis(connection_pool=_redis_pool)
    try:
        yield client
    finally:
        await client.close()


async def publish_event(channel: str, message: str) -> bool:
    """Publish a message to Redis. Retries with backoff. Never raises.

    Returns True when Redis accepted the message and False after the final
    failed attempt, so callers can tell the user that live updates did not
    go out (BE-20: the old ``None`` return made those paths dead code). A
    Redis outage must never bring down the application.
    """
    for attempt in range(PUBLISH_ATTEMPTS):
        try:
            async with get_redis_client() as client:
                await client.publish(channel, message)
            return True
        except Exception as exc:
            if attempt < PUBLISH_ATTEMPTS - 1:
                logger.warning(
                    "Redis publish retry",
                    extra={
                        "channel": channel,
                        "attempt": attempt + 1,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(PUBLISH_BACKOFF_SECONDS * (2**attempt))
            else:
                logger.error(
                    "Redis publish failed",
                    extra={
                        "channel": channel,
                        "attempts": PUBLISH_ATTEMPTS,
                        "error": str(exc),
                    },
                )
    return False
