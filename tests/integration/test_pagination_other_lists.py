"""Paged materials, time entries and notifications (W3-08, ARCH-08)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    Material,
    Notification,
    NotificationTypeEnum,
    Order,
    TimeEntry,
    User,
)

PAGE_KEYS = {"items", "total", "limit", "offset", "next_offset"}


@pytest.mark.asyncio
async def test_materials_paged_search_and_viewer_projection(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers,
    viewer_auth_headers,
):
    token = uuid.uuid4().hex[:8]
    db_session.add_all(
        [
            Material(name=f"Gold {token} {i}", unit_price=60.0, stock=5, unit="g")
            for i in range(3)
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/materials/",
        params={"offset": 0, "limit": 2, "q": token},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == PAGE_KEYS
    assert body["total"] == 3
    assert body["next_offset"] == 2

    viewer = await client.get(
        "/api/v1/materials/",
        params={"offset": 0, "q": token},
        headers=viewer_auth_headers,
    )
    assert all("unit_price" not in m for m in viewer.json()["items"])

    legacy = await client.get("/api/v1/materials/", headers=admin_auth_headers)
    assert isinstance(legacy.json(), list)
    assert legacy.headers["X-Deprecated-List"] == "true"


@pytest.mark.asyncio
async def test_time_entries_for_user_paged_with_date_range(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    admin_auth_headers,
):
    activity = Activity(name=f"Polieren {uuid.uuid4().hex[:6]}", category="fabrication")
    order = Order(title="Zeitseiten", status="new")
    db_session.add_all([activity, order])
    await db_session.commit()
    base = datetime(2026, 1, 10, 8, 0)
    db_session.add_all(
        [
            TimeEntry(
                id=str(uuid.uuid4()),
                user_id=admin_user.id,
                activity_id=activity.id,
                order_id=order.id,
                start_time=base + timedelta(days=i),
                end_time=base + timedelta(days=i, hours=1),
                duration_minutes=60,
            )
            for i in range(4)
        ]
    )
    await db_session.commit()

    url = f"/api/v1/time-tracking/user/{admin_user.id}"
    resp = await client.get(
        url,
        params={
            "offset": 0,
            "limit": 2,
            "start_date": (base + timedelta(days=1)).isoformat(),
            "end_date": (base + timedelta(days=3, hours=1)).isoformat(),
        },
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["next_offset"] == 2

    legacy = await client.get(url, headers=admin_auth_headers)
    assert isinstance(legacy.json(), list)
    assert legacy.headers["X-Deprecated-List"] == "true"

    too_big = await client.get(
        url, params={"offset": 0, "limit": 201}, headers=admin_auth_headers
    )
    assert too_big.status_code == 422


@pytest.mark.asyncio
async def test_notifications_paged_only_own(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    goldsmith_user: User,
    admin_auth_headers,
):
    db_session.add_all(
        [
            Notification(
                user_id=admin_user.id,
                notification_type=NotificationTypeEnum.DEADLINE_WARNING,
                title=f"Frist {i}",
                message="Auftrag fällig",
                is_read=i == 0,
            )
            for i in range(3)
        ]
        + [
            Notification(
                user_id=goldsmith_user.id,
                notification_type=NotificationTypeEnum.DEADLINE_WARNING,
                title="Fremd",
                message="x",
            )
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/notifications/",
        params={"offset": 0, "limit": 2},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    unread = await client.get(
        "/api/v1/notifications/",
        params={"offset": 0, "unread_only": True},
        headers=admin_auth_headers,
    )
    assert unread.json()["total"] == 2

    legacy = await client.get(
        "/api/v1/notifications/", params={"limit": 10}, headers=admin_auth_headers
    )
    assert isinstance(legacy.json(), list)
    assert legacy.headers["X-Deprecated-List"] == "true"
