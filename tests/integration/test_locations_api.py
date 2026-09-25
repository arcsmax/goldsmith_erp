# tests/integration/test_locations_api.py
"""W8 Standorte: ADMIN CRUD, staff picker, write-path sync on entries/orders."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from goldsmith_erp.db.models import (
    Activity,
    CustomerAuditLog,
    LocationHistory,
    Order,
    TimeEntry,
    WorkshopLocation,
)

pytestmark = pytest.mark.asyncio

ADMIN_URL = "/api/v1/admin/locations"
PICKER_URL = "/api/v1/locations"


@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch, db_session):
    """Audit middleware writes to the test engine."""
    from goldsmith_erp.middleware import audit_logging

    factory = sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(audit_logging, "AsyncSessionLocal", factory)


async def _location(
    db: AsyncSession, name: str, *, active: bool = True, sort: int = 10
) -> WorkshopLocation:
    loc = WorkshopLocation(name=name, kind="bench", is_active=active, sort_order=sort)
    db.add(loc)
    await db.commit()
    await db.refresh(loc)
    return loc


async def _order(db: AsyncSession, customer_id: int) -> Order:
    order = Order(title="Ring", description="Testauftrag", customer_id=customer_id)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _activity(db: AsyncSession) -> Activity:
    act = Activity(name="Polieren", category="fabrication")
    db.add(act)
    await db.commit()
    await db.refresh(act)
    return act


async def test_admin_crud_round_trip_is_audited(
    client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
):
    resp = await client.post(
        ADMIN_URL,
        json={"name": "  Werkbank   3 ", "kind": "bench"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "Werkbank 3"
    assert created["is_active"] is True
    loc_id = created["id"]

    resp = await client.patch(
        f"{ADMIN_URL}/{loc_id}",
        json={"name": "Werkbank Drei", "sort_order": 5},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Werkbank Drei"
    assert resp.json()["sort_order"] == 5

    resp = await client.delete(f"{ADMIN_URL}/{loc_id}", headers=admin_auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    listed = (await client.get(ADMIN_URL, headers=admin_auth_headers)).json()
    assert [(r["name"], r["is_active"]) for r in listed] == [("Werkbank Drei", False)]

    db_session.expire_all()
    audits = (
        (
            await db_session.execute(
                select(CustomerAuditLog).where(
                    CustomerAuditLog.entity == "workshop_location"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) >= 4


async def test_duplicate_name_is_409_case_insensitive(
    client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
):
    await _location(db_session, "Tresor")
    resp = await client.post(
        ADMIN_URL, json={"name": "tresor"}, headers=admin_auth_headers
    )
    assert resp.status_code == 409


async def test_invalid_kind_is_422(client: AsyncClient, admin_auth_headers: dict):
    resp = await client.post(
        ADMIN_URL, json={"name": "X", "kind": "garage"}, headers=admin_auth_headers
    )
    assert resp.status_code == 422


async def _assert_admin_forbidden(
    client: AsyncClient, db_session: AsyncSession, headers: dict
) -> None:
    loc = await _location(db_session, "Werkbank 1")
    assert (await client.get(ADMIN_URL, headers=headers)).status_code == 403
    assert (
        await client.post(ADMIN_URL, json={"name": "Neu"}, headers=headers)
    ).status_code == 403
    assert (
        await client.patch(f"{ADMIN_URL}/{loc.id}", json={"name": "Y"}, headers=headers)
    ).status_code == 403
    assert (
        await client.delete(f"{ADMIN_URL}/{loc.id}", headers=headers)
    ).status_code == 403
    # The picker is open to every staff role.
    assert (await client.get(PICKER_URL, headers=headers)).status_code == 200


async def test_admin_routes_forbidden_for_goldsmith(
    client: AsyncClient, db_session: AsyncSession, goldsmith_auth_headers: dict
):
    await _assert_admin_forbidden(client, db_session, goldsmith_auth_headers)


async def test_admin_routes_forbidden_for_viewer(
    client: AsyncClient, db_session: AsyncSession, viewer_auth_headers: dict
):
    await _assert_admin_forbidden(client, db_session, viewer_auth_headers)


async def test_picker_hides_deactivated_locations_sorted(
    client: AsyncClient, db_session: AsyncSession, goldsmith_auth_headers: dict
):
    await _location(db_session, "Tresor", sort=20)
    await _location(db_session, "Werkbank 1", sort=10)
    await _location(db_session, "Alt", active=False, sort=5)

    resp = await client.get(PICKER_URL, headers=goldsmith_auth_headers)
    assert resp.status_code == 200
    assert [r["name"] for r in resp.json()] == ["Werkbank 1", "Tresor"]

    resp = await client.get(
        PICKER_URL, params={"active": "false"}, headers=goldsmith_auth_headers
    )
    assert [r["name"] for r in resp.json()] == ["Alt", "Werkbank 1", "Tresor"]


async def test_timer_start_by_id_writes_both_columns_and_survives_deactivation(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    goldsmith_auth_headers: dict,
    test_customer,
):
    loc_id = (await _location(db_session, "Werkbank 1")).id
    order = await _order(db_session, test_customer.id)
    act = await _activity(db_session)

    resp = await client.post(
        "/api/v1/time-tracking/start",
        json={"order_id": order.id, "activity_id": act.id, "location_id": loc_id},
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["location_id"] == loc_id
    assert body["location"] == "Werkbank 1"

    # Deactivated: gone from the picker, but the history row keeps it.
    await client.delete(f"{ADMIN_URL}/{loc_id}", headers=admin_auth_headers)
    db_session.expire_all()
    entry = (
        await db_session.execute(select(TimeEntry).where(TimeEntry.id == body["id"]))
    ).scalar_one()
    assert (entry.location_id, entry.location) == (loc_id, "Werkbank 1")
    picker = (await client.get(PICKER_URL, headers=goldsmith_auth_headers)).json()
    assert loc_id not in [r["id"] for r in picker]


async def test_rename_syncs_legacy_text_columns(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer,
):
    loc_id = (await _location(db_session, "Werkbank 1")).id
    order_id = (await _order(db_session, test_customer.id)).id
    resp = await client.post(
        f"/api/v1/orders/{order_id}/location",
        json={"location_id": loc_id},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["current_location"] == "Werkbank 1"
    assert resp.json()["location_id"] == loc_id

    await client.patch(
        f"{ADMIN_URL}/{loc_id}", json={"name": "Hauptbank"}, headers=admin_auth_headers
    )
    db_session.expire_all()
    refreshed = await db_session.get(Order, order_id)
    assert refreshed.current_location == "Hauptbank"
    history = (
        (
            await db_session.execute(
                select(LocationHistory).where(LocationHistory.order_id == order_id)
            )
        )
        .scalars()
        .all()
    )
    assert [h.location for h in history] == ["Werkbank 1"]


async def test_inactive_location_cannot_be_assigned(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer,
):
    loc = await _location(db_session, "Alt", active=False)
    order = await _order(db_session, test_customer.id)
    resp = await client.post(
        f"/api/v1/orders/{order.id}/location",
        json={"location_id": loc.id},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 422


async def test_legacy_text_is_linked_when_it_matches(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer,
):
    loc = await _location(db_session, "Tresor")
    order = await _order(db_session, test_customer.id)
    resp = await client.post(
        f"/api/v1/orders/{order.id}/location",
        json={"location": "tresor"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["location_id"] == loc.id
    assert resp.json()["current_location"] == "Tresor"

    resp = await client.post(
        f"/api/v1/orders/{order.id}/location",
        json={"location": "Beim Kunden"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["location_id"] is None
    assert resp.json()["current_location"] == "Beim Kunden"


async def test_time_entry_edit_sets_location(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    admin_user,
    test_customer,
):
    from datetime import datetime, timedelta, timezone

    loc = await _location(db_session, "Werkbank 2")
    order = await _order(db_session, test_customer.id)
    act = await _activity(db_session)
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    entry = TimeEntry(
        order_id=order.id,
        user_id=admin_user.id,
        activity_id=act.id,
        start_time=start,
        end_time=start + timedelta(hours=1),
        duration_minutes=60,
    )
    db_session.add(entry)
    await db_session.commit()

    resp = await client.put(
        f"/api/v1/time-tracking/{entry.id}",
        json={"location_id": loc.id},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["location_id"] == loc.id
    assert resp.json()["location"] == "Werkbank 2"


async def test_editing_history_keeps_a_deactivated_location(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    admin_user,
    test_customer,
):
    from datetime import datetime, timedelta, timezone

    loc_id = (await _location(db_session, "Alte Bank", active=False)).id
    order = await _order(db_session, test_customer.id)
    act = await _activity(db_session)
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    entry = TimeEntry(
        order_id=order.id,
        user_id=admin_user.id,
        activity_id=act.id,
        start_time=start,
        end_time=start + timedelta(hours=1),
        duration_minutes=60,
        location="Alte Bank",
        location_id=loc_id,
    )
    db_session.add(entry)
    await db_session.commit()

    resp = await client.put(
        f"/api/v1/time-tracking/{entry.id}",
        json={"location_id": loc_id, "notes": "nachgetragen"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["location_id"] == loc_id
    assert resp.json()["location"] == "Alte Bank"
