# src/goldsmith_erp/services/customer_activity_service.py
"""
Customer 360 (W2-12, DOM-38): one chronological list across the customer's
orders, repairs, quotes, invoices and customer updates.

Paging works on the merged list, server-side, in two steps:

1. One ``UNION ALL`` over lightweight ``(kind, id, occurred_at)`` rows,
   filtered by ``customer_id``, sorted newest first and cut with
   LIMIT/OFFSET. The same union gives the total count.
2. The page's rows are then loaded per kind by primary key (at most one
   query per kind, never per row) and mapped to ``CustomerActivityItem``.

Only ids and timestamps travel through the union, so encrypted or
differently typed columns never have to line up across tables.

Visibility: a kind is included only when the caller holds its view
permission (VIEWER: orders and repairs only). Amounts are stripped at the
router for callers without FINANCIAL_VIEW.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Final, FrozenSet, List, Sequence, Tuple

from sqlalchemy import Select, String, func, literal_column, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.permissions import Permission, has_permission
from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    Invoice,
    Order,
    Quote,
    RepairJob,
    User,
)
from goldsmith_erp.models.customer import CustomerActivityItem

logger = logging.getLogger(__name__)

KIND_ORDER: Final = "order"
KIND_REPAIR: Final = "repair"
KIND_QUOTE: Final = "quote"
KIND_INVOICE: Final = "invoice"
KIND_UPDATE: Final = "customer_update"

KIND_PERMISSIONS: Dict[str, Permission] = {
    KIND_ORDER: Permission.ORDER_VIEW,
    KIND_REPAIR: Permission.REPAIR_VIEW,
    KIND_QUOTE: Permission.QUOTE_VIEW,
    KIND_INVOICE: Permission.INVOICE_VIEW,
    KIND_UPDATE: Permission.CUSTOMER_UPDATE_VIEW,
}


@dataclass(frozen=True)
class ActivityPage:
    items: List[CustomerActivityItem]
    total: int


def visible_kinds(user: User) -> FrozenSet[str]:
    """The activity kinds this caller may see."""
    return frozenset(
        kind for kind, perm in KIND_PERMISSIONS.items() if has_permission(user, perm)
    )


# ---------------------------------------------------------------------------
# Step 1: the (kind, id, occurred_at) union
# ---------------------------------------------------------------------------


def _key_select(kind: str, id_col: Any, at_col: Any) -> Select[Any]:
    # A typed SQL constant, not a bind parameter: PostgreSQL cannot infer
    # the type of an untyped parameter inside a UNION branch. ``kind`` is
    # always one of the module's own KIND_* constants, never user input.
    if kind not in KIND_PERMISSIONS:
        raise ValueError(f"unknown activity kind: {kind}")
    return select(
        literal_column(f"'{kind}'", String).label("kind"),
        id_col.label("id"),
        at_col.label("occurred_at"),
    )


def _update_keys(customer_id: int) -> List[Select[Any]]:
    """Customer updates hang off an order or a repair, never the customer."""
    occurred = func.coalesce(CustomerUpdate.sent_at, CustomerUpdate.created_at)
    via_order = (
        _key_select(KIND_UPDATE, CustomerUpdate.id, occurred)
        .join(Order, CustomerUpdate.order_id == Order.id)
        .where(Order.customer_id == customer_id, Order.is_deleted.is_(False))
    )
    via_repair = (
        _key_select(KIND_UPDATE, CustomerUpdate.id, occurred)
        .join(RepairJob, CustomerUpdate.repair_job_id == RepairJob.id)
        .where(RepairJob.customer_id == customer_id, RepairJob.is_deleted.is_(False))
    )
    return [via_order, via_repair]


def _key_selects(customer_id: int, kinds: FrozenSet[str]) -> List[Select[Any]]:
    builders: Dict[str, Callable[[], List[Select[Any]]]] = {
        KIND_ORDER: lambda: [
            _key_select(KIND_ORDER, Order.id, Order.created_at).where(
                Order.customer_id == customer_id, Order.is_deleted.is_(False)
            )
        ],
        KIND_REPAIR: lambda: [
            _key_select(KIND_REPAIR, RepairJob.id, RepairJob.created_at).where(
                RepairJob.customer_id == customer_id,
                RepairJob.is_deleted.is_(False),
            )
        ],
        KIND_QUOTE: lambda: [
            _key_select(KIND_QUOTE, Quote.id, Quote.created_at).where(
                Quote.customer_id == customer_id
            )
        ],
        KIND_INVOICE: lambda: [
            _key_select(KIND_INVOICE, Invoice.id, Invoice.created_at).where(
                Invoice.customer_id == customer_id
            )
        ],
        KIND_UPDATE: lambda: _update_keys(customer_id),
    }
    selects: List[Select[Any]] = []
    for kind in KIND_PERMISSIONS:  # stable order
        if kind in kinds:
            selects.extend(builders[kind]())
    return selects


async def _page_keys(
    db: AsyncSession,
    selects: Sequence[Select[Any]],
    limit: int,
    offset: int,
) -> Tuple[List[Tuple[str, int]], int]:
    merged = union_all(*selects).subquery("activity")
    total = int(
        (await db.execute(select(func.count()).select_from(merged))).scalar_one()
    )
    page = await db.execute(
        select(merged.c.kind, merged.c.id)
        .order_by(merged.c.occurred_at.desc(), merged.c.kind.desc(), merged.c.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [(str(kind), int(row_id)) for kind, row_id in page.all()], total


# ---------------------------------------------------------------------------
# Step 2: hydrate the page's rows (one query per kind)
# ---------------------------------------------------------------------------


def _status(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _order_item(row: Any) -> CustomerActivityItem:
    return CustomerActivityItem(
        kind=KIND_ORDER,
        id=row.id,
        occurred_at=row.created_at,
        status=_status(row.status),
        title=row.title or f"Auftrag #{row.id}",
        reference=f"#{row.id}",
        amount=row.price,
        order_id=row.id,
    )


def _repair_item(row: Any) -> CustomerActivityItem:
    first_line = (row.item_description or "").split("\n", 1)[0]
    return CustomerActivityItem(
        kind=KIND_REPAIR,
        id=row.id,
        occurred_at=row.created_at,
        status=_status(row.status),
        title=first_line or row.repair_number,
        reference=row.repair_number,
        amount=row.actual_cost if row.actual_cost is not None else row.estimated_cost,
        repair_job_id=row.id,
    )


def _quote_item(row: Any) -> CustomerActivityItem:
    return CustomerActivityItem(
        kind=KIND_QUOTE,
        id=row.id,
        occurred_at=row.created_at,
        status=_status(row.status),
        title=f"Kostenvoranschlag {row.quote_number}",
        reference=row.quote_number,
        amount=row.total,
        order_id=row.order_id,
    )


def _invoice_item(row: Any) -> CustomerActivityItem:
    return CustomerActivityItem(
        kind=KIND_INVOICE,
        id=row.id,
        occurred_at=row.created_at,
        status=_status(row.status),
        title=f"Rechnung {row.invoice_number}",
        reference=row.invoice_number,
        amount=row.total,
        order_id=row.order_id,
    )


def _update_item(row: Any) -> CustomerActivityItem:
    return CustomerActivityItem(
        kind=KIND_UPDATE,
        id=row.id,
        occurred_at=row.sent_at or row.created_at,
        status=_status(row.status),
        title=row.subject,
        order_id=row.order_id,
        repair_job_id=row.repair_job_id,
    )


_HYDRATORS: Dict[str, Tuple[Any, Callable[[Any], CustomerActivityItem]]] = {
    KIND_ORDER: (Order, _order_item),
    KIND_REPAIR: (RepairJob, _repair_item),
    KIND_QUOTE: (Quote, _quote_item),
    KIND_INVOICE: (Invoice, _invoice_item),
    KIND_UPDATE: (CustomerUpdate, _update_item),
}


async def _hydrate(
    db: AsyncSession, keys: Sequence[Tuple[str, int]]
) -> List[CustomerActivityItem]:
    by_kind: Dict[str, List[int]] = {}
    for kind, row_id in keys:
        by_kind.setdefault(kind, []).append(row_id)
    loaded: Dict[Tuple[str, int], CustomerActivityItem] = {}
    for kind, ids in by_kind.items():
        model, to_item = _HYDRATORS[kind]
        rows = (await db.execute(select(model).where(model.id.in_(ids)))).scalars()
        for row in rows:
            loaded[(kind, row.id)] = to_item(row)
    return [loaded[key] for key in keys if key in loaded]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class CustomerActivityService:
    """Static-method service; all methods take the AsyncSession first."""

    @staticmethod
    async def customer_exists(db: AsyncSession, customer_id: int) -> bool:
        result = await db.execute(
            select(Customer.id).where(
                Customer.id == customer_id, Customer.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def list_activity(
        db: AsyncSession,
        customer_id: int,
        kinds: FrozenSet[str],
        limit: int,
        offset: int,
    ) -> ActivityPage:
        """One page of the customer's merged history, newest first."""
        selects = _key_selects(customer_id, kinds)
        if not selects:
            return ActivityPage(items=[], total=0)
        keys, total = await _page_keys(db, selects, limit, offset)
        items = await _hydrate(db, keys)
        if len(items) != len(keys):
            # A row vanished between the two steps (concurrent delete).
            logger.warning(
                "Customer activity: rows disappeared while paging",
                extra={
                    "customer_id": customer_id,
                    "expected": len(keys),
                    "loaded": len(items),
                },
            )
        return ActivityPage(items=items, total=total)
