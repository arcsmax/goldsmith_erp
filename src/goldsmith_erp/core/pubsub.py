# src/goldsmith_erp/core/pubsub.py

import asyncio
from typing import AsyncIterator

import redis.asyncio as redis
from fastapi import WebSocket

from goldsmith_erp.core.config import settings

# Create a shared Redis pool from URL in settings
# Build Redis URL if not provided
redis_url = str(settings.REDIS_URL) if settings.REDIS_URL else f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

_redis_pool = redis.ConnectionPool.from_url(
    redis_url,
    decode_responses=True
)

async def get_redis_connection() -> redis.Redis:
    """
    Acquire a Redis client instance from the connection pool.
    """
    return redis.Redis(connection_pool=_redis_pool)


async def publish_event(channel: str, message: str) -> None:
    """
    Publish a message to the given Redis channel.
    """
    redis_client = await get_redis_connection()
    await redis_client.publish(channel, message)


async def _subscribe(channel: str) -> AsyncIterator[dict]:
    """
    Internal helper to yield parsed Redis messages.
    """
    client = await get_redis_connection()
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(channel)

    try:
        # Loop forever, yielding each message dict as it arrives
        async for msg in pubsub.listen():
            if msg.get("type") == "message":
                yield msg
    finally:
        await pubsub.unsubscribe(channel)


async def subscribe_and_forward(
    ws: WebSocket, channel: str
) -> None:
    """
    Subscribe to Redis channel and forward each message to WebSocket.
    Cleans up on disconnect or error.
    """
    # ensure WS type hint
    await ws.accept()
    try:
        async for msg in _subscribe(channel):
            data = msg["data"]
            # forward only the data payload
            await ws.send_text(data)
    except asyncio.CancelledError:
        # Subscription cancelled; let caller handle cleanup
        raise
    except Exception as exc:
        # Log or handle other errors if desired
        print(f"Redis subscription error: {exc}")
    finally:
        print(f"Unsubscribed from Redis channel: {channel}")