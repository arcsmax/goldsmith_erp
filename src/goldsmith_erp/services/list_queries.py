"""Server-side filtered, counted and paged list queries (ARCH-08, W3-08).

Backs the paged mode of the list endpoints (orders, repairs, quotes,
materials, time entries, notifications). Each ``*_statement`` builds the
filtered, ordered ``SELECT`` without loader options; :func:`fetch_page` adds
the eager loads, runs one ``COUNT(*)`` over the same filter and returns one
page. Legacy (unpaged) requests keep using the existing service methods.

Search (``q``) matches plain columns with an escaped ``ILIKE`` and customers
through :func:`customer_ids_matching`. Customer names are Fernet-encrypted
(non-deterministic), so the only SQL-side lookup is the ``email_hash`` blind
index; names go through ``CustomerService.search_customers`` (decrypt and
match, the existing autocomplete strategy), capped at
:data:`MAX_CUSTOMER_MATCHES`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Sequence

from sqlalchemy import ColumnElement, Select, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import ORMOption

from goldsmith_erp.db.models import Material as MaterialModel
from goldsmith_erp.db.models import Notification as NotificationModel
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.models import OrderStatusEnum
from goldsmith_erp.db.models import Quote as QuoteModel
from goldsmith_erp.db.models import QuoteStatus
from goldsmith_erp.db.models import RepairJob as RepairJobModel
from goldsmith_erp.db.models import RepairJobStatus
from goldsmith_erp.db.models import TimeEntry as TimeEntryModel
from goldsmith_erp.models.pagination import PageParams
from goldsmith_erp.services.customer_service import CustomerService

MAX_CUSTOMER_MATCHES = 200


@dataclass(frozen=True)
class PageResult:
    """One page of ORM rows plus the total over all pages."""

    items: List[Any]
    total: int


def _like(q: str) -> str:
    """``%q%`` with LIKE wildcards in the user's text escaped."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def customer_ids_matching(db: AsyncSession, q: str) -> List[int]:
    """Ids of active customers whose name, company or email matches ``q``."""
    customers = await CustomerService.search_customers(
        db, q, limit=MAX_CUSTOMER_MATCHES
    )
    return [int(c.id) for c in customers]


def _customer_clause(column: Any, ids: Sequence[int]) -> ColumnElement[bool]:
    return column.in_(ids) if ids else false()


async def fetch_page(
    db: AsyncSession,
    stmt: Select[Any],
    params: PageParams,
    options: Sequence[ORMOption] = (),
) -> PageResult:
    """Count all rows of ``stmt`` and load one page with ``options``."""
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int((await db.execute(count_stmt)).scalar_one())
    page_stmt = stmt.options(*options).offset(params.offset).limit(params.limit)
    rows = (await db.execute(page_stmt)).scalars().all()
    return PageResult(items=list(rows), total=total)


# --------------------------------------------------------------------------- #
# Orders
# --------------------------------------------------------------------------- #

ORDER_LIST_OPTIONS: tuple[ORMOption, ...] = (
    selectinload(OrderModel.materials),
    selectinload(OrderModel.customer),
    selectinload(OrderModel.gemstones),
)


async def orders_statement(
    db: AsyncSession,
    *,
    status: Optional[OrderStatusEnum] = None,
    customer_id: Optional[int] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    q: Optional[str] = None,
) -> Select[Any]:
    """Non-deleted orders, newest first. ``q``: id, title or customer.

    ``description`` is design IP and deliberately not searchable.
    """
    stmt = select(OrderModel).where(OrderModel.is_deleted.is_(False))
    if status is not None:
        stmt = stmt.where(OrderModel.status == status)
    if customer_id is not None:
        stmt = stmt.where(OrderModel.customer_id == customer_id)
    if created_from is not None:
        stmt = stmt.where(OrderModel.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(OrderModel.created_at <= created_to)
    if q:
        ids = await customer_ids_matching(db, q)
        clauses: list[ColumnElement[bool]] = [
            OrderModel.title.ilike(_like(q), escape="\\"),
            _customer_clause(OrderModel.customer_id, ids),
        ]
        if q.strip().isdigit():
            clauses.append(OrderModel.id == int(q.strip()))
        stmt = stmt.where(or_(*clauses))
    return stmt.order_by(OrderModel.created_at.desc(), OrderModel.id.desc())


# --------------------------------------------------------------------------- #
# Repairs
# --------------------------------------------------------------------------- #

REPAIR_LIST_OPTIONS: tuple[ORMOption, ...] = (selectinload(RepairJobModel.customer),)


async def repairs_statement(
    db: AsyncSession,
    *,
    status: Optional[RepairJobStatus] = None,
    customer_id: Optional[int] = None,
    q: Optional[str] = None,
) -> Select[Any]:
    """Non-deleted repairs, newest first. ``q``: number, bag, item or customer."""
    stmt = select(RepairJobModel).where(RepairJobModel.is_deleted.is_(False))
    if status is not None:
        stmt = stmt.where(RepairJobModel.status == status)
    if customer_id is not None:
        stmt = stmt.where(RepairJobModel.customer_id == customer_id)
    if q:
        like = _like(q)
        ids = await customer_ids_matching(db, q)
        stmt = stmt.where(
            or_(
                RepairJobModel.repair_number.ilike(like, escape="\\"),
                RepairJobModel.bag_number.ilike(like, escape="\\"),
                RepairJobModel.item_description.ilike(like, escape="\\"),
                _customer_clause(RepairJobModel.customer_id, ids),
            )
        )
    return stmt.order_by(RepairJobModel.created_at.desc(), RepairJobModel.id.desc())


# --------------------------------------------------------------------------- #
# Quotes
# --------------------------------------------------------------------------- #

QUOTE_LIST_OPTIONS: tuple[ORMOption, ...] = (selectinload(QuoteModel.line_items),)


async def quotes_statement(
    db: AsyncSession,
    *,
    status: Optional[QuoteStatus] = None,
    customer_id: Optional[int] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    q: Optional[str] = None,
) -> Select[Any]:
    """Quotes, newest first. ``q``: quote number or customer."""
    stmt = select(QuoteModel)
    if status is not None:
        stmt = stmt.where(QuoteModel.status == status)
    if customer_id is not None:
        stmt = stmt.where(QuoteModel.customer_id == customer_id)
    if created_from is not None:
        stmt = stmt.where(QuoteModel.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(QuoteModel.created_at <= created_to)
    if q:
        ids = await customer_ids_matching(db, q)
        stmt = stmt.where(
            or_(
                QuoteModel.quote_number.ilike(_like(q), escape="\\"),
                _customer_clause(QuoteModel.customer_id, ids),
            )
        )
    return stmt.order_by(QuoteModel.created_at.desc(), QuoteModel.id.desc())


# --------------------------------------------------------------------------- #
# Materials, time entries, notifications
# --------------------------------------------------------------------------- #


def materials_statement(*, q: Optional[str] = None) -> Select[Any]:
    """Materials by name. ``q``: name or supplier."""
    stmt = select(MaterialModel)
    if q:
        like = _like(q)
        stmt = stmt.where(
            or_(
                MaterialModel.name.ilike(like, escape="\\"),
                MaterialModel.supplier.ilike(like, escape="\\"),
            )
        )
    return stmt.order_by(MaterialModel.name.asc(), MaterialModel.id.asc())


TIME_ENTRY_LIST_OPTIONS: tuple[ORMOption, ...] = (
    selectinload(TimeEntryModel.activity),
    selectinload(TimeEntryModel.order),
    selectinload(TimeEntryModel.user),
    selectinload(TimeEntryModel.interruptions),
    selectinload(TimeEntryModel.photos),
)


def time_entries_statement(
    *,
    user_id: Optional[int] = None,
    order_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Select[Any]:
    """Time entries, latest start first, filtered by user/order/date range."""
    stmt = select(TimeEntryModel)
    if user_id is not None:
        stmt = stmt.where(TimeEntryModel.user_id == user_id)
    if order_id is not None:
        stmt = stmt.where(TimeEntryModel.order_id == order_id)
    if start_date is not None:
        stmt = stmt.where(TimeEntryModel.start_time >= start_date)
    if end_date is not None:
        stmt = stmt.where(TimeEntryModel.start_time <= end_date)
    return stmt.order_by(TimeEntryModel.start_time.desc(), TimeEntryModel.id.desc())


def notifications_statement(*, user_id: int, unread_only: bool = False) -> Select[Any]:
    """The user's own notifications, newest first."""
    stmt = select(NotificationModel).where(NotificationModel.user_id == user_id)
    if unread_only:
        stmt = stmt.where(NotificationModel.is_read.is_(False))
    return stmt.order_by(
        NotificationModel.created_at.desc(), NotificationModel.id.desc()
    )
