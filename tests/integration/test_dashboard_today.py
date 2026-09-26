"""GET /api/v1/dashboard/today — the "Heute" work view (W2-03).

Findings: FE-05, DOM-14, DOM-15, DOM-15b (docs/review/2026-09-25/).

Definition of done (05-domain-product-fit.md, section F row 5): an order one
day past its deadline appears in the overdue lane; the customer-pending lane
lists SENT cost changes, failed customer updates and repairs ready but not
collected. VIEWER gets the operational lanes without any price field.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    CostChangeRequest,
    CostChangeStatus,
    Customer,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Order,
    OrderStatusEnum,
    Quote,
    QuoteStatus,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    TimeEntry,
    User,
)
from goldsmith_erp.services.dashboard_service import BERLIN, berlin_today

URL = "/api/v1/dashboard/today"

FINANCIAL_KEYS = frozenset(
    {
        "amount",
        "price",
        "total",
        "new_amount",
        "original_amount",
        "estimated_cost",
        "actual_cost",
        "estimated_value",
    }
)


def _at_noon(days_from_today: int) -> datetime:
    """Naive-UTC timestamp for Berlin noon ``days_from_today`` days away."""
    local_day = berlin_today() + timedelta(days=days_from_today)
    local_noon = datetime.combine(local_day, time(12, 0), tzinfo=BERLIN)
    return local_noon.astimezone(timezone.utc).replace(tzinfo=None)


def _walk_keys(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_keys(item)


@pytest_asyncio.fixture
async def seeded(
    db_session: AsyncSession, goldsmith_user: User, test_customer: Customer
) -> dict[str, int]:
    """One row per bucket plus rows that must NOT show up."""
    overdue_order = Order(
        title="Trauringe Meier",
        status=OrderStatusEnum.IN_PROGRESS,
        customer_id=test_customer.id,
        deadline=_at_noon(-1),
        price=1200.0,
    )
    due_soon_order = Order(
        title="Kette Schulz",
        status=OrderStatusEnum.CONFIRMED,
        customer_id=test_customer.id,
        deadline=_at_noon(2),
        price=300.0,
    )
    far_order = Order(
        title="Anhänger später",
        status=OrderStatusEnum.CONFIRMED,
        customer_id=test_customer.id,
        deadline=_at_noon(20),
    )
    # Overdue but already finished: not overdue work, but waiting for pickup.
    finished_order = Order(
        title="Ohrringe fertig",
        status=OrderStatusEnum.COMPLETED,
        customer_id=test_customer.id,
        deadline=_at_noon(-5),
    )
    delivered_order = Order(
        title="Ring abgeholt",
        status=OrderStatusEnum.DELIVERED,
        customer_id=test_customer.id,
        deadline=_at_noon(-9),
    )
    deleted_order = Order(
        title="Gelöscht",
        status=OrderStatusEnum.IN_PROGRESS,
        customer_id=test_customer.id,
        deadline=_at_noon(-3),
        is_deleted=True,
    )
    cost_change_order = Order(
        title="Collier mit Stein",
        status=OrderStatusEnum.IN_PROGRESS,
        customer_id=test_customer.id,
    )
    db_session.add_all(
        [
            overdue_order,
            due_soon_order,
            far_order,
            finished_order,
            delivered_order,
            deleted_order,
            cost_change_order,
        ]
    )
    await db_session.flush()

    overdue_repair = RepairJob(
        repair_number="REP-2026-0901",
        bag_number="T-11",
        customer_id=test_customer.id,
        item_description="Kettenverschluss defekt",
        item_type=RepairItemType.CHAIN,
        status=RepairJobStatus.IN_REPAIR,
        estimated_completion_date=_at_noon(-2),
        estimated_cost=45.0,
    )
    ready_repair = RepairJob(
        repair_number="REP-2026-0902",
        bag_number="T-12",
        customer_id=test_customer.id,
        item_description="Ring geweitet",
        item_type=RepairItemType.RING,
        status=RepairJobStatus.READY,
        estimated_completion_date=_at_noon(-4),
        estimated_cost=60.0,
    )
    picked_up_repair = RepairJob(
        repair_number="REP-2026-0903",
        bag_number="T-13",
        customer_id=test_customer.id,
        item_description="Abgeholt",
        item_type=RepairItemType.OTHER,
        status=RepairJobStatus.PICKED_UP,
        estimated_completion_date=_at_noon(-6),
    )
    db_session.add_all([overdue_repair, ready_repair, picked_up_repair])
    await db_session.flush()

    cost_change = CostChangeRequest(
        order_id=cost_change_order.id,
        original_amount=800.0,
        new_amount=950.0,
        delta_percent=18.75,
        reason="Größerer Stein",
        status=CostChangeStatus.SENT,
        created_by=goldsmith_user.id,
    )
    draft_cost_change = CostChangeRequest(
        order_id=overdue_order.id,
        original_amount=1200.0,
        new_amount=1300.0,
        delta_percent=8.3,
        reason="Entwurf",
        status=CostChangeStatus.DRAFT,
        created_by=goldsmith_user.id,
    )
    failed_update = CustomerUpdate(
        order_id=overdue_order.id,
        kind=CustomerUpdateKind.PROGRESS,
        subject="Fortschritt",
        body="Ihr Ring ist in Arbeit.",
        status=CustomerUpdateStatus.SEND_FAILED,
        sent_by=goldsmith_user.id,
    )
    sent_update = CustomerUpdate(
        order_id=due_soon_order.id,
        kind=CustomerUpdateKind.PROGRESS,
        subject="Fortschritt",
        body="Verschickt.",
        status=CustomerUpdateStatus.SENT,
        sent_by=goldsmith_user.id,
    )
    quote = Quote(
        quote_number="KV-2026-0901",
        customer_id=test_customer.id,
        created_by=goldsmith_user.id,
        status=QuoteStatus.SENT,
        valid_until=_at_noon(5),
        total=499.0,
    )
    activity = Activity(name="Polieren", category="finishing")
    db_session.add_all(
        [cost_change, draft_cost_change, failed_update, sent_update, quote, activity]
    )
    await db_session.flush()

    running = TimeEntry(
        order_id=overdue_order.id,
        user_id=goldsmith_user.id,
        activity_id=activity.id,
        start_time=datetime.utcnow() - timedelta(minutes=30),
    )
    db_session.add(running)
    await db_session.commit()

    return {
        "overdue_order": overdue_order.id,
        "due_soon_order": due_soon_order.id,
        "far_order": far_order.id,
        "finished_order": finished_order.id,
        "delivered_order": delivered_order.id,
        "deleted_order": deleted_order.id,
        "cost_change_order": cost_change_order.id,
        "overdue_repair": overdue_repair.id,
        "ready_repair": ready_repair.id,
        "picked_up_repair": picked_up_repair.id,
        "cost_change": cost_change.id,
        "failed_update": failed_update.id,
        "quote": quote.id,
        "running_entry": running.id,
    }


@pytest.mark.asyncio
async def test_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get(URL)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_overdue_lane_sorted_by_days_overdue_desc(
    client: AsyncClient, goldsmith_auth_headers: dict, seeded: dict[str, int]
) -> None:
    resp = await client.get(URL, headers=goldsmith_auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    overdue = [(i["kind"], i["id"], i["days_overdue"]) for i in body["overdue"]]
    assert overdue == [
        ("repair", seeded["overdue_repair"], 2),
        ("order", seeded["overdue_order"], 1),
    ]
    assert body["counts"]["overdue"] == 2
    order_row = body["overdue"][1]
    assert order_row["title"] == "Trauringe Meier"
    assert order_row["customer_name"] == "Maria Mustermann"
    assert order_row["due_date"] == (berlin_today() - timedelta(days=1)).isoformat()
    repair_row = body["overdue"][0]
    assert repair_row["reference"] == "REP-2026-0901"
    assert repair_row["bag_number"] == "T-11"


@pytest.mark.asyncio
async def test_due_soon_lane_holds_next_three_days_only(
    client: AsyncClient, goldsmith_auth_headers: dict, seeded: dict[str, int]
) -> None:
    body = (await client.get(URL, headers=goldsmith_auth_headers)).json()
    due_soon = [(i["kind"], i["id"], i["days_overdue"]) for i in body["due_soon"]]
    assert due_soon == [("order", seeded["due_soon_order"], -2)]


@pytest.mark.asyncio
async def test_terminal_and_deleted_rows_excluded_from_deadline_lanes(
    client: AsyncClient, goldsmith_auth_headers: dict, seeded: dict[str, int]
) -> None:
    body = (await client.get(URL, headers=goldsmith_auth_headers)).json()
    deadline_ids = {(i["kind"], i["id"]) for i in body["overdue"] + body["due_soon"]}
    for key in (
        "finished_order",
        "delivered_order",
        "deleted_order",
        "far_order",
    ):
        assert ("order", seeded[key]) not in deadline_ids, key
    for key in ("ready_repair", "picked_up_repair"):
        assert ("repair", seeded[key]) not in deadline_ids, key


@pytest.mark.asyncio
async def test_customer_pending_lane_lists_every_waiting_item(
    client: AsyncClient, goldsmith_auth_headers: dict, seeded: dict[str, int]
) -> None:
    body = (await client.get(URL, headers=goldsmith_auth_headers)).json()
    pending = {(i["kind"], i["id"]) for i in body["customer_pending"]}
    assert pending == {
        ("cost_change", seeded["cost_change"]),
        ("customer_update", seeded["failed_update"]),
        ("repair_ready", seeded["ready_repair"]),
        ("order_ready", seeded["finished_order"]),
        ("quote", seeded["quote"]),
    }
    by_kind = {i["kind"]: i for i in body["customer_pending"]}
    assert by_kind["cost_change"]["order_id"] == seeded["cost_change_order"]
    assert by_kind["cost_change"]["amount"] == 950.0
    assert by_kind["customer_update"]["order_id"] == seeded["overdue_order"]
    assert by_kind["repair_ready"]["repair_id"] == seeded["ready_repair"]
    assert by_kind["quote"]["quote_id"] == seeded["quote"]
    assert by_kind["quote"]["amount"] == 499.0
    assert body["counts"]["customer_pending"] == 5


@pytest.mark.asyncio
async def test_timers_lane_shows_running_entry(
    client: AsyncClient, goldsmith_auth_headers: dict, seeded: dict[str, int]
) -> None:
    body = (await client.get(URL, headers=goldsmith_auth_headers)).json()
    timers = body["timers"]
    assert [t["id"] for t in timers] == [seeded["running_entry"]]
    assert timers[0]["is_running"] is True
    assert timers[0]["order_id"] == seeded["overdue_order"]
    assert timers[0]["activity_name"] == "Polieren"


@pytest.mark.asyncio
async def test_goldsmith_sees_financial_flag(
    client: AsyncClient, goldsmith_auth_headers: dict, seeded: dict[str, int]
) -> None:
    body = (await client.get(URL, headers=goldsmith_auth_headers)).json()
    assert body["can_view_financials"] is True
    assert date.fromisoformat(body["today"]) == berlin_today()


@pytest.mark.asyncio
async def test_viewer_gets_operational_lanes_without_prices(
    client: AsyncClient, viewer_auth_headers: dict, seeded: dict[str, int]
) -> None:
    resp = await client.get(URL, headers=viewer_auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    leaked = FINANCIAL_KEYS.intersection(_walk_keys(body))
    assert not leaked, f"VIEWER received financial keys: {sorted(leaked)}"
    assert body["can_view_financials"] is False

    # Deadline lanes are operational and stay visible.
    assert [i["id"] for i in body["overdue"]] == [
        seeded["overdue_repair"],
        seeded["overdue_order"],
    ]
    # Cost changes, customer updates and quotes need permissions VIEWER lacks.
    kinds = {i["kind"] for i in body["customer_pending"]}
    assert kinds == {"repair_ready", "order_ready"}
    # VIEWER does not track time on this order: no foreign timers.
    assert body["timers"] == []


@pytest.mark.asyncio
async def test_admin_sees_all_running_timers(
    client: AsyncClient, admin_auth_headers: dict, seeded: dict[str, int]
) -> None:
    body = (await client.get(URL, headers=admin_auth_headers)).json()
    assert [t["id"] for t in body["timers"]] == [seeded["running_entry"]]
    assert body["timers"][0]["user_name"] == "Integration Goldsmith"


async def _count_selects(
    client: AsyncClient, headers: dict, session: AsyncSession
) -> int:
    """Number of SELECTs the endpoint issues (audit INSERTs are ignored)."""
    statements: list[str] = []

    def _record(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        statements.append(statement)

    engine = session.bind.sync_engine  # type: ignore[union-attr]
    event.listen(engine, "before_cursor_execute", _record)
    try:
        resp = await client.get(URL, headers=headers)
        assert resp.status_code == 200, resp.text
    finally:
        event.remove(engine, "before_cursor_execute", _record)
    return sum(1 for s in statements if s.lstrip().upper().startswith("SELECT"))


@pytest.mark.asyncio
async def test_query_count_does_not_grow_with_rows(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    seeded: dict[str, int],
) -> None:
    """No N+1: five more overdue orders with their own customers add no query."""
    before = await _count_selects(client, admin_auth_headers, db_session)

    for n in range(5):
        customer = Customer(
            first_name=f"Kunde{n}",
            last_name="Test",
            email=f"n1-{n}-{seeded['overdue_order']}@integration-test.example.com",
            customer_type="private",
            is_active=True,
        )
        db_session.add(customer)
        await db_session.flush()
        db_session.add(
            Order(
                title=f"Überfällig {n}",
                status=OrderStatusEnum.IN_PROGRESS,
                customer_id=customer.id,
                deadline=_at_noon(-(n + 3)),
            )
        )
    await db_session.commit()

    after = await _count_selects(client, admin_auth_headers, db_session)
    assert after == before
