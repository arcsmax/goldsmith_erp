"""``sort`` on the paged list endpoints, and paged /customers/ (W3-sort).

Covers: asc/desc sort per endpoint, unknown-field -> 422 with the
DomainError validation code, and the new paged customers list (Page[T],
blind-index ``q`` search, VIEWER projection, legacy path unchanged).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    Customer,
    Material,
    Notification,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    Order,
    Quote,
    QuoteStatus,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    TimeEntry,
    User,
)

PAGE_KEYS = {"items", "total", "limit", "offset", "next_offset"}
INVALID_SORT_CODE = "pagination.invalid_sort_field"


def _token() -> str:
    return uuid.uuid4().hex[:8]


def _letters() -> str:
    """Name-safe random suffix (customer names reject digits)."""
    return "".join(chr(ord("a") + int(c, 16)) for c in uuid.uuid4().hex[:10])


@pytest_asyncio.fixture
async def sort_customer(db_session: AsyncSession) -> Customer:
    customer = Customer(
        first_name="Sortina",
        last_name=f"Sortier{_letters()}",
        email=f"sort-{_token()}@integration-test.example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest.mark.asyncio
class TestOrdersSort:
    async def test_sort_by_title_ascending_and_descending(
        self, client: AsyncClient, admin_auth_headers, db_session, sort_customer
    ):
        token = _token()
        db_session.add_all(
            [
                Order(
                    title=f"{letter}-{token}",
                    description="x",
                    customer_id=sort_customer.id,
                    status="new",
                )
                for letter in ("Charlie", "Alfa", "Bravo")
            ]
        )
        await db_session.commit()

        asc = await client.get(
            "/api/v1/orders/",
            params={"offset": 0, "q": token, "sort": "title"},
            headers=admin_auth_headers,
        )
        assert asc.status_code == 200, asc.text
        titles_asc = [i["title"] for i in asc.json()["items"]]
        assert titles_asc == sorted(titles_asc)

        desc = await client.get(
            "/api/v1/orders/",
            params={"offset": 0, "q": token, "sort": "-title"},
            headers=admin_auth_headers,
        )
        titles_desc = [i["title"] for i in desc.json()["items"]]
        assert titles_desc == sorted(titles_desc, reverse=True)
        assert titles_desc == list(reversed(titles_asc))

    async def test_unknown_sort_field_is_422_with_domain_code(
        self, client: AsyncClient, admin_auth_headers
    ):
        resp = await client.get(
            "/api/v1/orders/",
            params={"offset": 0, "sort": "price"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == INVALID_SORT_CODE

    async def test_sort_ignored_in_legacy_mode(
        self, client: AsyncClient, admin_auth_headers
    ):
        # No ``offset`` -> legacy path; an unknown field must not 422 here,
        # matching every other paged-only filter ("nur mit offset").
        resp = await client.get(
            "/api/v1/orders/",
            params={"sort": "not_a_real_field"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_repairs_sort_by_repair_number_descending(
    client: AsyncClient, admin_auth_headers, db_session, sort_customer, admin_user: User
):
    token = _token()
    jobs = [
        RepairJob(
            repair_number=f"R{token}{i}",
            bag_number=f"B{token}{i}",
            customer_id=sort_customer.id,
            received_by=admin_user.id,
            item_description="Sortiertest",
            item_type=RepairItemType.RING,
            status=RepairJobStatus.RECEIVED,
        )
        for i in range(3)
    ]
    db_session.add_all(jobs)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/repairs/",
        params={"offset": 0, "q": token, "sort": "-repair_number"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    numbers = [i["repair_number"] for i in resp.json()["items"]]
    assert numbers == sorted(numbers, reverse=True)

    bad = await client.get(
        "/api/v1/repairs/",
        params={"offset": 0, "sort": "estimated_cost"},
        headers=admin_auth_headers,
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == INVALID_SORT_CODE


@pytest.mark.asyncio
async def test_quotes_sort_by_valid_until(
    client: AsyncClient, admin_auth_headers, db_session, sort_customer, admin_user: User
):
    token = _token()
    rows = [
        Quote(
            quote_number=f"KV{token}{i}",
            customer_id=sort_customer.id,
            created_by=admin_user.id,
            status=QuoteStatus.DRAFT,
            valid_until=datetime.utcnow() + timedelta(days=i),
            subtotal=100.0,
            tax_rate=19.0,
            tax_amount=19.0,
            total=119.0,
        )
        for i in (3, 1, 2)
    ]
    db_session.add_all(rows)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/quotes/",
        params={"offset": 0, "q": token, "sort": "valid_until"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    dates = [i["valid_until"] for i in resp.json()["items"]]
    assert dates == sorted(dates)

    bad = await client.get(
        "/api/v1/quotes/",
        params={"offset": 0, "sort": "total"},
        headers=admin_auth_headers,
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == INVALID_SORT_CODE


@pytest.mark.asyncio
async def test_materials_sort_by_stock_descending(
    client: AsyncClient, admin_auth_headers, db_session
):
    token = _token()
    db_session.add_all(
        [
            Material(name=f"Gold {token} {i}", unit_price=60.0, stock=stock, unit="g")
            for i, stock in enumerate((5, 20, 10))
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/materials/",
        params={"offset": 0, "q": token, "sort": "-stock"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    stocks = [float(i["stock"]) for i in resp.json()["items"]]
    assert stocks == sorted(stocks, reverse=True)

    bad = await client.get(
        "/api/v1/materials/",
        params={"offset": 0, "sort": "unit_price"},
        headers=admin_auth_headers,
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == INVALID_SORT_CODE


@pytest.mark.asyncio
async def test_time_entries_sort_by_end_time(
    client: AsyncClient, admin_auth_headers, db_session, admin_user: User
):
    activity = Activity(name=f"Polieren {_token()}", category="fabrication")
    order = Order(title=f"Sortzeit {_token()}", status="new")
    db_session.add_all([activity, order])
    await db_session.commit()
    base = datetime(2026, 2, 1, 8, 0)
    db_session.add_all(
        [
            TimeEntry(
                id=str(uuid.uuid4()),
                user_id=admin_user.id,
                activity_id=activity.id,
                order_id=order.id,
                start_time=base + timedelta(hours=i),
                end_time=base + timedelta(hours=3 - i),
                duration_minutes=60,
            )
            for i in range(3)
        ]
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/time-tracking/order/{order.id}",
        params={"offset": 0, "sort": "end_time"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    ends = [i["end_time"] for i in resp.json()["items"]]
    assert ends == sorted(ends)

    bad = await client.get(
        f"/api/v1/time-tracking/order/{order.id}",
        params={"offset": 0, "sort": "duration_minutes"},
        headers=admin_auth_headers,
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == INVALID_SORT_CODE


@pytest.mark.asyncio
async def test_notifications_sort_by_severity(
    client: AsyncClient, admin_auth_headers, db_session, admin_user: User
):
    db_session.add_all(
        [
            Notification(
                user_id=admin_user.id,
                notification_type=NotificationTypeEnum.DEADLINE_WARNING,
                title=f"Sort {sev.value}",
                message="x",
                severity=sev,
            )
            for sev in (
                NotificationSeverityEnum.URGENT,
                NotificationSeverityEnum.INFO,
                NotificationSeverityEnum.WARNING,
            )
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/notifications/",
        params={"offset": 0, "sort": "severity"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] >= 3

    bad = await client.get(
        "/api/v1/notifications/",
        params={"offset": 0, "sort": "message"},
        headers=admin_auth_headers,
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == INVALID_SORT_CODE


@pytest.mark.asyncio
class TestCustomersPaged:
    async def test_offset_returns_page_envelope_with_total(
        self, client: AsyncClient, admin_auth_headers, db_session
    ):
        token = _letters()
        db_session.add_all(
            [
                Customer(
                    first_name="Paged",
                    last_name=f"Kunde{token}{i}",
                    customer_type="private",
                    is_active=True,
                )
                for i in range(3)
            ]
        )
        await db_session.commit()

        resp = await client.get(
            "/api/v1/customers/",
            params={"offset": 0, "limit": 2, "customer_type": "private"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == PAGE_KEYS
        assert body["limit"] == 2
        assert len(body["items"]) == 2
        assert "X-Deprecated-List" not in resp.headers

    async def test_q_searches_full_email_via_blind_index(
        self, client: AsyncClient, admin_auth_headers, sort_customer
    ):
        resp = await client.get(
            "/api/v1/customers/",
            params={"offset": 0, "q": sort_customer.email.upper()},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == sort_customer.id

    async def test_q_does_not_substring_match_names(
        self, client: AsyncClient, admin_auth_headers, sort_customer
    ):
        # Unlike the legacy ``search`` param, paged ``q`` is blind-index-only:
        # a name fragment (not a full email) must not match anything.
        resp = await client.get(
            "/api/v1/customers/",
            params={"offset": 0, "q": sort_customer.last_name[:6]},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 0

    async def test_sort_by_customer_type(
        self, client: AsyncClient, admin_auth_headers, db_session
    ):
        token = _letters()
        db_session.add_all(
            [
                Customer(
                    first_name="Firma",
                    last_name=f"B{token}",
                    customer_type="business",
                    is_active=True,
                ),
                Customer(
                    first_name="Privat",
                    last_name=f"A{token}",
                    customer_type="private",
                    is_active=True,
                ),
            ]
        )
        await db_session.commit()

        resp = await client.get(
            "/api/v1/customers/",
            params={"offset": 0, "sort": "customer_type"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        types = [i["customer_type"] for i in resp.json()["items"]]
        assert types == sorted(types)

    async def test_unknown_sort_field_is_422_with_domain_code(
        self, client: AsyncClient, admin_auth_headers
    ):
        resp = await client.get(
            "/api/v1/customers/",
            params={"offset": 0, "sort": "last_name"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == INVALID_SORT_CODE

    async def test_viewer_can_read_paged_customers(
        self, client: AsyncClient, viewer_auth_headers, sort_customer
    ):
        resp = await client.get(
            "/api/v1/customers/",
            params={"offset": 0, "customer_type": "private"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == PAGE_KEYS
        for item in body["items"]:
            assert set(item) == {
                "id",
                "first_name",
                "last_name",
                "company_name",
                "email",
                "phone",
                "customer_type",
                "tags",
                "is_active",
            }


@pytest.mark.asyncio
async def test_customers_legacy_list_unchanged(
    client: AsyncClient, admin_auth_headers, sort_customer
):
    resp = await client.get(
        "/api/v1/customers/",
        params={"search": sort_customer.last_name},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)
    assert resp.headers["X-Deprecated-List"] == "true"
    assert any(c["id"] == sort_customer.id for c in resp.json())
