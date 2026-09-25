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

Sort (W3-sort)
    Every ``*_statement`` builder takes an optional ``sort`` string (see
    ``models/pagination.py``) and runs it through :func:`apply_sort` against
    that entity's ``*_SORT_FIELDS`` whitelist — the single source of truth
    routers also use to document the OpenAPI ``sort`` description. An
    unknown field is a 422 ``DomainValidationError``
    (``pagination.invalid_sort_field``), never a silent no-op. When ``sort``
    is empty, the statement's existing default order (newest first, id as
    tie-breaker) is unchanged. Encrypted PII columns (customer name/email)
    are never whitelisted since Fernet ciphertext has no stable order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Mapping, Optional, Sequence

from sqlalchemy import ColumnElement, Select, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import ORMOption

from goldsmith_erp.core.encryption import hmac_blind_index
from goldsmith_erp.core.errors import DomainValidationError
from goldsmith_erp.db.models import Customer as CustomerModel
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


def apply_sort(
    stmt: Select[Any],
    sort: Optional[str],
    allowed: Mapping[str, Any],
    tiebreaker: Any,
) -> Select[Any]:
    """Apply a whitelisted ``sort`` string, or leave ``stmt``'s order as-is.

    ``sort`` is ``field`` (ascending) or ``-field`` (descending),
    comma-separated. An unknown field raises ``DomainValidationError`` (422,
    ``pagination.invalid_sort_field``) — never silently ignored or matched
    by prefix, so a typo cannot masquerade as "no sort". ``tiebreaker`` (the
    entity's primary key) is always appended last so pages never overlap
    even when the chosen sort key has duplicate values.
    """
    if not sort:
        return stmt
    clauses: list[Any] = []
    for raw in sort.split(","):
        token = raw.strip()
        if not token:
            continue
        descending = token.startswith("-")
        field = token[1:] if descending else token
        column = allowed.get(field)
        if column is None:
            raise DomainValidationError(
                f"Unbekanntes Sortierfeld: '{field}'.",
                code="pagination.invalid_sort_field",
                extra={"field": field, "allowed": sorted(allowed)},
            )
        clauses.append(column.desc() if descending else column.asc())
    if not clauses:
        return stmt
    return stmt.order_by(None).order_by(*clauses, tiebreaker.asc())


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

# W3-sort: financial fields (price, costs, margins) are deliberately excluded
# — VIEWER never sees them (C5) and sorting must not become a side channel.
ORDER_SORT_FIELDS: dict[str, Any] = {
    "created_at": OrderModel.created_at,
    "deadline": OrderModel.deadline,
    "status": OrderModel.status,
    "title": OrderModel.title,
}


async def orders_statement(
    db: AsyncSession,
    *,
    status: Optional[OrderStatusEnum] = None,
    customer_id: Optional[int] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
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
    stmt = stmt.order_by(OrderModel.created_at.desc(), OrderModel.id.desc())
    return apply_sort(stmt, sort, ORDER_SORT_FIELDS, OrderModel.id)


# --------------------------------------------------------------------------- #
# Repairs
# --------------------------------------------------------------------------- #

REPAIR_LIST_OPTIONS: tuple[ORMOption, ...] = (selectinload(RepairJobModel.customer),)

# W3-sort: estimated_cost/actual_cost stay off the whitelist (financial data).
REPAIR_SORT_FIELDS: dict[str, Any] = {
    "created_at": RepairJobModel.created_at,
    "status": RepairJobModel.status,
    "estimated_completion_date": RepairJobModel.estimated_completion_date,
    "repair_number": RepairJobModel.repair_number,
}


async def repairs_statement(
    db: AsyncSession,
    *,
    status: Optional[RepairJobStatus] = None,
    customer_id: Optional[int] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
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
    stmt = stmt.order_by(RepairJobModel.created_at.desc(), RepairJobModel.id.desc())
    return apply_sort(stmt, sort, REPAIR_SORT_FIELDS, RepairJobModel.id)


# --------------------------------------------------------------------------- #
# Quotes
# --------------------------------------------------------------------------- #

QUOTE_LIST_OPTIONS: tuple[ORMOption, ...] = (selectinload(QuoteModel.line_items),)

# W3-sort: subtotal/tax_amount/total stay off the whitelist (financial data).
QUOTE_SORT_FIELDS: dict[str, Any] = {
    "created_at": QuoteModel.created_at,
    "status": QuoteModel.status,
    "valid_until": QuoteModel.valid_until,
    "quote_number": QuoteModel.quote_number,
}


async def quotes_statement(
    db: AsyncSession,
    *,
    status: Optional[QuoteStatus] = None,
    customer_id: Optional[int] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
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
    stmt = stmt.order_by(QuoteModel.created_at.desc(), QuoteModel.id.desc())
    return apply_sort(stmt, sort, QUOTE_SORT_FIELDS, QuoteModel.id)


# --------------------------------------------------------------------------- #
# Materials, time entries, notifications
# --------------------------------------------------------------------------- #


MATERIAL_SORT_FIELDS: dict[str, Any] = {
    "name": MaterialModel.name,
    "stock": MaterialModel.stock,
    "supplier": MaterialModel.supplier,
}


def materials_statement(
    *, q: Optional[str] = None, sort: Optional[str] = None
) -> Select[Any]:
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
    stmt = stmt.order_by(MaterialModel.name.asc(), MaterialModel.id.asc())
    return apply_sort(stmt, sort, MATERIAL_SORT_FIELDS, MaterialModel.id)


TIME_ENTRY_LIST_OPTIONS: tuple[ORMOption, ...] = (
    selectinload(TimeEntryModel.activity),
    selectinload(TimeEntryModel.order),
    selectinload(TimeEntryModel.user),
    selectinload(TimeEntryModel.interruptions),
    selectinload(TimeEntryModel.photos),
)

TIME_ENTRY_SORT_FIELDS: dict[str, Any] = {
    "start_time": TimeEntryModel.start_time,
    "end_time": TimeEntryModel.end_time,
}


def time_entries_statement(
    *,
    user_id: Optional[int] = None,
    order_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort: Optional[str] = None,
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
    stmt = stmt.order_by(TimeEntryModel.start_time.desc(), TimeEntryModel.id.desc())
    return apply_sort(stmt, sort, TIME_ENTRY_SORT_FIELDS, TimeEntryModel.id)


NOTIFICATION_SORT_FIELDS: dict[str, Any] = {
    "created_at": NotificationModel.created_at,
    "severity": NotificationModel.severity,
    "notification_type": NotificationModel.notification_type,
    "is_read": NotificationModel.is_read,
}


def notifications_statement(
    *, user_id: int, unread_only: bool = False, sort: Optional[str] = None
) -> Select[Any]:
    """The user's own notifications, newest first."""
    stmt = select(NotificationModel).where(NotificationModel.user_id == user_id)
    if unread_only:
        stmt = stmt.where(NotificationModel.is_read.is_(False))
    stmt = stmt.order_by(
        NotificationModel.created_at.desc(), NotificationModel.id.desc()
    )
    return apply_sort(stmt, sort, NOTIFICATION_SORT_FIELDS, NotificationModel.id)


# --------------------------------------------------------------------------- #
# Customers (W3, paged /customers/)
# --------------------------------------------------------------------------- #

CUSTOMER_SORT_FIELDS: dict[str, Any] = {
    "created_at": CustomerModel.created_at,
    "customer_type": CustomerModel.customer_type,
    "is_active": CustomerModel.is_active,
}


def customers_statement(
    *,
    customer_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    tag: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,
) -> Select[Any]:
    """Customers, newest first. ``q``: full email via the ``email_hash`` blind-index only.

    Name/company/email are Fernet-encrypted (non-deterministic ciphertext),
    so — unlike orders/repairs/quotes — there is no SQL-side substring
    search here: only an exact blind-index match on a full email address,
    same fast path as ``CustomerService.get_customers``. Fragment/name
    search stays on the legacy (unpaged) path, which still calls
    ``CustomerService.get_customers``'s Python-side decrypt-and-match.
    For the same reason ``sort`` never whitelists name/email columns
    (see :data:`CUSTOMER_SORT_FIELDS`).
    """
    stmt = select(CustomerModel)
    if customer_type:
        stmt = stmt.where(CustomerModel.customer_type == customer_type)
    if is_active is not None:
        stmt = stmt.where(CustomerModel.is_active.is_(is_active))
    if tag:
        stmt = stmt.where(CustomerModel.tags.contains([tag]))
    if q:
        stmt = stmt.where(CustomerModel.email_hash == hmac_blind_index(q))
    stmt = stmt.order_by(CustomerModel.created_at.desc(), CustomerModel.id.desc())
    return apply_sort(stmt, sort, CUSTOMER_SORT_FIELDS, CustomerModel.id)
