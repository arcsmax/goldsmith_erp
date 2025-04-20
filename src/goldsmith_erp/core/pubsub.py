import asyncio
import redis.asyncio as redis

redis_url = "redis://localhost:6379"
pub = redis.Redis.from_url(redis_url)
sub = pub.pubsub()

async def publish_event(channel: str, message: str) -> None:
    await pub.publish(channel, message)

async def subscribe_and_forward(ws: WebSocket, channel: str):
    await sub.subscribe(channel)
    try:
        while True:
            msg = await sub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg:
                await ws.send_text(msg["data"].decode())
            await asyncio.sleep(0.1)
    finally:
        await sub.unsubscribe(channel)