"""
D — Adversarial test: the RBAC financial-data projection (SEC-01/SEC-09,
api/role_projection.py) only guards REST responses. It never touches the
real-time WebSocket channel, which rebroadcasts the RAW order_updates Redis
payload — including Order.price — to every authenticated WebSocket client
regardless of role.

Evidence read directly from source (not inferred):

- main.py `_authenticate_websocket` only decodes the JWT and returns a
  user_id; it never loads the user's role or calls has_permission /
  ensure_financial_view. `/ws/orders` accepts ANY authenticated user.
- core/pubsub.py `subscribe_and_forward` does
  `async for msg in _subscribe(channel): await ws.send_text(msg["data"])`
  — a byte-for-byte relay with zero filtering.
- services/order_service.py embeds `"price": str(order.price)` (or
  `None`) directly into the `order_updates` envelope on create, update, and
  `_safe_publish_order_event` (used by every order mutation path).

tests/integration/test_viewer_role_projection.py's 458-line sweep is
REST-only (httpx AsyncClient) and never opens a WebSocket, so this gap is
invisible to that otherwise very thorough coverage.

Test strategy: use the same starlette.testclient.TestClient pattern as
tests/integration/test_websocket_auth.py (real /ws/orders route, DB
override, Redis mocked out), but instead of no-op'ing subscribe_and_forward
entirely, patch only core.pubsub._subscribe (the Redis listen() generator)
to yield ONE real order_updates envelope containing a price — exactly the
bytes order_service.py would have published — and let the REAL,
unmodified subscribe_and_forward relay it. A VIEWER-role connection then
reads it straight off the socket.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from goldsmith_erp.core.security import create_access_token, get_password_hash
from goldsmith_erp.db.session import get_db
from goldsmith_erp.main import app

FINANCIAL_ORDER_UPDATE_ENVELOPE = json.dumps(
    {
        "action": "create",
        "source": "manual",
        "order_id": 4242,
        "status": "completed",
        "data": {
            "id": 4242,
            "customer_id": 7,
            "title": "Verlobungsring Solitaer 1ct",
            "created_at": "2026-09-25T00:00:00",
            "status": "completed",
            "price": "8950.00",
        },
    }
)


async def _fake_subscribe(channel: str):
    """Stand-in for core.pubsub._subscribe: yields exactly one real-shaped
    Redis pubsub message, the way redis-py's pubsub().listen() would, then
    stops. Lets the REAL subscribe_and_forward (imported into main.py) run
    unmodified, so this test exercises the actual relay code path."""
    yield {"type": "message", "data": FINANCIAL_ORDER_UPDATE_ENVELOPE}


@pytest.fixture()
def ws_client(db_session):
    from tests.integration.conftest import _override_get_db_factory

    app.dependency_overrides[get_db] = _override_get_db_factory(db_session)
    with patch("goldsmith_erp.core.pubsub._subscribe", new=_fake_subscribe):
        yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestWebSocketBypassesFinancialRbac:
    async def test_viewer_receives_order_price_over_ws_orders(
        self, ws_client, db_session
    ):
        """VIEWER cannot see Order.price on ANY REST endpoint (SEC-01,
        api/role_projection.py; enforced end-to-end in
        tests/integration/test_viewer_role_projection.py). Confirm they
        receive it verbatim over /ws/orders anyway."""
        from goldsmith_erp.db.models import User, UserRole

        viewer = User(
            email=f"ws_leak_viewer_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("pw"),
            first_name="WS",
            last_name="Viewer",
            role=UserRole.VIEWER,
            is_active=True,
        )
        db_session.add(viewer)
        await db_session.commit()
        await db_session.refresh(viewer)

        token = create_access_token(
            data={"sub": str(viewer.id)}, expires_delta=timedelta(hours=1)
        )

        with ws_client.websocket_connect(f"/ws/orders?token={token}") as ws:
            raw = ws.receive_text()

        payload = json.loads(raw)
        leaked_price = payload.get("data", {}).get("price")
        assert leaked_price != "8950.00", (
            "CRITICAL RBAC BYPASS: a VIEWER-role WebSocket client received "
            "Order.price ('8950.00') over /ws/orders. api/role_projection.py "
            "(SEC-01/SEC-09) strips financial fields from every REST "
            "response for callers lacking Permission.FINANCIAL_VIEW, but "
            "main.py's /ws/orders endpoint "
            "(_authenticate_websocket) performs NO role/permission check "
            "at all beyond 'is this JWT valid', and core/pubsub.py "
            "subscribe_and_forward relays the raw order_updates Redis "
            "payload verbatim to every connected socket. Any authenticated "
            "VIEWER can watch live order prices, customer IDs and titles in "
            "real time, completely bypassing the RBAC financial-data fix "
            "for the entire order lifecycle (create/update/location-change "
            "all publish 'price' — services/order_service.py)."
        )

    async def test_admin_route_confirms_the_envelope_really_carries_price(
        self, ws_client, db_session
    ):
        """Sanity check the fixture itself isn't the source of the finding:
        an ADMIN (who IS entitled to price) receives the identical payload
        — proving /ws/orders draws no distinction between the two roles at
        all, rather than this being a VIEWER-specific parsing accident."""
        from goldsmith_erp.db.models import User, UserRole

        admin = User(
            email=f"ws_leak_admin_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("pw"),
            first_name="WS",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)

        token = create_access_token(
            data={"sub": str(admin.id)}, expires_delta=timedelta(hours=1)
        )

        with ws_client.websocket_connect(f"/ws/orders?token={token}") as ws:
            raw = ws.receive_text()

        assert raw == FINANCIAL_ORDER_UPDATE_ENVELOPE
