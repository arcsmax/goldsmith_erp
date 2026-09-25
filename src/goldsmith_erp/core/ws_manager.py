"""Process-wide WebSocket fan-out hub (W2-13 / FE-08 / BE-20 / D.1 / SEC-01).

One Redis subscription per process feeds every connected ``/ws/events``
socket. Each Redis event is routed to the right users and reduced to an
*invalidation hint*: action, entity id, status and timestamps. Prices,
costs, rates, design text and customer PII never go over the socket; the
client refetches through REST, which applies the role projection
(``api/role_projection.py``).

Routing:

=========================  ======================  ==========================
Redis channel              Client ``channel``      Recipients
=========================  ======================  ==========================
``order_updates``          ``order_updates``       every connected user
``time_tracking_updates``  ``time_tracking_updates``  ``payload["user_id"]``
``repair_updates``         ``repair_updates``      every connected user
``job_updates``            ``job_updates``         every connected user
``notifications:{uid}``    ``notifications``       ``uid``
=========================  ======================  ==========================

Liveness: every socket gets ``{"type": "ping"}`` every
``heartbeat_interval`` seconds; a failed send prunes the socket. If the
Redis subscription dies, every socket is closed with 1011 so clients
reconnect instead of sitting on a silent channel.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Optional, Protocol

import redis.asyncio as redis
from fastapi import WebSocket, WebSocketDisconnect

from goldsmith_erp.core.pubsub import redis_url

logger = logging.getLogger(__name__)

ORDER_CHANNEL = "order_updates"
TIME_TRACKING_CHANNEL = "time_tracking_updates"
REPAIR_CHANNEL = "repair_updates"
JOB_CHANNEL = "job_updates"
NOTIFICATION_PATTERN = "notifications:*"
NOTIFICATION_PREFIX = "notifications:"
CLIENT_NOTIFICATION_CHANNEL = "notifications"

SUBSCRIBED_CHANNELS = (
    ORDER_CHANNEL,
    TIME_TRACKING_CHANNEL,
    REPAIR_CHANNEL,
    JOB_CHANNEL,
)

DEFAULT_HEARTBEAT_SECONDS = 30.0
DEFAULT_POLL_TIMEOUT_SECONDS = 1.0
SUBSCRIBER_CONNECT_TIMEOUT_SECONDS = 2.0
CLOSE_CODE_SUBSCRIBER_DOWN = 1011
PING_FRAME = json.dumps({"type": "ping"})

# Whitelists: only these keys survive into a hint. Anything else (price,
# data.*, title, description, customer ids, notes, …) is dropped.
_ORDER_HINT_KEYS = ("action", "source", "order_id", "status", "location")
_TIMER_HINT_KEYS = (
    "action",
    "source",
    "user_id",
    "entry_id",
    "old_entry_id",
    "new_entry_id",
    "order_id",
    "activity_id",
    "switched_at",
    "started_at",
    "stopped_at",
)
_NOTIFICATION_HINT_KEYS = (
    "id",
    "notification_type",
    "severity",
    "related_order_id",
    "is_read",
    "created_at",
)
_REPAIR_HINT_KEYS = (
    "action",
    "repair_id",
    "repair_number",
    "status",
    "new_status",
    "photo_id",
    "phase",
    "timestamp",
)
_JOB_HINT_KEYS = ("job_id", "kind", "status", "timestamp")


class PubSubLike(Protocol):
    async def subscribe(self, *channels: str) -> Any: ...

    async def psubscribe(self, *patterns: str) -> Any: ...

    async def get_message(
        self, ignore_subscribe_messages: bool = ..., timeout: float = ...
    ) -> Optional[dict[str, Any]]: ...

    async def aclose(self) -> Any: ...


PubSubFactory = Callable[[], Awaitable[PubSubLike]]


@dataclass(frozen=True)
class RoutedEvent:
    """A hint ready to send, plus who may receive it (None = everyone)."""

    frame: str
    user_ids: Optional[frozenset[int]]


def _pick(payload: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: payload[key] for key in keys if key in payload}


def _frame(channel: str, data: dict[str, Any]) -> str:
    return json.dumps({"channel": channel, "data": data})


def _as_user_id(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def route_event(channel: str, raw: str) -> Optional[RoutedEvent]:
    """Turn a raw Redis event into a role-safe hint and its recipients.

    Returns None for malformed payloads, unknown channels and user-scoped
    events without a valid user id (fail closed: never broadcast them).
    """
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Dropping non-JSON realtime event", extra={"channel": channel})
        return None
    if not isinstance(payload, dict):
        logger.warning("Dropping non-object realtime event", extra={"channel": channel})
        return None

    if channel == ORDER_CHANNEL:
        return RoutedEvent(_frame(channel, _pick(payload, _ORDER_HINT_KEYS)), None)

    if channel == TIME_TRACKING_CHANNEL:
        user_id = _as_user_id(payload.get("user_id"))
        if user_id is None:
            logger.warning(
                "Dropping time-tracking event without user_id",
                extra={"channel": channel, "action": payload.get("action")},
            )
            return None
        hint = _pick(payload, _TIMER_HINT_KEYS)
        return RoutedEvent(_frame(channel, hint), frozenset({user_id}))

    if channel == REPAIR_CHANNEL:
        return RoutedEvent(_frame(channel, _pick(payload, _REPAIR_HINT_KEYS)), None)

    if channel == JOB_CHANNEL:
        return RoutedEvent(_frame(channel, _pick(payload, _JOB_HINT_KEYS)), None)

    if channel.startswith(NOTIFICATION_PREFIX):
        user_id = _as_user_id(channel[len(NOTIFICATION_PREFIX) :])
        if user_id is None:
            return None
        hint = _pick(payload, _NOTIFICATION_HINT_KEYS)
        return RoutedEvent(
            _frame(CLIENT_NOTIFICATION_CHANNEL, hint), frozenset({user_id})
        )

    return None


class _RedisSubscription:
    """Dedicated subscriber connection; closing it also closes its client.

    No ``socket_timeout`` here on purpose: the subscriber waits for
    messages via ``get_message(timeout=…)``; the short read timeout of the
    shared request pool would kill an idle subscription.
    """

    def __init__(self) -> None:
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=SUBSCRIBER_CONNECT_TIMEOUT_SECONDS,
            health_check_interval=int(DEFAULT_HEARTBEAT_SECONDS),
        )
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)

    async def subscribe(self, *channels: str) -> None:
        await self._pubsub.subscribe(*channels)

    async def psubscribe(self, *patterns: str) -> None:
        await self._pubsub.psubscribe(*patterns)

    async def get_message(
        self, ignore_subscribe_messages: bool = True, timeout: float = 1.0
    ) -> Optional[dict[str, Any]]:
        message = await self._pubsub.get_message(
            ignore_subscribe_messages=ignore_subscribe_messages, timeout=timeout
        )
        return dict(message) if message else None

    async def aclose(self) -> None:
        try:
            await self._pubsub.aclose()
        finally:
            await self._client.aclose()


async def _default_pubsub_factory() -> PubSubLike:
    return _RedisSubscription()


class RealtimeHub:
    """Tracks sockets per user and runs one Redis subscriber for all of them."""

    def __init__(
        self,
        pubsub_factory: Optional[PubSubFactory] = None,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_SECONDS,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT_SECONDS,
    ) -> None:
        self._pubsub_factory = pubsub_factory or _default_pubsub_factory
        self.heartbeat_interval = heartbeat_interval
        self.poll_timeout = poll_timeout
        self._connections: dict[int, set[WebSocket]] = {}
        self._subscriber: Optional[asyncio.Task[None]] = None
        self.subscriber_starts = 0

    # ------------------------------------------------------------------
    # Connection bookkeeping
    # ------------------------------------------------------------------

    @property
    def connection_count(self) -> int:
        return sum(len(sockets) for sockets in self._connections.values())

    def _register(self, user_id: int, websocket: WebSocket) -> None:
        sockets = self._connections.get(user_id, set())
        self._connections = {**self._connections, user_id: sockets | {websocket}}
        if self._subscriber is None or self._subscriber.done():
            self.subscriber_starts += 1
            self._subscriber = asyncio.create_task(self._run_subscriber())

    def _discard(self, user_id: int, websocket: WebSocket) -> None:
        remaining = self._connections.get(user_id, set()) - {websocket}
        others = {
            uid: sockets for uid, sockets in self._connections.items() if uid != user_id
        }
        self._connections = {**others, user_id: remaining} if remaining else others

    async def _unregister(self, user_id: int, websocket: WebSocket) -> None:
        self._discard(user_id, websocket)
        if self.connection_count == 0:
            await self._stop_subscriber()

    async def _stop_subscriber(self) -> None:
        task, self._subscriber = self._subscriber, None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Fan-out
    # ------------------------------------------------------------------

    def _targets(
        self, user_ids: Optional[frozenset[int]]
    ) -> list[tuple[int, WebSocket]]:
        return [
            (uid, ws)
            for uid, sockets in self._connections.items()
            if user_ids is None or uid in user_ids
            for ws in sockets
        ]

    async def dispatch(self, channel: str, raw: str) -> int:
        """Route one Redis event; returns the number of sockets reached."""
        event = route_event(channel, raw)
        if event is None:
            return 0
        delivered = 0
        for user_id, websocket in self._targets(event.user_ids):
            try:
                await websocket.send_text(event.frame)
                delivered += 1
            except Exception as exc:  # dead socket → prune, keep fanning out
                logger.info(
                    "Pruning dead WebSocket during fan-out",
                    extra={"user_id": user_id, "error": str(exc)},
                )
                # Bookkeeping only: this runs inside the subscriber task,
                # which must not cancel itself. serve() cleans up the rest.
                self._discard(user_id, websocket)
        return delivered

    async def _run_subscriber(self) -> None:
        pubsub: Optional[PubSubLike] = None
        try:
            pubsub = await self._pubsub_factory()
            await pubsub.subscribe(*SUBSCRIBED_CHANNELS)
            await pubsub.psubscribe(NOTIFICATION_PATTERN)
            logger.info("Realtime hub subscribed to Redis")
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=self.poll_timeout
                )
                if not message or message.get("type") not in ("message", "pmessage"):
                    continue
                await self.dispatch(str(message["channel"]), message["data"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Realtime hub Redis subscription died; closing sockets",
                extra={"error": str(exc), "connections": self.connection_count},
                exc_info=True,
            )
            await self._close_all(CLOSE_CODE_SUBSCRIBER_DOWN)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.aclose()
                except Exception as exc:
                    logger.warning(
                        "Closing Redis pubsub failed", extra={"error": str(exc)}
                    )

    async def _close_all(self, code: int) -> None:
        targets = self._targets(None)
        self._connections = {}
        for user_id, websocket in targets:
            try:
                await websocket.close(code=code, reason="Live-Updates unterbrochen")
            except Exception as exc:
                logger.debug(
                    "Socket already closed",
                    extra={"user_id": user_id, "error": str(exc)},
                )

    # ------------------------------------------------------------------
    # Per-connection loop
    # ------------------------------------------------------------------

    async def _heartbeat(self, websocket: WebSocket) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            await websocket.send_text(PING_FRAME)

    @staticmethod
    async def _drain(websocket: WebSocket) -> None:
        """Read client frames ("pong") until the client goes away."""
        while True:
            await websocket.receive_text()

    async def serve(self, websocket: WebSocket, user_id: int) -> None:
        """Run an accepted socket until it disconnects or stops answering."""
        self._register(user_id, websocket)
        tasks = [
            asyncio.create_task(self._drain(websocket)),
            asyncio.create_task(self._heartbeat(websocket)),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except (asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    pass
                except Exception as exc:
                    logger.info(
                        "WebSocket ended", extra={"user_id": user_id, "error": str(exc)}
                    )
            await self._unregister(user_id, websocket)


realtime_hub = RealtimeHub()
