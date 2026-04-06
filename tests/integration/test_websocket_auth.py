"""
Integration tests for WebSocket authentication.

Tests cover:
- /ws/orders rejects connections without a token (close code 4001)
- /ws/orders rejects connections with an invalid JWT (close code 4001)
- /ws/orders accepts connections with a valid JWT
- /ws/notifications/{user_id} rejects when token user_id != path user_id
- /ws/notifications/{user_id} accepts when token user_id matches path

WebSocket auth is handled by _authenticate_websocket in main.py, which reads
the token from the ``access_token`` cookie or the ``token`` query parameter.
For testing we pass the token as a query parameter.

subscribe_and_forward is patched to a no-op coroutine so tests do not require
a running Redis instance.
"""
import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

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


def _noop_subscribe_and_forward():
    """
    Return an async function that blocks until cancelled.

    Replaces subscribe_and_forward so WebSocket endpoints don't attempt
    to connect to Redis.  The coroutine just sleeps indefinitely — the
    caller (the WS endpoint) cancels it when the connection closes.
    """
    async def _noop(ws, channel):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
    return _noop


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ws_client(db_session):
    """
    Starlette synchronous TestClient with DB override and Redis mock.

    Uses ``raise_server_exceptions=False`` so that WebSocket close frames
    from the server do not raise Python exceptions in the test process.
    """
    from tests.integration.conftest import _override_get_db_factory

    app.dependency_overrides[get_db] = _override_get_db_factory(db_session)
    with patch(
        "goldsmith_erp.core.pubsub.subscribe_and_forward",
        new=_noop_subscribe_and_forward(),
    ), patch(
        "goldsmith_erp.main.subscribe_and_forward",
        new=_noop_subscribe_and_forward(),
    ):
        yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ===========================================================================
# /ws/orders tests
# ===========================================================================


class TestWsOrdersAuth:
    """WebSocket authentication tests for /ws/orders."""

    def test_ws_orders_without_token_rejected(self, ws_client):
        """Connect to /ws/orders with no token — should get closed with code 4001."""
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with ws_client.websocket_connect("/ws/orders") as ws:
                ws.receive_text()
        assert exc_info.value.code == 4001

    def test_ws_orders_with_invalid_token_rejected(self, ws_client):
        """Connect to /ws/orders with an invalid JWT — should close with code 4001."""
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with ws_client.websocket_connect(
                "/ws/orders?token=this.is.not.a.valid.jwt"
            ) as ws:
                ws.receive_text()
        assert exc_info.value.code == 4001

    def test_ws_orders_with_valid_token_accepted(self, ws_client, goldsmith_user):
        """Connect to /ws/orders with a valid JWT — should be accepted."""
        token = _make_token(goldsmith_user.id)
        with ws_client.websocket_connect(f"/ws/orders?token={token}") as ws:
            # Connection accepted — send a message to verify the socket is live
            ws.send_text("ping")
            # Close cleanly from the client side
            ws.close()


# ===========================================================================
# /ws/notifications/{user_id} tests
# ===========================================================================


class TestWsNotificationsAuth:
    """WebSocket authentication tests for /ws/notifications/{user_id}."""

    def test_ws_notifications_wrong_user_rejected(self, ws_client, goldsmith_user):
        """Connect to /ws/notifications/999 with a token for a different user_id.

        The server checks ``authenticated_user_id != user_id`` and closes
        with code 4001 when they don't match.
        """
        from starlette.websockets import WebSocketDisconnect

        token = _make_token(goldsmith_user.id)
        wrong_user_id = goldsmith_user.id + 9999  # guaranteed to be different

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with ws_client.websocket_connect(
                f"/ws/notifications/{wrong_user_id}?token={token}"
            ) as ws:
                ws.receive_text()
        assert exc_info.value.code == 4001

    def test_ws_notifications_correct_user_accepted(self, ws_client, goldsmith_user):
        """Connect to /ws/notifications/{user_id} with a matching token.

        The token's ``sub`` claim must equal the path ``user_id``.
        """
        token = _make_token(goldsmith_user.id)
        with ws_client.websocket_connect(
            f"/ws/notifications/{goldsmith_user.id}?token={token}"
        ) as ws:
            # Connection accepted — send a message to verify the socket is live
            ws.send_text("ping")
            ws.close()
