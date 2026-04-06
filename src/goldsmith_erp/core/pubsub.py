# src/goldsmith_erp/core/pubsub.py

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as redis
from fastapi import WebSocket

from goldsmith_erp.core.config import settings

logger = logging.getLogger(__name__)

# Create a shared Redis pool from URL in settings
# Build Redis URL if not provided
redis_url = str(settings.REDIS_URL) if settings.REDIS_URL else f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

_redis_pool = redis.ConnectionPool.from_url(
    redis_url,
    decode_responses=True
)

@asynccontextmanager
async def get_redis_client():
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


async def publish_event(channel: str, message: str) -> None:
    """Publish a message to Redis. Retries with exponential backoff. Never raises.

    Attempts up to 3 times with 0.5s / 1s delays between retries.
    On final failure the error is logged and the caller continues unaffected —
    a Redis outage must never bring down the application.
    """
    for attempt in range(3):
        try:
            async with get_redis_client() as client:
                await client.publish(channel, message)
                return
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(0.5 * (2 ** attempt))
                logger.warning(f"Redis publish retry {attempt + 1}/3: {e}")
            else:
                logger.error(f"Redis publish failed after 3 attempts: {e}")


async def _subscribe(channel: str) -> AsyncIterator[dict]:
    """
    Internal helper to yield parsed Redis messages with proper cleanup.
    """
    async with get_redis_client() as client:
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(channel)

        try:
            # Loop forever, yielding each message dict as it arrives
            async for msg in pubsub.listen():
                if msg.get("type") == "message":
                    yield msg
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()


async def subscribe_and_forward(
    ws: WebSocket, channel: str
) -> None:
    """
    Subscribe to Redis channel and forward each message to WebSocket.
    Cleans up on disconnect or error.
    """
    # Note: caller is responsible for ws.accept() before invoking this function
    try:
        async for msg in _subscribe(channel):
            data = msg["data"]
            # forward only the data payload
            await ws.send_text(data)
    except asyncio.CancelledError:
        # Subscription cancelled; let caller handle cleanup
        raise
    except Exception as exc:
        # Log error with context
        logger.error(
            "Redis subscription error",
            extra={"channel": channel, "error": str(exc)},
            exc_info=True
        )
    finally:
        logger.debug("Unsubscribed from Redis channel", extra={"channel": channel})