"""W2-07: order events written with transitions, the status endpoint and
the merged timeline (ARCH-01, BE-06, DOM-13).

- every transition writes an ``order_events`` row in the SAME transaction
  as the status change; a failed transition writes nothing;
- ``PATCH /orders/{id}/status`` validates via the table: 409 + German
  message listing the allowed next statuses; 422 when on_hold/cancelled
  have no reason;
- PUT/PATCH ``/orders/{id}`` with a status go through the same table;
- ``GET /orders/{id}/timeline`` merges events, customer updates, photos and
  time entries by time; VIEWER gets no financial detail and no design IP.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    Customer,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Order,
    OrderEvent,
    OrderPhoto,
    OrderStatusEnum,
    TimeEntry,
    User,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.services import order_workflow as wf

S = OrderStatusEnum


def _status_url(order_id: int) -> str:
    return f"/api/v1/orders/{order_id}/status"


def _timeline_url(order_id: int) -> str:
    return f"/api/v1/orders/{order_id}/timeline"


async def _order(db: AsyncSession, customer: Customer, status=S.IN_PROGRESS) -> Order:
    order = Order(
        title=f"Timeline {uuid.uuid4().hex[:6]}",
        description="Verlaufstest",
        customer_id=customer.id,
        status=status,
        price=900.0,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _events(db: AsyncSession, order_id: int) -> list[OrderEvent]:
    db.expire_all()
    result = await db.execute(
        select(OrderEvent)
        .where(OrderEvent.order_id == order_id)
        .order_by(OrderEvent.id)
    )
    return list(result.scalars().all())


async def _status_of(db: AsyncSession, order_id: int) -> OrderStatusEnum:
    db.expire_all()
    result = await db.execute(select(Order.status).where(Order.id == order_id))
    return result.scalar_one()


# --------------------------------------------------------------------------- #
# Same-transaction guarantee
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestSameTransaction:
    async def test_rollback_after_transition_discards_status_and_event(
        self, db_session: AsyncSession, test_customer: Customer, admin_user: User
    ):
        order = await _order(db_session, test_customer)
        order_id = order.id
        with pytest.raises(RuntimeError):
            async with transactional(db_session):
                await wf.transition(db_session, order, S.QUALITY_CHECK, admin_user)
                raise RuntimeError("boom after the transition")

        assert await _status_of(db_session, order_id) is S.IN_PROGRESS
        assert await _events(db_session, order_id) == []

    async def test_commit_persists_status_and_event_together(
        self, db_session: AsyncSession, test_customer: Customer, admin_user: User
    ):
        order = await _order(db_session, test_customer)
        order_id = order.id
        async with transactional(db_session):
            await wf.transition(db_session, order, S.QUALITY_CHECK, admin_user)

        assert await _status_of(db_session, order_id) is S.QUALITY_CHECK
        events = await _events(db_session, order_id)
        assert [(e.from_status, e.to_status) for e in events] == [
            ("in_progress", "quality_check")
        ]


# --------------------------------------------------------------------------- #
# PATCH /orders/{id}/status
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestStatusEndpoint:
    async def test_allowed_transition_returns_200_and_writes_event(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        admin_user: User,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer)
        order_id, admin_id = order.id, admin_user.id
        resp = await client.patch(
            _status_url(order_id),
            json={"status": "quality_check"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "quality_check"
        events = await _events(db_session, order_id)
        assert len(events) == 1
        assert events[0].user_id == admin_id
        assert events[0].to_status == "quality_check"

    async def test_delivered_to_in_progress_is_409_german(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer, status=S.DELIVERED)
        order_id = order.id
        resp = await client.patch(
            _status_url(order_id),
            json={"status": "in_progress"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "INVALID_STATUS_TRANSITION"
        assert detail["allowed"] == []
        assert "Ausgeliefert" in detail["message"]
        assert await _status_of(db_session, order_id) is S.DELIVERED
        assert await _events(db_session, order_id) == []

    async def test_409_lists_allowed_next_statuses(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer, status=S.DRAFT)
        order_id = order.id
        resp = await client.patch(
            _status_url(order_id),
            json={"status": "delivered"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["allowed"] == ["confirmed", "cancelled"]
        assert "Bestätigt" in detail["message"]
        assert "Storniert" in detail["message"]

    async def test_on_hold_requires_reason_and_stores_resume_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer)
        order_id = order.id
        missing = await client.patch(
            _status_url(order_id),
            json={"status": "on_hold"},
            headers=admin_auth_headers,
        )
        assert missing.status_code == 422, missing.text
        assert await _events(db_session, order_id) == []

        resume = (date.today() + timedelta(days=10)).isoformat()
        resp = await client.patch(
            _status_url(order_id),
            json={
                "status": "on_hold",
                "reason": "Wartet auf Stein",
                "resume_date": resume,
            },
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "on_hold"
        assert body["hold_reason"] == "Wartet auf Stein"
        assert body["resume_date"] == resume

    async def test_cancel_requires_reason(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer, status=S.CONFIRMED)
        order_id = order.id
        resp = await client.patch(
            _status_url(order_id),
            json={"status": "cancelled", "reason": "Kunde hat storniert"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["cancel_reason"] == "Kunde hat storniert"

    async def test_viewer_cannot_change_status(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer)
        order_id = order.id
        resp = await client.patch(
            _status_url(order_id),
            json={"status": "quality_check"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403
        assert await _events(db_session, order_id) == []

    async def test_unknown_order_is_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.patch(
            _status_url(999999),
            json={"status": "quality_check"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    async def test_generic_put_with_forbidden_status_is_409(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer, status=S.DELIVERED)
        order_id, title = order.id, order.title
        resp = await client.put(
            f"/api/v1/orders/{order_id}",
            json={"status": "in_progress", "title": "Neu"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409, resp.text
        db_session.expire_all()
        refreshed = await db_session.get(Order, order_id)
        # Failed transition writes nothing — not even the title change.
        assert refreshed.title == title
        assert await _events(db_session, order_id) == []

    async def test_generic_patch_with_unchanged_status_is_not_an_error(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer, status=S.DELIVERED)
        order_id = order.id
        resp = await client.patch(
            f"/api/v1/orders/{order_id}",
            json={"status": "delivered", "title": "Umbenannt"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert await _events(db_session, order_id) == []


@pytest.mark.asyncio
async def test_create_order_writes_creation_event_and_defaults_to_draft(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
):
    resp = await client.post(
        "/api/v1/orders/",
        json={
            "title": "Neuer Ring",
            "description": "Ein Ring",
            "customer_id": test_customer.id,
        },
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "draft"  # DOM-46: new code never sets NEW
    events = await _events(db_session, body["id"])
    assert [(e.from_status, e.to_status) for e in events] == [(None, "draft")]


# --------------------------------------------------------------------------- #
# GET /orders/{id}/timeline
# --------------------------------------------------------------------------- #


async def _seed_timeline(
    db: AsyncSession, order: Order, user: User
) -> dict[str, datetime]:
    base = datetime.utcnow() - timedelta(days=5)
    t = {
        "event": base,
        "time_entry": base + timedelta(days=1),
        "photo": base + timedelta(days=2),
        "update": base + timedelta(days=3),
        "cost": base + timedelta(days=4),
    }
    db.add(
        OrderEvent(
            order_id=order.id,
            from_status="confirmed",
            to_status="in_progress",
            user_id=user.id,
            created_at=t["event"],
            meta={"origin": "manual"},
        )
    )
    activity = Activity(name="Fassen", category="setting", created_at=base)
    db.add(activity)
    await db.flush()
    db.add(
        TimeEntry(
            id=str(uuid.uuid4()),
            order_id=order.id,
            user_id=user.id,
            activity_id=activity.id,
            start_time=t["time_entry"],
            end_time=t["time_entry"] + timedelta(minutes=90),
            duration_minutes=90,
            notes="interne Notiz",
            created_at=t["time_entry"],
        )
    )
    db.add(
        OrderPhoto(
            id=str(uuid.uuid4()),
            order_id=order.id,
            file_path="/uploads/secret-design.jpg",
            timestamp=t["photo"],
            taken_by=user.id,
        )
    )
    db.add(
        CustomerUpdate(
            order_id=order.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Ihr Ring ist in der Fassung",
            body="Kundentext",
            status=CustomerUpdateStatus.SENT,
            sent_at=t["update"],
            sent_by=user.id,
            created_at=t["update"],
        )
    )
    db.add(
        CustomerUpdate(
            order_id=order.id,
            kind=CustomerUpdateKind.COST_CHANGE,
            subject="Kostenänderung: +120,00 EUR",
            body="Kostentext",
            status=CustomerUpdateStatus.DRAFT,
            sent_by=user.id,
            created_at=t["cost"],
        )
    )
    await db.commit()
    return t


@pytest.mark.asyncio
class TestTimeline:
    async def test_admin_timeline_merges_all_sources_by_time(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        admin_user: User,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer)
        order_id = order.id
        await _seed_timeline(db_session, order, admin_user)

        resp = await client.get(_timeline_url(order_id), headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["order_id"] == order_id
        kinds = [item["kind"] for item in body["items"]]
        assert kinds == [
            "status",
            "time_entry",
            "photo",
            "customer_update",
            "customer_update",
        ]
        ats = [item["at"] for item in body["items"]]
        assert ats == sorted(ats)
        status_item = body["items"][0]
        assert status_item["data"]["to_status"] == "in_progress"
        assert status_item["data"]["to_label"] == "In Bearbeitung"
        cost_item = body["items"][-1]
        assert cost_item["data"]["subject"] == "Kostenänderung: +120,00 EUR"
        # Customer free text and internal notes never ride on the timeline.
        text = resp.text
        assert "Kundentext" not in text and "interne Notiz" not in text
        assert "secret-design.jpg" not in text

    async def test_viewer_timeline_has_no_financial_or_design_detail(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        admin_user: User,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer)
        order_id = order.id
        await _seed_timeline(db_session, order, admin_user)

        resp = await client.get(_timeline_url(order_id), headers=viewer_auth_headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        kinds = [item["kind"] for item in items]
        assert "photo" not in kinds  # design IP: DESIGN_VIEW only
        assert "120,00" not in resp.text
        cost = [i for i in items if i["data"].get("kind") == "cost_change"]
        assert cost and "subject" not in cost[0]["data"]
        progress = [i for i in items if i["data"].get("kind") == "progress"]
        assert progress[0]["data"]["subject"] == "Ihr Ring ist in der Fassung"

    async def test_timeline_of_status_endpoint_changes(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _order(db_session, test_customer)
        order_id = order.id
        for payload in (
            {"status": "on_hold", "reason": "Wartet auf Kunde"},
            {"status": "in_progress"},
        ):
            resp = await client.patch(
                _status_url(order_id), json=payload, headers=admin_auth_headers
            )
            assert resp.status_code == 200, resp.text

        resp = await client.get(_timeline_url(order_id), headers=admin_auth_headers)
        items = [i for i in resp.json()["items"] if i["kind"] == "status"]
        assert [i["data"]["to_status"] for i in items] == ["on_hold", "in_progress"]
        assert items[0]["data"]["reason"] == "Wartet auf Kunde"
        assert items[0]["summary"] == "In Bearbeitung → Pausiert"

    async def test_timeline_unknown_order_is_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.get(_timeline_url(999999), headers=admin_auth_headers)
        assert resp.status_code == 404
