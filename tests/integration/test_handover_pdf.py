"""W2-11 (DOM-34, DOM-35): GET /orders/{id}/handover-pdf."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, Gemstone, Order, OrderStatusEnum


@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch, db_session):
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from sqlalchemy.orm import sessionmaker

    from goldsmith_erp.middleware import audit_logging

    factory = sessionmaker(
        bind=db_session.bind, class_=_AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(audit_logging, "AsyncSessionLocal", factory)


async def _order(db: AsyncSession, customer: Customer, status) -> Order:
    order = Order(
        title="Verlobungsring",
        description="Solitär",
        customer_id=customer.id,
        status=status,
        alloy="750",
        is_deleted=False,
    )
    db.add(order)
    await db.commit()
    db.add(
        Gemstone(
            order_id=order.id,
            type="Diamant",
            carat=0.3,
            cost=900.0,
            quantity=1,
            setting_type="prong",
        )
    )
    await db.commit()
    await db.refresh(order)
    return order


@pytest_asyncio.fixture
async def delivered_order(db_session, test_customer) -> Order:
    return await _order(db_session, test_customer, OrderStatusEnum.DELIVERED)


@pytest.mark.asyncio
async def test_handover_pdf_for_a_delivered_order(
    client: AsyncClient, delivered_order: Order, goldsmith_auth_headers: dict
):
    resp = await client.get(
        f"/api/v1/orders/{delivered_order.id}/handover-pdf",
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert f"abholprotokoll_{delivered_order.id}" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_handover_data_carries_stones_but_no_cost(
    db_session: AsyncSession, delivered_order: Order
):
    from goldsmith_erp.services.handover_service import build_handover_data
    from goldsmith_erp.services.order_service import OrderService

    order = await OrderService.get_order(db_session, delivered_order.id)
    data = await build_handover_data(db_session, order)
    assert data.customer_name == "Maria Mustermann"
    assert data.gemstone_lines == ["1 × Diamant 0,30 ct, Krappenfassung"]
    assert data.stone_types == ["Diamant"]
    assert "900" not in " ".join(data.gemstone_lines)


@pytest.mark.asyncio
async def test_handover_pdf_needs_a_finished_order(
    client: AsyncClient,
    db_session: AsyncSession,
    test_customer: Customer,
    goldsmith_auth_headers: dict,
):
    open_order = await _order(db_session, test_customer, OrderStatusEnum.IN_PROGRESS)
    resp = await client.get(
        f"/api/v1/orders/{open_order.id}/handover-pdf", headers=goldsmith_auth_headers
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_handover_pdf_is_design_data_viewer_is_refused(
    client: AsyncClient, delivered_order: Order, viewer_auth_headers: dict
):
    resp = await client.get(
        f"/api/v1/orders/{delivered_order.id}/handover-pdf",
        headers=viewer_auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_missing_order_is_404(client: AsyncClient, goldsmith_auth_headers: dict):
    resp = await client.get(
        "/api/v1/orders/987654/handover-pdf", headers=goldsmith_auth_headers
    )
    assert resp.status_code == 404
