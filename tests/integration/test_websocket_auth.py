"""
Integration tests for WebSocket authentication on ``/ws/events``.

Tests cover:
- /ws/events rejects connections without a token (close code 4001)
- /ws/events rejects connections with an invalid JWT (close code 4001)
- /ws/events accepts a valid JWT from the ``access_token`` cookie
- /ws/events still accepts the legacy ``?token=`` query parameter
  (W3-10 removes it)
- the removed raw relays /ws/orders and /ws/notifications/{id} no longer
  accept connections (W2-13; /ws/orders leaked Order.price, SEC-01 / D.1)

Recipient routing is the user id from the token, not a path parameter, so
a user can no longer ask for somebody else's channel. The realtime hub is
replaced by one with an idle in-memory subscriber so no Redis is needed;
fan-out behaviour is covered in test_ws_fanout.py.
"""

import asyncio
from datetime import timedelta
from typing import Any, Optional

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from goldsmith_erp.core import ws_manager
from goldsmith_erp.core.security import create_access_token
from goldsmith_erp.db.session import get_db
from goldsmith_erp.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(user_id: int) -> str:
    """Create a valid JWT for the given user_id."""
    return create_access_token(
        data={"sub": str(user_id)},
        expires_delta=timedelta(hours=1),
    )


class _IdlePubSub:
    """Subscriber that never receives anything (no Redis in tests)."""

    async def subscribe(self, *channels: str) -> None:
        return None

    async def psubscribe(self, *patterns: str) -> None:
        return None

    async def get_message(
        self, ignore_subscribe_messages: bool = True, timeout: float = 1.0
    ) -> Optional[dict[str, Any]]:
        await asyncio.sleep(timeout)
        return None

    async def aclose(self) -> None:
        return None


async def _idle_factory() -> _IdlePubSub:
    return _IdlePubSub()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ws_client(db_session, fake_redis, monkeypatch):
    """
    Starlette synchronous TestClient with DB override and an idle hub.

    Uses ``raise_server_exceptions=False`` so that WebSocket close frames
    from the server do not raise Python exceptions in the test process.
    """
    from tests.integration.conftest import _override_get_db_factory

    monkeypatch.setattr(
        ws_manager,
        "realtime_hub",
        ws_manager.RealtimeHub(
            pubsub_factory=_idle_factory, heartbeat_interval=3600.0, poll_timeout=0.05
        ),
    )
    app.dependency_overrides[get_db] = _override_get_db_factory(db_session)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ===========================================================================
# /ws/events tests
# ===========================================================================


class TestWsEventsAuth:
    """WebSocket authentication tests for /ws/events."""

    def test_ws_events_without_token_rejected(self, ws_client):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with ws_client.websocket_connect("/ws/events") as ws:
                ws.receive_text()
        assert exc_info.value.code == 4001

    def test_ws_events_with_invalid_token_rejected(self, ws_client):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with ws_client.websocket_connect(
                "/ws/events?token=this.is.not.a.valid.jwt"
            ) as ws:
                ws.receive_text()
        assert exc_info.value.code == 4001

    def test_ws_events_with_cookie_token_accepted(self, ws_client, goldsmith_user):
        token = _make_token(goldsmith_user.id)
        with ws_client.websocket_connect(
            "/ws/events", headers={"cookie": f"access_token={token}"}
        ) as ws:
            ws.send_text("pong")
            ws.close()

    def test_ws_events_with_legacy_query_token_accepted(
        self, ws_client, goldsmith_user
    ):
        token = _make_token(goldsmith_user.id)
        with ws_client.websocket_connect(f"/ws/events?token={token}") as ws:
            ws.send_text("pong")
            ws.close()


class TestLegacyEndpointsRemoved:
    @pytest.mark.parametrize("path", ["/ws/orders", "/ws/notifications/{uid}"])
    def test_legacy_endpoint_refuses_connection(self, ws_client, goldsmith_user, path):
        token = _make_token(goldsmith_user.id)
        url = path.format(uid=goldsmith_user.id) + f"?token={token}"
        with pytest.raises(WebSocketDisconnect):
            with ws_client.websocket_connect(url) as ws:
                ws.receive_text()
