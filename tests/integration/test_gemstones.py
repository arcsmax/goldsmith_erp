"""Integration tests for order gemstones (W2-06, DOM-04).

CRUD under ``/orders/{id}/gemstones`` + ``/gemstones/{id}``, the Fassungsart
contract, the Kundenstein rule, role projection (VIEWER sees no cost and no
design details, cannot write) and the audit row for the list read.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    CustomerAuditLog,
    Gemstone,
    Order,
    OrderStatusEnum,
)


@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch, db_session):
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from sqlalchemy.orm import sessionmaker

    from goldsmith_erp.middleware import audit_logging

    factory = sessionmaker(
        bind=db_session.bind, class_=_AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(audit_logging, "AsyncSessionLocal", factory)


@pytest_asyncio.fixture
async def order(db_session: AsyncSession, test_customer: Customer) -> Order:
    row = Order(
        title="Verlobungsring",
        description="Solitär",
        customer_id=test_customer.id,
        status=OrderStatusEnum.CONFIRMED,
        is_deleted=False,
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


_DIAMOND = {
    "type": "Diamant",
    "quantity": 3,
    "carat": 0.1,
    "color": "G",
    "quality": "VS1",
    "shape": "rund",
    "setting_type": "prong",
    "cost": 120.0,
}


async def _create(client: AsyncClient, order_id: int, headers: dict, body: dict):
    return await client.post(
        f"/api/v1/orders/{order_id}/gemstones", json=body, headers=headers
    )


@pytest.mark.asyncio
async def test_goldsmith_creates_lists_updates_and_deletes_a_stone(
    client: AsyncClient, order: Order, goldsmith_auth_headers: dict
):
    created = await _create(client, order.id, goldsmith_auth_headers, _DIAMOND)
    assert created.status_code == 201, created.text
    stone = created.json()
    assert stone["order_id"] == order.id
    assert stone["setting_type"] == "prong"
    assert stone["total_cost"] == pytest.approx(360.0)
    assert stone["is_customer_stone"] is False

    listed = await client.get(
        f"/api/v1/orders/{order.id}/gemstones", headers=goldsmith_auth_headers
    )
    assert listed.status_code == 200
    assert [s["id"] for s in listed.json()] == [stone["id"]]

    patched = await client.patch(
        f"/api/v1/gemstones/{stone['id']}",
        json={"quantity": 5, "setting_type": "channel"},
        headers=goldsmith_auth_headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["quantity"] == 5
    assert patched.json()["setting_type"] == "channel"
    assert patched.json()["total_cost"] == pytest.approx(600.0)

    deleted = await client.delete(
        f"/api/v1/gemstones/{stone['id']}", headers=goldsmith_auth_headers
    )
    assert deleted.status_code == 204
    listed = await client.get(
        f"/api/v1/orders/{order.id}/gemstones", headers=goldsmith_auth_headers
    )
    assert listed.json() == []


@pytest.mark.asyncio
async def test_unknown_fassungsart_is_rejected(
    client: AsyncClient, order: Order, goldsmith_auth_headers: dict
):
    resp = await _create(
        client, order.id, goldsmith_auth_headers, {**_DIAMOND, "setting_type": "glue"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_customer_stone_cannot_carry_a_purchase_price(
    client: AsyncClient, order: Order, goldsmith_auth_headers: dict
):
    resp = await _create(
        client,
        order.id,
        goldsmith_auth_headers,
        {"type": "Saphir", "is_customer_stone": True, "cost": 50.0},
    )
    assert resp.status_code == 422

    ok = await _create(
        client,
        order.id,
        goldsmith_auth_headers,
        {"type": "Saphir", "is_customer_stone": True, "setting_type": "bezel"},
    )
    assert ok.status_code == 201
    assert ok.json()["cost"] == 0.0

    # Turning a priced stone into a Kundenstein without clearing the price fails.
    priced = await _create(client, order.id, goldsmith_auth_headers, _DIAMOND)
    resp = await client.patch(
        f"/api/v1/gemstones/{priced.json()['id']}",
        json={"is_customer_stone": True},
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_viewer_reads_without_cost_or_design_and_cannot_write(
    client: AsyncClient,
    order: Order,
    goldsmith_auth_headers: dict,
    viewer_auth_headers: dict,
):
    created = await _create(client, order.id, goldsmith_auth_headers, _DIAMOND)
    stone_id = created.json()["id"]

    listed = await client.get(
        f"/api/v1/orders/{order.id}/gemstones", headers=viewer_auth_headers
    )
    assert listed.status_code == 200
    (stone,) = listed.json()
    assert stone["type"] == "Diamant"
    assert stone["quantity"] == 3
    for hidden in ("cost", "total_cost", "carat", "setting_type", "color", "notes"):
        assert hidden not in stone

    denied = await _create(client, order.id, viewer_auth_headers, _DIAMOND)
    assert denied.status_code == 403
    denied = await client.delete(
        f"/api/v1/gemstones/{stone_id}", headers=viewer_auth_headers
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_list_read_writes_an_audit_row(
    client: AsyncClient,
    db_session: AsyncSession,
    order: Order,
    goldsmith_auth_headers: dict,
):
    await client.get(
        f"/api/v1/orders/{order.id}/gemstones", headers=goldsmith_auth_headers
    )
    rows = (
        (
            await db_session.execute(
                select(CustomerAuditLog).where(CustomerAuditLog.entity == "gemstone")
            )
        )
        .scalars()
        .all()
    )
    assert any(r.action == "list_accessed_financial" for r in rows)


@pytest.mark.asyncio
async def test_missing_order_is_404(client: AsyncClient, goldsmith_auth_headers: dict):
    resp = await client.get(
        "/api/v1/orders/999999/gemstones", headers=goldsmith_auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_created_stone_is_stored_with_its_setting_code(
    client: AsyncClient,
    db_session: AsyncSession,
    order: Order,
    goldsmith_auth_headers: dict,
):
    """The stone lands in the gemstones table (feeds the ML feature builder)."""
    await _create(client, order.id, goldsmith_auth_headers, _DIAMOND)
    rows = (
        (
            await db_session.execute(
                select(Gemstone).where(Gemstone.order_id == order.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].setting_type == "prong"
