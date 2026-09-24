"""W2-13 / FE-08 / BE-20 — authenticated WebSocket fan-out.

One socket per browser session (``/ws/events``). The process-wide
``RealtimeHub`` holds a single Redis subscription and routes each event to
the right users:

* ``order_updates``          → every connected staff socket, as an
  invalidation hint (no price / customer data on the wire).
* ``time_tracking_updates``  → only the sockets of ``payload["user_id"]``.
* ``notifications:{uid}``    → only the sockets of ``uid``.

Redis is replaced by an in-memory broker (``_FakeBroker``) so the tests run
without a Redis server. All sockets share one blocking portal (one event
loop), exactly like one uvicorn worker.
"""

from __future__ import annotations

import asyncio
import json
import queue
from datetime import timedelta
from typing import Any, Iterator

import anyio
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from goldsmith_erp.core import ws_manager
from goldsmith_erp.core.security import create_access_token
from goldsmith_erp.core.token_revocation import blocklist_jti
from goldsmith_erp.db.session import get_db
from goldsmith_erp.main import app

# ---------------------------------------------------------------------------
# In-memory Redis pub/sub stand-in
# ---------------------------------------------------------------------------


class _FakePubSub:
    """Implements the subset of redis.asyncio PubSub the hub uses."""

    def __init__(self, broker: "_FakeBroker") -> None:
        self._broker = broker

    async def subscribe(self, *channels: str) -> None:
        self._broker.channels.update(channels)

    async def psubscribe(self, *patterns: str) -> None:
        self._broker.patterns.update(patterns)

    async def get_message(
        self, ignore_subscribe_messages: bool = True, timeout: float = 1.0
    ) -> dict[str, Any] | None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if self._broker.fail_next_read:
                self._broker.fail_next_read = False
                raise ConnectionError("redis connection lost")
            try:
                return self._broker.messages.get_nowait()
            except queue.Empty:
                if asyncio.get_running_loop().time() >= deadline:
                    return None
                await asyncio.sleep(0.01)

    async def aclose(self) -> None:
        self._broker.closed += 1


class _FakeBroker:
    def __init__(self) -> None:
        self.messages: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self.channels: set[str] = set()
        self.patterns: set[str] = set()
        self.closed = 0
        self.fail_next_read = False

    async def factory(self) -> _FakePubSub:
        return _FakePubSub(self)

    def publish(self, channel: str, payload: dict[str, Any]) -> None:
        is_pattern = channel.startswith("notifications:")
        self.messages.put(
            {
                "type": "pmessage" if is_pattern else "message",
                "pattern": "notifications:*" if is_pattern else None,
                "channel": channel,
                "data": json.dumps(payload),
            }
        )


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _cookie(user_id: int) -> dict[str, str]:
    token = create_access_token(
        data={"sub": str(user_id)}, expires_delta=timedelta(hours=1)
    )
    return {"cookie": f"access_token={token}"}


@pytest.fixture()
def broker(monkeypatch: pytest.MonkeyPatch) -> _FakeBroker:
    fake = _FakeBroker()
    hub = ws_manager.RealtimeHub(
        pubsub_factory=fake.factory,
        heartbeat_interval=3600.0,
        poll_timeout=0.05,
    )
    monkeypatch.setattr(ws_manager, "realtime_hub", hub)
    return fake


@pytest.fixture()
def ws_client(db_session, fake_redis, broker) -> Iterator[TestClient]:
    """TestClient whose sockets share ONE event loop (like one worker)."""
    from tests.integration.conftest import _override_get_db_factory

    app.dependency_overrides[get_db] = _override_get_db_factory(db_session)
    client = TestClient(app, raise_server_exceptions=False)
    with anyio.from_thread.start_blocking_portal(**client.async_backend) as portal:
        client.portal = portal
        try:
            yield client
        finally:
            client.portal = None
            app.dependency_overrides.clear()


ORDER_EVENT = {
    "action": "update",
    "source": "manual",
    "order_id": 42,
    "status": "in_progress",
    "data": {"id": 42, "price": "1332.80", "customer_id": 7, "title": "Ring"},
}


def _timer_event(user_id: int) -> dict[str, Any]:
    return {
        "action": "switch",
        "source": "scan",
        "user_id": user_id,
        "new_entry_id": "e-1",
        "order_id": 42,
        "activity_id": 3,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAuth:
    def test_unauthenticated_connect_rejected(self, ws_client):
        with pytest.raises(WebSocketDisconnect) as exc:
            with ws_client.websocket_connect("/ws/events") as ws:
                ws.receive_text()
        assert exc.value.code == 4001

    def test_invalid_token_rejected(self, ws_client):
        with pytest.raises(WebSocketDisconnect) as exc:
            with ws_client.websocket_connect(
                "/ws/events", headers={"cookie": "access_token=not.a.jwt"}
            ) as ws:
                ws.receive_text()
        assert exc.value.code == 4001

    def test_revoked_token_rejected(self, ws_client, goldsmith_user, fake_redis):
        """A token blocklisted at logout must not open a live channel."""
        from jose import jwt

        from goldsmith_erp.core.config import settings
        from goldsmith_erp.core.security import ALGORITHM

        headers = _cookie(goldsmith_user.id)
        token = headers["cookie"].split("=", 1)[1]
        jti = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])["jti"]
        ws_client.portal.call(blocklist_jti, jti, 3600)

        with pytest.raises(WebSocketDisconnect) as exc:
            with ws_client.websocket_connect("/ws/events", headers=headers) as ws:
                ws.receive_text()
        assert exc.value.code == 4001


class TestFanOut:
    def test_time_tracking_update_reaches_own_socket(
        self, ws_client, broker, goldsmith_user
    ):
        with ws_client.websocket_connect(
            "/ws/events", headers=_cookie(goldsmith_user.id)
        ) as ws:
            broker.publish("time_tracking_updates", _timer_event(goldsmith_user.id))
            message = ws.receive_json()

        assert message["channel"] == "time_tracking_updates"
        assert message["data"]["action"] == "switch"
        assert message["data"]["user_id"] == goldsmith_user.id

    def test_order_update_reaches_socket_as_hint_without_financials(
        self, ws_client, broker, goldsmith_user
    ):
        with ws_client.websocket_connect(
            "/ws/events", headers=_cookie(goldsmith_user.id)
        ) as ws:
            broker.publish("order_updates", ORDER_EVENT)
            message = ws.receive_json()

        assert message["channel"] == "order_updates"
        assert message["data"] == {
            "action": "update",
            "source": "manual",
            "order_id": 42,
            "status": "in_progress",
        }
        assert "price" not in json.dumps(message)

    def test_user_scoped_events_do_not_reach_other_users(
        self, ws_client, broker, goldsmith_user, viewer_user
    ):
        with (
            ws_client.websocket_connect(
                "/ws/events", headers=_cookie(goldsmith_user.id)
            ) as own,
            ws_client.websocket_connect(
                "/ws/events", headers=_cookie(viewer_user.id)
            ) as other,
        ):
            broker.publish("time_tracking_updates", _timer_event(goldsmith_user.id))
            broker.publish(
                f"notifications:{goldsmith_user.id}", {"id": 1, "title": "Neu"}
            )
            broker.publish("order_updates", ORDER_EVENT)

            own_channels = [own.receive_json()["channel"] for _ in range(3)]
            # The first message the other user sees is the broadcast: the
            # timer and notification events for goldsmith_user were skipped.
            other_first = other.receive_json()

        assert own_channels == [
            "time_tracking_updates",
            "notifications",
            "order_updates",
        ]
        assert other_first["channel"] == "order_updates"

    def test_time_tracking_event_without_user_id_is_dropped(
        self, ws_client, broker, goldsmith_user
    ):
        with ws_client.websocket_connect(
            "/ws/events", headers=_cookie(goldsmith_user.id)
        ) as ws:
            broker.publish("time_tracking_updates", {"action": "switch"})
            broker.publish("order_updates", ORDER_EVENT)
            first = ws.receive_json()
        assert first["channel"] == "order_updates"

    def test_one_redis_subscription_for_many_sockets(
        self, ws_client, broker, goldsmith_user, viewer_user
    ):
        with (
            ws_client.websocket_connect(
                "/ws/events", headers=_cookie(goldsmith_user.id)
            ) as a,
            ws_client.websocket_connect(
                "/ws/events", headers=_cookie(viewer_user.id)
            ) as b,
        ):
            broker.publish("order_updates", ORDER_EVENT)
            assert a.receive_json()["channel"] == "order_updates"
            assert b.receive_json()["channel"] == "order_updates"
            assert ws_manager.realtime_hub.subscriber_starts == 1
        assert broker.channels == {"order_updates", "time_tracking_updates"}
        assert broker.patterns == {"notifications:*"}


class TestNoFinancialDataOnTheWire:
    """D.1 / SEC-01: WS messages are invalidation hints only.

    REST applies the role projection (api/role_projection.py); the socket
    must never carry price, cost, rates, design text or customer PII, so a
    VIEWER cannot watch live prices.
    """

    FORBIDDEN = (
        "price",
        "cost",
        "hourly_rate",
        "margin",
        "title",
        "description",
        "customer_id",
        "message",
        "8950.00",
        "Verlobungsring",
    )

    def test_viewer_socket_gets_order_hint_without_financial_fields(
        self, ws_client, broker, viewer_user
    ):
        payload = {
            "action": "create",
            "source": "manual",
            "order_id": 4242,
            "status": "completed",
            "price": "8950.00",
            "material_cost": 1200,
            "hourly_rate": 85,
            "profit_margin": 40,
            "description": "Verlobungsring Solitaer 1ct",
            "data": {
                "id": 4242,
                "customer_id": 7,
                "title": "Verlobungsring Solitaer 1ct",
                "status": "completed",
                "price": "8950.00",
            },
        }
        with ws_client.websocket_connect(
            "/ws/events", headers=_cookie(viewer_user.id)
        ) as ws:
            broker.publish("order_updates", payload)
            raw = ws.receive_text()

        message = json.loads(raw)
        assert message["data"]["order_id"] == 4242
        assert message["data"]["status"] == "completed"
        assert message["data"]["action"] == "create"
        for needle in self.FORBIDDEN:
            assert needle not in raw, f"{needle!r} leaked over the WebSocket"

    def test_notification_event_is_a_hint_without_text(
        self, ws_client, broker, goldsmith_user
    ):
        with ws_client.websocket_connect(
            "/ws/events", headers=_cookie(goldsmith_user.id)
        ) as ws:
            broker.publish(
                f"notifications:{goldsmith_user.id}",
                {
                    "id": 9,
                    "title": "Abholung Verlobungsring",
                    "message": "Frau Muster holt ab, Preis 8950.00",
                    "notification_type": "pickup_reminder",
                    "severity": "info",
                    "related_order_id": 4242,
                    "related_customer_id": 7,
                    "is_read": False,
                    "created_at": "2026-09-25T10:00:00",
                },
            )
            raw = ws.receive_text()

        message = json.loads(raw)
        assert message["channel"] == "notifications"
        assert message["data"]["id"] == 9
        assert message["data"]["related_order_id"] == 4242
        for needle in ("Verlobungsring", "Muster", "8950.00", "customer"):
            assert needle not in raw

    @pytest.mark.parametrize("path", ["/ws/orders", "/ws/notifications/1"])
    def test_legacy_raw_relay_endpoints_are_gone(self, ws_client, path, admin_user):
        """The byte-for-byte relays (/ws/orders leaked Order.price) are removed."""
        with pytest.raises(WebSocketDisconnect):
            with ws_client.websocket_connect(
                path, headers=_cookie(admin_user.id)
            ) as ws:
                ws.receive_text()


class TestLiveness:
    def test_heartbeat_ping_is_sent(self, ws_client, goldsmith_user, monkeypatch):
        monkeypatch.setattr(ws_manager.realtime_hub, "heartbeat_interval", 0.05)
        with ws_client.websocket_connect(
            "/ws/events", headers=_cookie(goldsmith_user.id)
        ) as ws:
            assert ws.receive_json() == {"type": "ping"}

    def test_socket_closes_when_subscriber_dies(
        self, ws_client, broker, goldsmith_user
    ):
        """BE-20: a dead Redis subscription must not leave a silent socket."""
        with ws_client.websocket_connect(
            "/ws/events", headers=_cookie(goldsmith_user.id)
        ) as ws:
            broker.fail_next_read = True
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
        assert exc.value.code == 1011
