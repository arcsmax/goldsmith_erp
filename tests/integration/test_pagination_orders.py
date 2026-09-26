"""Paged order list: Page[T], legacy fallback, filters, search (W3-08, ARCH-08)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, Order, OrderStatusEnum

ORDERS_URL = "/api/v1/orders/"
PAGE_KEYS = {"items", "total", "limit", "offset", "next_offset"}


def _letters() -> str:
    """Name-safe random suffix (customer names reject digits)."""
    return "".join(chr(ord("a") + int(c, 16)) for c in uuid.uuid4().hex[:10])


def _token() -> str:
    return uuid.uuid4().hex[:10]


@pytest_asyncio.fixture
async def paged_customer(db_session: AsyncSession) -> Customer:
    customer = Customer(
        first_name="Paula",
        last_name=f"Seitenweise{_letters()}",
        email=f"paged-{_token()}@integration-test.example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def five_orders(
    db_session: AsyncSession, paged_customer: Customer
) -> list[Order]:
    statuses = [
        OrderStatusEnum.NEW,
        OrderStatusEnum.NEW,
        OrderStatusEnum.IN_PROGRESS,
        OrderStatusEnum.IN_PROGRESS,
        OrderStatusEnum.IN_PROGRESS,
    ]
    orders = [
        Order(
            title=f"Seitentest {i}",
            description="Designbeschreibung vertraulich",
            customer_id=paged_customer.id,
            status=status,
            price=100.0 + i,
        )
        for i, status in enumerate(statuses)
    ]
    db_session.add_all(orders)
    await db_session.commit()
    return orders


@pytest.mark.asyncio
class TestOrdersPaged:
    async def test_offset_returns_page_envelope_with_total(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"offset": 0, "limit": 2, "customer_id": paged_customer.id},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == PAGE_KEYS
        assert body["total"] == 5
        assert body["limit"] == 2
        assert body["offset"] == 0
        assert body["next_offset"] == 2
        assert len(body["items"]) == 2
        assert "X-Deprecated-List" not in resp.headers

    async def test_last_page_has_no_next_offset(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"offset": 4, "limit": 2, "customer_id": paged_customer.id},
            headers=admin_auth_headers,
        )
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["next_offset"] is None

    async def test_pages_do_not_overlap(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        seen: list[int] = []
        for offset in (0, 2, 4):
            resp = await client.get(
                ORDERS_URL,
                params={"offset": offset, "limit": 2, "customer_id": paged_customer.id},
                headers=admin_auth_headers,
            )
            seen.extend(item["id"] for item in resp.json()["items"])
        assert sorted(seen) == sorted(o.id for o in five_orders)

    async def test_default_limit_is_50(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"offset": 0, "customer_id": paged_customer.id},
            headers=admin_auth_headers,
        )
        assert resp.json()["limit"] == 50

    async def test_status_filter(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={
                "offset": 0,
                "customer_id": paged_customer.id,
                "status": OrderStatusEnum.IN_PROGRESS.value,
            },
            headers=admin_auth_headers,
        )
        body = resp.json()
        assert body["total"] == 3
        assert {i["status"] for i in body["items"]} == {"in_progress"}

    async def test_search_by_title(
        self, client: AsyncClient, admin_auth_headers, db_session, paged_customer
    ):
        token = _token()
        db_session.add(
            Order(
                title=f"Ring {token}",
                description="x",
                customer_id=paged_customer.id,
                status="new",
            )
        )
        await db_session.commit()
        resp = await client.get(
            ORDERS_URL, params={"offset": 0, "q": token}, headers=admin_auth_headers
        )
        body = resp.json()
        assert body["total"] == 1
        assert token in body["items"][0]["title"]

    async def test_search_by_customer_name(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"offset": 0, "q": paged_customer.last_name},
            headers=admin_auth_headers,
        )
        assert resp.json()["total"] == 5

    async def test_search_by_customer_email_blind_index(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"offset": 0, "q": paged_customer.email.upper()},
            headers=admin_auth_headers,
        )
        assert resp.json()["total"] == 5

    async def test_search_escapes_like_wildcards(
        self, client: AsyncClient, admin_auth_headers, five_orders
    ):
        resp = await client.get(
            ORDERS_URL, params={"offset": 0, "q": "%"}, headers=admin_auth_headers
        )
        titles = [i["title"] for i in resp.json()["items"]]
        assert all("%" in (t or "") for t in titles)

    async def test_limit_above_200_is_422(
        self, client: AsyncClient, admin_auth_headers
    ):
        resp = await client.get(
            ORDERS_URL, params={"offset": 0, "limit": 201}, headers=admin_auth_headers
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "pagination.limit_too_large"

    async def test_limit_200_is_accepted(self, client: AsyncClient, admin_auth_headers):
        resp = await client.get(
            ORDERS_URL, params={"offset": 0, "limit": 200}, headers=admin_auth_headers
        )
        assert resp.status_code == 200

    async def test_viewer_projection_applies_to_page_items(
        self, client: AsyncClient, viewer_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"offset": 0, "customer_id": paged_customer.id},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert "price" not in item
            assert "hourly_rate" not in item
            assert "description" not in item

    async def test_admin_sees_price_in_page_items(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"offset": 0, "customer_id": paged_customer.id},
            headers=admin_auth_headers,
        )
        assert all("price" in item for item in resp.json()["items"])


@pytest.mark.asyncio
class TestOrdersLegacy:
    async def test_no_offset_returns_plain_list_with_deprecation_header(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"customer_id": paged_customer.id},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) == 5
        assert resp.headers["X-Deprecated-List"] == "true"

    async def test_legacy_skip_and_limit_still_work(
        self, client: AsyncClient, admin_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"skip": 1, "limit": 2, "customer_id": paged_customer.id},
            headers=admin_auth_headers,
        )
        assert len(resp.json()) == 2

    async def test_legacy_limit_500_still_allowed(
        self, client: AsyncClient, admin_auth_headers
    ):
        resp = await client.get(
            ORDERS_URL, params={"limit": 500}, headers=admin_auth_headers
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_legacy_limit_is_capped(
        self, client: AsyncClient, admin_auth_headers
    ):
        resp = await client.get(
            ORDERS_URL, params={"limit": 501}, headers=admin_auth_headers
        )
        assert resp.status_code == 422

    async def test_legacy_viewer_projection_still_applied(
        self, client: AsyncClient, viewer_auth_headers, paged_customer, five_orders
    ):
        resp = await client.get(
            ORDERS_URL,
            params={"customer_id": paged_customer.id},
            headers=viewer_auth_headers,
        )
        assert all("price" not in item for item in resp.json())
