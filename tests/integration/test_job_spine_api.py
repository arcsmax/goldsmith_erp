"""ARCH phase 5 integration: repair invoicing, /jobs, timelines, dashboard.

Endpoints:
  POST /api/v1/repairs/{id}/invoice
  GET  /api/v1/jobs/            (paged, kind/status/customer/q/sort)
  GET  /api/v1/jobs/{id}
  GET  /api/v1/jobs/{id}/timeline
  GET  /api/v1/dashboard/today  (job_id on order and repair items)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    Invoice,
    Order,
    OrderStatusEnum,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
)
from goldsmith_erp.services.invoice_snapshot_service import InvoiceSnapshotService
from goldsmith_erp.services.number_sequence_service import berlin_year
from goldsmith_erp.services.status_report_service import build_repair_status_report

pytestmark = pytest.mark.asyncio

REPAIRS_URL = "/api/v1/repairs"
JOBS_URL = "/api/v1/jobs/"


@pytest_asyncio.fixture
async def cid(test_customer: Customer) -> int:
    """The test customer's id, read before any API commit expires the row."""
    return int(test_customer.id)


def _due() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()


async def _repair_via_api(
    client: AsyncClient, headers: dict, customer_id: int | None
) -> dict:
    payload: dict[str, Any] = {
        "item_description": "Ehering weiten",
        "item_type": RepairItemType.RING.value,
    }
    if customer_id is not None:
        payload["customer_id"] = customer_id
    resp = await client.post(f"{REPAIRS_URL}/", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _advance_to_ready(
    client: AsyncClient, headers: dict, repair_id: int, actual_cost: float | None
) -> None:
    steps: list[tuple[str, dict]] = [
        ("diagnose", {"diagnosis_notes": "Schiene dünn", "estimated_cost": 60.0}),
        ("approve", {}),
        ("start", {}),
        ("quality-check", {}),
    ]
    for action, body in steps:
        resp = await client.post(
            f"{REPAIRS_URL}/{repair_id}/{action}", json=body, headers=headers
        )
        assert resp.status_code == 200, (action, resp.text)
    if actual_cost is not None:
        resp = await client.post(
            f"{REPAIRS_URL}/{repair_id}/complete",
            json={"actual_cost": actual_cost},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text


async def _invoice(client: AsyncClient, headers: dict, repair_id: int):
    return await client.post(
        f"{REPAIRS_URL}/{repair_id}/invoice", json={"due_date": _due()}, headers=headers
    )


async def _job_id(db: AsyncSession, repair_id: int) -> int:
    db.expire_all()
    repair = (
        await db.execute(select(RepairJob).where(RepairJob.id == repair_id))
    ).scalar_one()
    return int(repair.job_id)


# --------------------------------------------------------------------------- #
# Repair invoicing
# --------------------------------------------------------------------------- #


async def test_ready_repair_is_invoiced_with_net_price_and_snapshot(
    client: AsyncClient,
    admin_auth_headers: dict,
    cid: int,
    db_session: AsyncSession,
):
    repair = await _repair_via_api(client, admin_auth_headers, cid)
    await _advance_to_ready(client, admin_auth_headers, repair["id"], 80.0)

    resp = await _invoice(client, admin_auth_headers, repair["id"])

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["order_id"] is None
    assert body["job_id"] == await _job_id(db_session, repair["id"])
    assert body["customer_id"] == cid
    assert body["invoice_number"] == f"RE-{berlin_year()}-0001"
    assert Decimal(str(body["subtotal"])) == Decimal("80.00")
    assert Decimal(str(body["tax_rate"])) == Decimal("19.0")
    assert Decimal(str(body["total"])) == Decimal("95.20")
    (line,) = body["line_items"]
    assert line["line_type"] == "labor"
    assert line["description"] == f"Reparatur {repair['repair_number']}"
    assert body["service_date"] is not None

    invoice = (
        await db_session.execute(select(Invoice).where(Invoice.id == body["id"]))
    ).scalar_one()
    snapshot = InvoiceSnapshotService.load(invoice)
    assert snapshot is not None
    assert snapshot["invoice"]["order_id"] is None
    assert snapshot["invoice"]["order_title"] == f"Reparatur {repair['repair_number']}"
    assert snapshot["invoice"]["reference"] == repair["repair_number"]
    assert snapshot["invoice"]["reference_label"] == "Reparaturnummer:"
    assert snapshot["recipient"]["name"]
    assert snapshot["seller"]


async def test_repair_invoice_pdf_names_the_repair(
    client: AsyncClient, admin_auth_headers: dict, cid: int
):
    repair = await _repair_via_api(client, admin_auth_headers, cid)
    await _advance_to_ready(client, admin_auth_headers, repair["id"], 50.0)
    created = (await _invoice(client, admin_auth_headers, repair["id"])).json()

    resp = await client.get(
        f"/api/v1/invoices/{created['id']}/pdf", headers=admin_auth_headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.content[:4] == b"%PDF"


async def test_second_live_invoice_for_a_repair_is_409(
    client: AsyncClient, admin_auth_headers: dict, cid: int
):
    repair = await _repair_via_api(client, admin_auth_headers, cid)
    await _advance_to_ready(client, admin_auth_headers, repair["id"], 40.0)
    assert (await _invoice(client, admin_auth_headers, repair["id"])).status_code == 201

    resp = await _invoice(client, admin_auth_headers, repair["id"])

    assert resp.status_code == 409, resp.text


async def test_unfinished_repair_is_422(
    client: AsyncClient, admin_auth_headers: dict, cid: int
):
    repair = await _repair_via_api(client, admin_auth_headers, cid)

    resp = await _invoice(client, admin_auth_headers, repair["id"])

    assert resp.status_code == 422, resp.text
    assert "fertige" in resp.text


async def test_repair_without_customer_is_422(
    client: AsyncClient, admin_auth_headers: dict
):
    repair = await _repair_via_api(client, admin_auth_headers, None)
    await _advance_to_ready(client, admin_auth_headers, repair["id"], 40.0)

    resp = await _invoice(client, admin_auth_headers, repair["id"])

    assert resp.status_code == 422, resp.text
    assert "Kunde" in resp.text


async def test_repair_without_price_is_422(
    client: AsyncClient,
    admin_auth_headers: dict,
    cid: int,
    db_session: AsyncSession,
):
    repair = RepairJob(
        repair_number="REP-2026-0500",
        bag_number="TU-2026-0500",
        customer_id=cid,
        item_description="Uhr",
        item_type=RepairItemType.WATCH,
        status=RepairJobStatus.READY,
    )
    db_session.add(repair)
    await db_session.commit()

    resp = await _invoice(client, admin_auth_headers, int(repair.id))

    assert resp.status_code == 422, resp.text
    assert "Preis" in resp.text


async def test_unknown_repair_is_404_and_viewer_is_403(
    client: AsyncClient, admin_auth_headers: dict, viewer_auth_headers: dict
):
    assert (await _invoice(client, admin_auth_headers, 999999)).status_code == 404
    assert (await _invoice(client, viewer_auth_headers, 1)).status_code == 403


async def test_order_invoice_gets_the_order_job_id(
    client: AsyncClient,
    admin_auth_headers: dict,
    cid: int,
    db_session: AsyncSession,
):
    order = Order(
        title="Trauring",
        customer_id=cid,
        status=OrderStatusEnum.COMPLETED,
        price=Decimal("500"),
        completed_at=datetime(2026, 9, 20, 15, 0),
    )
    db_session.add(order)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/invoices/",
        json={"order_id": order.id, "due_date": _due()},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 201, resp.text
    await db_session.refresh(order)
    assert order.job_id is not None
    assert resp.json()["job_id"] == order.job_id


# --------------------------------------------------------------------------- #
# /jobs
# --------------------------------------------------------------------------- #


async def _order_via_api(
    client: AsyncClient, headers: dict, customer_id: int, title: str
) -> dict:
    resp = await client.post(
        "/api/v1/orders/",
        json={
            "title": title,
            "description": "Gelbgold 585",
            "customer_id": customer_id,
            "price": 300.0,
        },
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def test_jobs_list_covers_both_kinds_with_filters(
    client: AsyncClient, admin_auth_headers: dict, cid: int
):
    order = await _order_via_api(client, admin_auth_headers, cid, "Anhänger")
    repair = await _repair_via_api(client, admin_auth_headers, cid)

    resp = await client.get(JOBS_URL, headers=admin_auth_headers)
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert page["total"] == 2
    kinds = {item["kind"]: item for item in page["items"]}
    assert kinds["order"]["order_id"] == order["id"]
    assert kinds["order"]["number"].startswith(f"AU-{berlin_year()}-")
    assert kinds["order"]["status"] == "draft"
    assert kinds["order"]["status_label"] == "Entwurf"
    assert kinds["repair"]["repair_id"] == repair["id"]
    assert kinds["repair"]["number"] == repair["repair_number"]
    assert kinds["repair"]["status"] == "intake"
    assert kinds["repair"]["customer"]["display_name"]
    assert Decimal(str(kinds["order"]["agreed_price"])) == Decimal("300")

    only_repairs = (
        await client.get(
            JOBS_URL, params={"kind": "repair"}, headers=admin_auth_headers
        )
    ).json()
    assert [i["kind"] for i in only_repairs["items"]] == ["repair"]
    by_status = (
        await client.get(
            JOBS_URL,
            params=[("status", "draft"), ("status", "ready")],
            headers=admin_auth_headers,
        )
    ).json()
    assert [i["kind"] for i in by_status["items"]] == ["order"]
    by_q = (
        await client.get(JOBS_URL, params={"q": "Anhänger"}, headers=admin_auth_headers)
    ).json()
    assert by_q["total"] == 1
    by_customer = (
        await client.get(
            JOBS_URL, params={"customer_id": cid}, headers=admin_auth_headers
        )
    ).json()
    assert by_customer["total"] == 2
    sorted_page = (
        await client.get(
            JOBS_URL, params={"sort": "number", "limit": 1}, headers=admin_auth_headers
        )
    ).json()
    assert sorted_page["items"][0]["kind"] == "order"  # "AU-" < "REP-"
    assert sorted_page["next_offset"] == 1


async def test_jobs_list_rejects_unknown_sort_field(
    client: AsyncClient, admin_auth_headers: dict
):
    resp = await client.get(
        JOBS_URL, params={"sort": "agreed_price"}, headers=admin_auth_headers
    )
    assert resp.status_code == 422


async def test_viewer_sees_jobs_without_price(
    client: AsyncClient,
    admin_auth_headers: dict,
    viewer_auth_headers: dict,
    cid: int,
):
    await _order_via_api(client, admin_auth_headers, cid, "Brosche")

    resp = await client.get(JOBS_URL, headers=viewer_auth_headers)

    assert resp.status_code == 200, resp.text
    (item,) = resp.json()["items"]
    assert "agreed_price" not in item
    single = await client.get(f"{JOBS_URL}{item['id']}", headers=viewer_auth_headers)
    assert single.status_code == 200
    assert "agreed_price" not in single.json()


async def test_jobs_require_auth_and_unknown_job_is_404(
    client: AsyncClient, admin_auth_headers: dict
):
    assert (await client.get(JOBS_URL)).status_code == 401
    assert (
        await client.get(f"{JOBS_URL}999999", headers=admin_auth_headers)
    ).status_code == 404


async def test_job_timeline_delegates_per_kind(
    client: AsyncClient,
    admin_auth_headers: dict,
    viewer_auth_headers: dict,
    cid: int,
    db_session: AsyncSession,
):
    order = await _order_via_api(client, admin_auth_headers, cid, "Kette")
    repair = await _repair_via_api(client, admin_auth_headers, cid)
    await _advance_to_ready(client, admin_auth_headers, repair["id"], 30.0)
    jobs = {
        i["kind"]: i
        for i in (await client.get(JOBS_URL, headers=admin_auth_headers)).json()[
            "items"
        ]
    }

    order_tl = await client.get(
        f"{JOBS_URL}{jobs['order']['id']}/timeline", headers=admin_auth_headers
    )
    assert order_tl.status_code == 200, order_tl.text
    body = order_tl.json()
    assert body["kind"] == "order" and body["order_id"] == order["id"]
    assert body["items"][0]["summary"].startswith("Angelegt")

    repair_tl = await client.get(
        f"{JOBS_URL}{jobs['repair']['id']}/timeline", headers=viewer_auth_headers
    )
    assert repair_tl.status_code == 200, repair_tl.text
    items = repair_tl.json()["items"]
    status_items = [i for i in items if i["kind"] == "status"]
    assert [i["data"]["to_status"] for i in status_items] == [
        "received",
        "diagnosed",
        "quoted",
        "approved",
        "in_repair",
        "quality_check",
        "ready",
    ]
    assert status_items[-1]["data"]["to_label"] == "Abholbereit"
    # The pickup-ready Kundeninfo draft is on the repair timeline too.
    assert any(i["kind"] == "customer_update" for i in items)


# --------------------------------------------------------------------------- #
# Attach points: customer updates, status report, dashboard
# --------------------------------------------------------------------------- #


async def test_repair_customer_update_and_status_report_use_the_job(
    client: AsyncClient,
    admin_auth_headers: dict,
    cid: int,
    db_session: AsyncSession,
):
    repair = await _repair_via_api(client, admin_auth_headers, cid)
    await _advance_to_ready(client, admin_auth_headers, repair["id"], 30.0)
    job_id = await _job_id(db_session, repair["id"])

    update = (
        await db_session.execute(
            select(CustomerUpdate).where(CustomerUpdate.repair_job_id == repair["id"])
        )
    ).scalar_one()
    assert update.job_id == job_id

    report = await build_repair_status_report(db_session, repair["id"])
    summaries = [event.summary for event in report.events]
    assert summaries[0] == "Reparatur angenommen"
    assert "Status geändert: Qualitätskontrolle → Abholbereit" in summaries


async def test_dashboard_items_carry_the_job_id_for_orders_and_repairs(
    client: AsyncClient,
    admin_auth_headers: dict,
    cid: int,
    db_session: AsyncSession,
):
    overdue = datetime.now(timezone.utc) - timedelta(days=2)
    order = await _order_via_api(client, admin_auth_headers, cid, "Ring")
    await client.patch(
        f"/api/v1/orders/{order['id']}",
        json={"deadline": overdue.isoformat()},
        headers=admin_auth_headers,
    )
    repair = await _repair_via_api(client, admin_auth_headers, cid)
    row = (
        await db_session.execute(select(RepairJob).where(RepairJob.id == repair["id"]))
    ).scalar_one()
    row.estimated_completion_date = overdue
    await db_session.commit()

    resp = await client.get("/api/v1/dashboard/today", headers=admin_auth_headers)

    assert resp.status_code == 200, resp.text
    overdue_items = {i["kind"]: i for i in resp.json()["overdue"]}
    assert overdue_items["repair"]["job_id"] == await _job_id(db_session, repair["id"])
    db_session.expire_all()
    order_row = (
        await db_session.execute(select(Order).where(Order.id == order["id"]))
    ).scalar_one()
    assert overdue_items["order"]["job_id"] == order_row.job_id
