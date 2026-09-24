"""W2-01 / FE-13: ``first_photo_id`` on the orders list projection.

The orders list carries the id of each order's oldest photo so the list can
render a thumbnail via ``/photos/{id}/thumbnail`` without one request per
order. Photos are design IP (DESIGN_VIEW, SEC-09 / GDPR-04): a VIEWER gets
``first_photo_id: null`` even when the order has photos.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, Order, OrderPhoto, OrderStatusEnum, User

ORDERS_URL = "/api/v1/orders/"


@pytest_asyncio.fixture
async def order_with_photos(
    db_session: AsyncSession, test_customer: Customer, goldsmith_user: User
) -> tuple[Order, str]:
    """An order with two photos; returns the order and the OLDEST photo id."""
    order = Order(
        title="W2-01 photo list order",
        description="Ring mit Fotos",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
    )
    db_session.add(order)
    await db_session.flush()
    base = datetime(2026, 9, 1, 10, 0, 0)
    newer = OrderPhoto(
        order_id=order.id,
        file_path="orders/newer.jpg",
        timestamp=base + timedelta(hours=2),
        taken_by=goldsmith_user.id,
    )
    older = OrderPhoto(
        order_id=order.id,
        file_path="orders/older.jpg",
        timestamp=base,
        taken_by=goldsmith_user.id,
    )
    db_session.add_all([newer, older])
    await db_session.commit()
    await db_session.refresh(order)
    await db_session.refresh(older)
    return order, older.id


@pytest_asyncio.fixture
async def order_without_photos(
    db_session: AsyncSession, test_customer: Customer
) -> Order:
    order = Order(
        title="W2-01 no photo order",
        description="Ring ohne Fotos",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


def _find(orders: list[dict], order_id: int) -> dict:
    matching = [o for o in orders if o.get("id") == order_id]
    assert matching, f"order {order_id} missing from list"
    return matching[0]


@pytest.mark.asyncio
async def test_goldsmith_list_carries_oldest_photo_id(
    client: AsyncClient,
    goldsmith_auth_headers: dict,
    order_with_photos: tuple[Order, str],
    order_without_photos: Order,
) -> None:
    order, oldest_id = order_with_photos

    resp = await client.get(ORDERS_URL, headers=goldsmith_auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert _find(body, order.id)["first_photo_id"] == oldest_id
    no_photo = _find(body, order_without_photos.id)
    assert "first_photo_id" in no_photo
    assert no_photo["first_photo_id"] is None


@pytest.mark.asyncio
async def test_viewer_list_gets_null_first_photo_id(
    client: AsyncClient,
    viewer_auth_headers: dict,
    order_with_photos: tuple[Order, str],
) -> None:
    order, _oldest_id = order_with_photos

    resp = await client.get(ORDERS_URL, headers=viewer_auth_headers)

    assert resp.status_code == 200, resp.text
    entry = _find(resp.json(), order.id)
    assert "first_photo_id" in entry
    assert entry["first_photo_id"] is None
