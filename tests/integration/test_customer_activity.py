"""
W2-12 (DOM-38): customer 360 — GET /api/v1/customers/{id}/activity.

One chronological list (newest first) across orders, repairs, quotes,
invoices and customer updates of ONE customer, paged with the Page[T]
contract. VIEWER projection: no amounts, and no quotes / invoices /
customer updates (VIEWER holds neither FINANCIAL_VIEW nor
CUSTOMER_UPDATE_VIEW).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Invoice,
    InvoiceStatus,
    Order,
    OrderStatusEnum,
    Quote,
    QuoteStatus,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    User,
)

pytestmark = pytest.mark.asyncio

BASE = datetime(2026, 9, 1, 10, 0)


def _url(customer_id: int) -> str:
    return f"/api/v1/customers/{customer_id}/activity"


def _at(day: int) -> datetime:
    return BASE + timedelta(days=day)


async def _other_customer(db: AsyncSession) -> Customer:
    other = Customer(
        first_name="Otto",
        last_name="Andere",
        phone="+49 30 111",
        customer_type="private",
        is_active=True,
    )
    db.add(other)
    await db.commit()
    await db.refresh(other)
    return other


async def _seed(db: AsyncSession, customer: Customer, author: User) -> Dict[str, int]:
    """One row per kind, days 1..6 (6 = newest), plus noise rows."""
    order = Order(
        title="Trauring Meier",
        customer_id=customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        price=1200.0,
        created_at=_at(1),
    )
    db.add(order)
    await db.flush()
    repair = RepairJob(
        repair_number="REP-2026-0901",
        bag_number="TU-2026-0901",
        customer_id=customer.id,
        item_description="Kette gerissen",
        item_type=RepairItemType.CHAIN,
        status=RepairJobStatus.RECEIVED,
        estimated_cost=40.0,
        created_at=_at(2),
    )
    quote = Quote(
        quote_number="KV-2026-0901",
        customer_id=customer.id,
        created_by=author.id,
        status=QuoteStatus.SENT,
        valid_until=_at(30),
        total=950.0,
        created_at=_at(3),
    )
    invoice = Invoice(
        invoice_number="RE-2026-0901",
        order_id=order.id,
        customer_id=customer.id,
        created_by=author.id,
        status=InvoiceStatus.PAID,
        due_date=_at(20),
        total=1200.0,
        created_at=_at(4),
    )
    db.add_all([repair, quote, invoice])
    await db.flush()
    order_update = CustomerUpdate(
        order_id=order.id,
        kind=CustomerUpdateKind.PROGRESS,
        subject="Ihr Trauring ist in Arbeit",
        body="Hallo",
        status=CustomerUpdateStatus.SENT,
        sent_by=author.id,
        created_at=_at(5),
    )
    repair_update = CustomerUpdate(
        repair_job_id=repair.id,
        kind=CustomerUpdateKind.READY_FOR_PICKUP,
        subject="Ihre Kette ist abholbereit",
        body="Hallo",
        status=CustomerUpdateStatus.DRAFT,
        sent_by=author.id,
        created_at=_at(6),
    )
    db.add_all([order_update, repair_update])

    # Noise: another customer's order and a soft-deleted order of ours.
    other = await _other_customer(db)
    db.add(
        Order(
            title="Fremder Auftrag",
            customer_id=other.id,
            status=OrderStatusEnum.DRAFT,
            created_at=_at(7),
        )
    )
    db.add(
        Order(
            title="Gelöschter Auftrag",
            customer_id=customer.id,
            status=OrderStatusEnum.DRAFT,
            is_deleted=True,
            created_at=_at(8),
        )
    )
    await db.commit()
    return {
        "order": order.id,
        "repair": repair.id,
        "quote": quote.id,
        "invoice": invoice.id,
        "order_update": order_update.id,
        "repair_update": repair_update.id,
    }


async def test_activity_merges_all_kinds_newest_first(
    client: AsyncClient,
    admin_auth_headers: dict,
    admin_user: User,
    test_customer: Customer,
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session, test_customer, admin_user)

    resp = await client.get(
        _url(test_customer.id), params={"offset": 0}, headers=admin_auth_headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 6
    assert body["offset"] == 0
    assert body["next_offset"] is None
    kinds = [(item["kind"], item["id"]) for item in body["items"]]
    assert kinds == [
        ("customer_update", ids["repair_update"]),
        ("customer_update", ids["order_update"]),
        ("invoice", ids["invoice"]),
        ("quote", ids["quote"]),
        ("repair", ids["repair"]),
        ("order", ids["order"]),
    ]


async def test_activity_rows_carry_status_title_reference_amount_and_links(
    client: AsyncClient,
    admin_auth_headers: dict,
    admin_user: User,
    test_customer: Customer,
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session, test_customer, admin_user)

    resp = await client.get(
        _url(test_customer.id), params={"offset": 0}, headers=admin_auth_headers
    )

    rows = {(r["kind"], r["id"]): r for r in resp.json()["items"]}
    order = rows[("order", ids["order"])]
    assert order["status"] == "in_progress"
    assert order["title"] == "Trauring Meier"
    assert order["amount"] == 1200.0
    repair = rows[("repair", ids["repair"])]
    assert repair["reference"] == "REP-2026-0901"
    assert repair["amount"] == 40.0
    assert rows[("quote", ids["quote"])]["reference"] == "KV-2026-0901"
    assert rows[("quote", ids["quote"])]["amount"] == 950.0
    invoice = rows[("invoice", ids["invoice"])]
    assert invoice["reference"] == "RE-2026-0901"
    assert invoice["status"] == "paid"
    assert invoice["order_id"] == ids["order"]
    update = rows[("customer_update", ids["repair_update"])]
    assert update["title"] == "Ihre Kette ist abholbereit"
    assert update["status"] == "draft"
    assert update["repair_job_id"] == ids["repair"]
    assert update["amount"] is None
    assert rows[("customer_update", ids["order_update"])]["order_id"] == ids["order"]


async def test_activity_pages_across_kinds(
    client: AsyncClient,
    admin_auth_headers: dict,
    admin_user: User,
    test_customer: Customer,
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session, test_customer, admin_user)

    first = await client.get(
        _url(test_customer.id),
        params={"offset": 0, "limit": 4},
        headers=admin_auth_headers,
    )
    second = await client.get(
        _url(test_customer.id),
        params={"offset": 4, "limit": 4},
        headers=admin_auth_headers,
    )

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["next_offset"] == 4
    assert len(first.json()["items"]) == 4
    assert second.json()["next_offset"] is None
    assert [(r["kind"], r["id"]) for r in second.json()["items"]] == [
        ("repair", ids["repair"]),
        ("order", ids["order"]),
    ]


async def test_activity_defaults_to_a_page_without_offset(
    client: AsyncClient, admin_auth_headers: dict, test_customer: Customer
) -> None:
    resp = await client.get(_url(test_customer.id), headers=admin_auth_headers)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
        "next_offset": None,
    }


async def test_activity_limit_above_cap_is_rejected(
    client: AsyncClient, admin_auth_headers: dict, test_customer: Customer
) -> None:
    resp = await client.get(
        _url(test_customer.id),
        params={"offset": 0, "limit": 201},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 422


async def test_activity_viewer_sees_only_orders_and_repairs_without_amounts(
    client: AsyncClient,
    viewer_auth_headers: dict,
    admin_user: User,
    test_customer: Customer,
    db_session: AsyncSession,
) -> None:
    ids = await _seed(db_session, test_customer, admin_user)

    resp = await client.get(
        _url(test_customer.id), params={"offset": 0}, headers=viewer_auth_headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert [(r["kind"], r["id"]) for r in body["items"]] == [
        ("repair", ids["repair"]),
        ("order", ids["order"]),
    ]
    for row in body["items"]:
        assert "amount" not in row


async def test_activity_unknown_customer_gets_404(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    resp = await client.get(_url(999999), headers=admin_auth_headers)

    assert resp.status_code == 404


async def test_activity_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get(_url(1))

    assert resp.status_code == 401
