"""Paged repair and quote lists (W3-08, ARCH-08)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    Quote,
    QuoteStatus,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    User,
)

REPAIRS_URL = "/api/v1/repairs/"
QUOTES_URL = "/api/v1/quotes/"
PAGE_KEYS = {"items", "total", "limit", "offset", "next_offset"}


def _letters() -> str:
    """Name-safe random suffix (customer names reject digits)."""
    return "".join(chr(ord("a") + int(c, 16)) for c in uuid.uuid4().hex[:10])


def _token() -> str:
    return uuid.uuid4().hex[:8].upper()


@pytest_asyncio.fixture
async def page_customer(db_session: AsyncSession) -> Customer:
    customer = Customer(
        first_name="Rita",
        last_name=f"Reparatur{_letters()}",
        email=f"rq-{_token().lower()}@integration-test.example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def repairs(
    db_session: AsyncSession, page_customer: Customer, admin_user: User
) -> list[RepairJob]:
    token = _token()
    jobs = [
        RepairJob(
            repair_number=f"R{token}{i}",
            bag_number=f"B{token}{i}",
            customer_id=page_customer.id,
            received_by=admin_user.id,
            item_description="Ring Stein locker",
            item_type=RepairItemType.RING,
            status=RepairJobStatus.RECEIVED if i < 2 else RepairJobStatus.DIAGNOSED,
            estimated_cost=80.0,
        )
        for i in range(3)
    ]
    db_session.add_all(jobs)
    await db_session.commit()
    return jobs


@pytest_asyncio.fixture
async def quotes(
    db_session: AsyncSession, page_customer: Customer, admin_user: User
) -> list[Quote]:
    token = _token()
    rows = [
        Quote(
            quote_number=f"KV{token}{i}",
            customer_id=page_customer.id,
            created_by=admin_user.id,
            status=QuoteStatus.DRAFT if i == 0 else QuoteStatus.SENT,
            valid_until=datetime.utcnow() + timedelta(days=14),
            subtotal=100.0,
            tax_rate=19.0,
            tax_amount=19.0,
            total=119.0,
        )
        for i in range(3)
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return rows


@pytest.mark.asyncio
class TestRepairsPaged:
    async def test_page_envelope_and_total(
        self, client: AsyncClient, admin_auth_headers, page_customer, repairs
    ):
        resp = await client.get(
            REPAIRS_URL,
            params={"offset": 0, "limit": 2, "customer_id": page_customer.id},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == PAGE_KEYS
        assert body["total"] == 3
        assert body["next_offset"] == 2

    async def test_status_filter(
        self, client: AsyncClient, admin_auth_headers, page_customer, repairs
    ):
        resp = await client.get(
            REPAIRS_URL,
            params={
                "offset": 0,
                "customer_id": page_customer.id,
                "status": RepairJobStatus.DIAGNOSED.value,
            },
            headers=admin_auth_headers,
        )
        assert resp.json()["total"] == 1

    async def test_search_by_number_and_customer(
        self, client: AsyncClient, admin_auth_headers, page_customer, repairs
    ):
        by_number = await client.get(
            REPAIRS_URL,
            params={"offset": 0, "q": repairs[0].repair_number},
            headers=admin_auth_headers,
        )
        assert by_number.json()["total"] == 1
        by_customer = await client.get(
            REPAIRS_URL,
            params={"offset": 0, "q": page_customer.last_name},
            headers=admin_auth_headers,
        )
        assert by_customer.json()["total"] == 3

    async def test_limit_above_200_is_422(
        self, client: AsyncClient, admin_auth_headers
    ):
        resp = await client.get(
            REPAIRS_URL, params={"offset": 0, "limit": 201}, headers=admin_auth_headers
        )
        assert resp.status_code == 422

    async def test_viewer_projection_applies(
        self, client: AsyncClient, viewer_auth_headers, page_customer, repairs
    ):
        resp = await client.get(
            REPAIRS_URL,
            params={"offset": 0, "customer_id": page_customer.id},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 3
        assert all("estimated_cost" not in item for item in items)

    async def test_legacy_list_with_header(
        self, client: AsyncClient, admin_auth_headers, page_customer, repairs
    ):
        resp = await client.get(
            REPAIRS_URL,
            params={"limit": 200, "customer_id": page_customer.id},
            headers=admin_auth_headers,
        )
        assert isinstance(resp.json(), list)
        assert len(resp.json()) == 3
        assert resp.headers["X-Deprecated-List"] == "true"


@pytest.mark.asyncio
class TestQuotesPaged:
    async def test_page_envelope_and_total(
        self, client: AsyncClient, admin_auth_headers, page_customer, quotes
    ):
        resp = await client.get(
            QUOTES_URL,
            params={"offset": 0, "limit": 2, "customer_id": page_customer.id},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == PAGE_KEYS
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["next_offset"] == 2

    async def test_status_filter_and_search(
        self, client: AsyncClient, admin_auth_headers, page_customer, quotes
    ):
        by_status = await client.get(
            QUOTES_URL,
            params={"offset": 0, "customer_id": page_customer.id, "status": "sent"},
            headers=admin_auth_headers,
        )
        assert by_status.json()["total"] == 2
        by_number = await client.get(
            QUOTES_URL,
            params={"offset": 0, "q": quotes[1].quote_number},
            headers=admin_auth_headers,
        )
        assert by_number.json()["total"] == 1
        by_customer = await client.get(
            QUOTES_URL,
            params={"offset": 0, "q": page_customer.last_name},
            headers=admin_auth_headers,
        )
        assert by_customer.json()["total"] == 3

    async def test_limit_above_200_is_422(
        self, client: AsyncClient, admin_auth_headers
    ):
        resp = await client.get(
            QUOTES_URL, params={"offset": 0, "limit": 201}, headers=admin_auth_headers
        )
        assert resp.status_code == 422

    async def test_viewer_is_still_forbidden(
        self, client: AsyncClient, viewer_auth_headers
    ):
        resp = await client.get(
            QUOTES_URL, params={"offset": 0}, headers=viewer_auth_headers
        )
        assert resp.status_code == 403

    async def test_legacy_envelope_kept_with_header(
        self, client: AsyncClient, admin_auth_headers, page_customer, quotes
    ):
        resp = await client.get(
            QUOTES_URL,
            params={"customer_id": page_customer.id},
            headers=admin_auth_headers,
        )
        body = resp.json()
        assert set(body) == {"items", "total", "skip", "limit"}
        assert body["total"] == 3
        assert resp.headers["X-Deprecated-List"] == "true"
