# src/goldsmith_erp/services/dashboard_service.py
"""The "Heute" start-of-day view (W2-03; FE-05, DOM-14, DOM-15, DOM-15b).

One server-side summary replaces the old client-side work queue, which
fetched the newest 100 orders, ranked overdue work lowest and ignored
repairs and everything waiting on the customer.

Lanes:

* ``overdue``          orders and repairs past their due date, most days
                       overdue first.
* ``due_soon``         due today or within ``DUE_SOON_DAYS`` days.
* ``customer_pending`` cost changes SENT (waiting for approval), customer
                       updates that failed to send, repairs READY and orders
                       COMPLETED but not collected, quotes SENT.
* ``timers``           time entries started today or still running.

Query budget: one SELECT per lane and entity type (7 in total), each with
``selectinload`` for the rows it displays, so the row count never adds
queries. Each lane is capped at ``LANE_CAP`` rows; ``truncated`` tells the
caller when the cap was hit.

Dates: timestamps are stored as naive UTC (ADR-2026-09-25). "Today" and a
row's due date are the calendar day in Europe/Berlin, the workshop's day.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.permissions import Permission, has_permission
from goldsmith_erp.db.models import (
    CostChangeRequest,
    CostChangeStatus,
    CustomerUpdate,
    CustomerUpdateStatus,
    Order,
    OrderStatusEnum,
    Quote,
    QuoteStatus,
    RepairJob,
    RepairJobStatus,
    TimeEntry,
    User,
)
from goldsmith_erp.models.dashboard import (
    DashboardToday,
    LaneCounts,
    PendingItem,
    TimerItem,
    WorkItem,
)

logger = logging.getLogger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")

# ORM rows (Order, RepairJob, CostChangeRequest, CustomerUpdate, Quote,
# TimeEntry, Customer). The legacy Column(...) declarations type every
# attribute as Column[T] for mypy, so mapper parameters take Any.
OrmRow = Any

# Due today or within this many days -> "due soon".
DUE_SOON_DAYS = 3
# Safety cap per lane and entity type. A small workshop stays far below it.
LANE_CAP = 200

# Orders that are no longer bench work. COMPLETED orders are finished and
# wait for pickup (customer-pending lane), DELIVERED ones are done.
# TODO(W2-07 / DOM-13): add OrderStatusEnum.ON_HOLD and OrderStatusEnum.CANCELLED
# here once those statuses exist, so parked and cancelled orders leave the
# overdue and due-soon lanes (on-hold gets its own lane in W2-07).
ORDER_NOT_BENCH_WORK: frozenset[OrderStatusEnum] = frozenset(
    {OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED}
)

# Repairs that are no longer bench work (READY waits for pickup instead).
REPAIR_NOT_BENCH_WORK: frozenset[RepairJobStatus] = frozenset(
    {RepairJobStatus.READY, RepairJobStatus.PICKED_UP, RepairJobStatus.CANCELLED}
)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def berlin_today(now_utc: Optional[datetime] = None) -> date:
    """The workshop's calendar day for ``now_utc`` (default: now)."""
    moment = now_utc or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(BERLIN).date()


def _berlin_date(stored_utc: datetime) -> date:
    """Calendar day in Berlin of a naive-UTC stored timestamp."""
    return stored_utc.replace(tzinfo=timezone.utc).astimezone(BERLIN).date()


def _day_start_utc(day: date) -> datetime:
    """Naive-UTC instant of Berlin midnight at the start of ``day``."""
    local_midnight = datetime.combine(day, time.min, tzinfo=BERLIN)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def _customer_name(customer: Optional[OrmRow]) -> Optional[str]:
    if customer is None:
        return None
    name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
    return name or None


def _status_value(status: Any) -> str:
    return str(getattr(status, "value", status))


# ---------------------------------------------------------------------------
# Row mappers (pure)
# ---------------------------------------------------------------------------


def _order_work_item(order: OrmRow, today: date) -> WorkItem:
    due = _berlin_date(order.deadline)
    return WorkItem(
        kind="order",
        id=order.id,
        reference=f"#{order.id}",
        title=order.title or f"Auftrag #{order.id}",
        status=_status_value(order.status),
        due_date=due,
        days_overdue=(today - due).days,
        customer_id=order.customer_id,
        customer_name=_customer_name(order.customer),
    )


def _repair_work_item(repair: OrmRow, today: date) -> WorkItem:
    due = _berlin_date(repair.estimated_completion_date)
    return WorkItem(
        kind="repair",
        id=repair.id,
        reference=repair.repair_number,
        title=repair.item_description,
        status=_status_value(repair.status),
        due_date=due,
        days_overdue=(today - due).days,
        customer_id=repair.customer_id,
        customer_name=_customer_name(repair.customer),
        bag_number=repair.bag_number,
    )


def split_deadline_lanes(
    items: Iterable[WorkItem],
) -> tuple[list[WorkItem], list[WorkItem]]:
    """Split into (overdue, due_soon).

    Overdue: most days overdue first. Due soon: soonest first. Ties keep
    orders and repairs in a stable order by kind and id.
    """
    rows = list(items)
    overdue = sorted(
        (i for i in rows if i.days_overdue > 0),
        key=lambda i: (-i.days_overdue, i.kind, i.id),
    )
    due_soon = sorted(
        (i for i in rows if -DUE_SOON_DAYS <= i.days_overdue <= 0),
        key=lambda i: (-i.days_overdue, i.kind, i.id),
    )
    return overdue, due_soon


def _cost_change_item(change: OrmRow) -> PendingItem:
    order = change.order
    return PendingItem(
        kind="cost_change",
        id=change.id,
        title=(order.title if order and order.title else f"Auftrag #{change.order_id}"),
        reference=f"#{change.order_id}",
        since=change.updated_at or change.created_at,
        customer_id=order.customer_id if order else None,
        customer_name=_customer_name(order.customer) if order else None,
        order_id=change.order_id,
        amount=change.new_amount,
    )


def _customer_update_item(update: OrmRow) -> PendingItem:
    order, repair = update.order, update.repair_job
    if repair is not None:
        title = repair.item_description
        reference = repair.repair_number
        customer = repair.customer
        customer_id = repair.customer_id
    else:
        title = order.title if order and order.title else "Kundeninfo"
        reference = f"#{update.order_id}" if update.order_id else "Kundeninfo"
        customer = order.customer if order else None
        customer_id = order.customer_id if order else None
    return PendingItem(
        kind="customer_update",
        id=update.id,
        title=title,
        reference=reference,
        since=update.sent_at or update.updated_at or update.created_at,
        customer_id=customer_id,
        customer_name=_customer_name(customer),
        order_id=update.order_id,
        repair_id=update.repair_job_id,
    )


def _repair_ready_item(repair: OrmRow) -> PendingItem:
    return PendingItem(
        kind="repair_ready",
        id=repair.id,
        title=repair.item_description,
        reference=repair.repair_number,
        since=repair.actual_completion_date or repair.updated_at,
        customer_id=repair.customer_id,
        customer_name=_customer_name(repair.customer),
        repair_id=repair.id,
        bag_number=repair.bag_number,
    )


def _order_ready_item(order: OrmRow) -> PendingItem:
    return PendingItem(
        kind="order_ready",
        id=order.id,
        title=order.title or f"Auftrag #{order.id}",
        reference=f"#{order.id}",
        since=order.completed_at or order.updated_at or order.created_at,
        customer_id=order.customer_id,
        customer_name=_customer_name(order.customer),
        order_id=order.id,
    )


def _quote_item(quote: OrmRow) -> PendingItem:
    return PendingItem(
        kind="quote",
        id=quote.id,
        title=f"Angebot {quote.quote_number}",
        reference=quote.quote_number,
        since=quote.updated_at or quote.created_at,
        customer_id=quote.customer_id,
        customer_name=_customer_name(quote.customer),
        order_id=quote.order_id,
        quote_id=quote.id,
        valid_until=_berlin_date(quote.valid_until) if quote.valid_until else None,
        amount=quote.total,
    )


def _timer_item(entry: OrmRow) -> TimerItem:
    user = entry.user
    user_name = (
        f"{user.first_name or ''} {user.last_name or ''}".strip() if user else None
    )
    return TimerItem(
        id=entry.id,
        order_id=entry.order_id,
        order_title=entry.order.title if entry.order else None,
        user_id=entry.user_id,
        user_name=user_name or None,
        activity_name=entry.activity.name if entry.activity else None,
        start_time=entry.start_time,
        end_time=entry.end_time,
        duration_minutes=entry.duration_minutes,
        is_running=entry.end_time is None,
    )


# ---------------------------------------------------------------------------
# Queries: one SELECT per lane and entity type
# ---------------------------------------------------------------------------


async def _fetch(db: AsyncSession, stmt: Any) -> Sequence[Any]:
    result = await db.execute(stmt.limit(LANE_CAP + 1))
    return result.scalars().unique().all()


def _active_orders() -> Any:
    return select(Order).where(Order.is_deleted.is_not(True))


def _active_repairs() -> Any:
    return select(RepairJob).where(RepairJob.is_deleted.is_not(True))


async def _orders_with_deadline(db: AsyncSession, horizon: datetime) -> Sequence[Any]:
    stmt = (
        _active_orders()
        .options(selectinload(Order.customer))
        .where(
            Order.deadline.is_not(None),
            Order.deadline < horizon,
            Order.status.not_in(ORDER_NOT_BENCH_WORK),
        )
        .order_by(Order.deadline.asc(), Order.id.asc())
    )
    return await _fetch(db, stmt)


async def _repairs_with_deadline(db: AsyncSession, horizon: datetime) -> Sequence[Any]:
    stmt = (
        _active_repairs()
        .options(selectinload(RepairJob.customer))
        .where(
            RepairJob.estimated_completion_date.is_not(None),
            RepairJob.estimated_completion_date < horizon,
            RepairJob.status.not_in(REPAIR_NOT_BENCH_WORK),
        )
        .order_by(RepairJob.estimated_completion_date.asc(), RepairJob.id.asc())
    )
    return await _fetch(db, stmt)


async def _sent_cost_changes(db: AsyncSession) -> Sequence[Any]:
    stmt = (
        select(CostChangeRequest)
        .join(CostChangeRequest.order)
        .options(selectinload(CostChangeRequest.order).selectinload(Order.customer))
        .where(
            CostChangeRequest.status == CostChangeStatus.SENT,
            Order.is_deleted.is_not(True),
        )
        .order_by(CostChangeRequest.updated_at.asc())
    )
    return await _fetch(db, stmt)


async def _failed_customer_updates(db: AsyncSession) -> Sequence[Any]:
    stmt = (
        select(CustomerUpdate)
        .options(
            selectinload(CustomerUpdate.order).selectinload(Order.customer),
            selectinload(CustomerUpdate.repair_job).selectinload(RepairJob.customer),
        )
        .where(
            CustomerUpdate.status == CustomerUpdateStatus.SEND_FAILED,
            or_(
                CustomerUpdate.order_id.is_not(None),
                CustomerUpdate.repair_job_id.is_not(None),
            ),
        )
        .order_by(CustomerUpdate.updated_at.asc())
    )
    return await _fetch(db, stmt)


async def _ready_repairs(db: AsyncSession) -> Sequence[Any]:
    stmt = (
        _active_repairs()
        .options(selectinload(RepairJob.customer))
        .where(RepairJob.status == RepairJobStatus.READY)
        .order_by(RepairJob.updated_at.asc())
    )
    return await _fetch(db, stmt)


async def _completed_orders(db: AsyncSession) -> Sequence[Any]:
    stmt = (
        _active_orders()
        .options(selectinload(Order.customer))
        .where(Order.status == OrderStatusEnum.COMPLETED)
        .order_by(Order.updated_at.asc())
    )
    return await _fetch(db, stmt)


async def _sent_quotes(db: AsyncSession) -> Sequence[Any]:
    stmt = (
        select(Quote)
        .options(selectinload(Quote.customer))
        .where(Quote.status == QuoteStatus.SENT)
        .order_by(Quote.valid_until.asc())
    )
    return await _fetch(db, stmt)


async def _todays_timers(
    db: AsyncSession, user: User, day_start: datetime
) -> Sequence[Any]:
    stmt = (
        select(TimeEntry)
        .options(
            selectinload(TimeEntry.order),
            selectinload(TimeEntry.activity),
            selectinload(TimeEntry.user),
        )
        .where(or_(TimeEntry.end_time.is_(None), TimeEntry.start_time >= day_start))
        .order_by(TimeEntry.start_time.desc())
    )
    if not has_permission(user, Permission.TIME_VIEW_ALL):
        stmt = stmt.where(TimeEntry.user_id == user.id)
    return await _fetch(db, stmt)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class _LaneCollector:
    """Caps each fetched row set at ``LANE_CAP`` and remembers truncation."""

    def __init__(self) -> None:
        self.truncated = False

    def keep(self, rows: Sequence[Any]) -> Sequence[Any]:
        if len(rows) > LANE_CAP:
            self.truncated = True
        return rows[:LANE_CAP]


async def _deadline_lanes(
    db: AsyncSession, user: User, today: date, lanes: _LaneCollector
) -> tuple[list[WorkItem], list[WorkItem]]:
    horizon = _day_start_utc(today + timedelta(days=DUE_SOON_DAYS + 1))
    work = [
        _order_work_item(o, today)
        for o in lanes.keep(await _orders_with_deadline(db, horizon))
    ]
    if has_permission(user, Permission.REPAIR_VIEW):
        work += [
            _repair_work_item(r, today)
            for r in lanes.keep(await _repairs_with_deadline(db, horizon))
        ]
    return split_deadline_lanes(work)


async def _customer_pending_lane(
    db: AsyncSession, user: User, lanes: _LaneCollector
) -> list[PendingItem]:
    """Everything waiting on the customer; longest waiting first.

    Each source is gated by the permission its own endpoint requires, so a
    VIEWER sees only ready-for-pickup rows.
    """
    pending: list[PendingItem] = []
    if has_permission(user, Permission.COST_CHANGE_VIEW):
        rows = lanes.keep(await _sent_cost_changes(db))
        pending += [_cost_change_item(c) for c in rows]
    if has_permission(user, Permission.CUSTOMER_UPDATE_VIEW):
        rows = lanes.keep(await _failed_customer_updates(db))
        pending += [_customer_update_item(u) for u in rows]
    if has_permission(user, Permission.REPAIR_VIEW):
        rows = lanes.keep(await _ready_repairs(db))
        pending += [_repair_ready_item(r) for r in rows]
    pending += [_order_ready_item(o) for o in lanes.keep(await _completed_orders(db))]
    if has_permission(user, Permission.QUOTE_VIEW):
        pending += [_quote_item(q) for q in lanes.keep(await _sent_quotes(db))]
    return sorted(pending, key=lambda p: (p.since, p.kind, p.id))


async def _timer_lane(
    db: AsyncSession, user: User, today: date, lanes: _LaneCollector
) -> list[TimerItem]:
    if not (
        has_permission(user, Permission.TIME_VIEW_OWN)
        or has_permission(user, Permission.TIME_VIEW_ALL)
    ):
        return []
    rows = lanes.keep(await _todays_timers(db, user, _day_start_utc(today)))
    return [_timer_item(t) for t in rows]


class DashboardService:
    """Builds the role-aware "Heute" summary."""

    @staticmethod
    async def get_today(
        db: AsyncSession, user: User, *, now_utc: Optional[datetime] = None
    ) -> DashboardToday:
        """Return every lane for ``user``.

        Lanes the caller lacks the permission for are returned empty rather
        than 403, so one screen serves every role. Financial fields are
        still present here; the router strips them per role.
        """
        now = now_utc or datetime.now(timezone.utc)
        today = berlin_today(now)
        lanes = _LaneCollector()

        overdue, due_soon = await _deadline_lanes(db, user, today, lanes)
        pending = await _customer_pending_lane(db, user, lanes)
        timers = await _timer_lane(db, user, today, lanes)

        logger.info(
            "Dashboard today built",
            extra={
                "user_id": user.id,
                "overdue": len(overdue),
                "due_soon": len(due_soon),
                "customer_pending": len(pending),
                "timers": len(timers),
                "truncated": lanes.truncated,
            },
        )
        return DashboardToday(
            today=today,
            generated_at=now.astimezone(timezone.utc).replace(tzinfo=None),
            can_view_financials=has_permission(user, Permission.FINANCIAL_VIEW),
            truncated=lanes.truncated,
            overdue=overdue,
            due_soon=due_soon,
            customer_pending=pending,
            timers=timers,
            counts=LaneCounts(
                overdue=len(overdue),
                due_soon=len(due_soon),
                customer_pending=len(pending),
                timers=len(timers),
            ),
        )
