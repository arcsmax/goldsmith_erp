"""Order gemstones: CRUD and role projection (W2-06, DOM-04).

All reads and writes are audit-logged. Reads and creates live under
``/orders/{id}/gemstones``, which ``AuditLoggingMiddleware`` cannot see (the
documented ``/orders/{id}/...`` blind spot), so this service writes the
``CustomerAuditLog`` row itself via ``write_financial_audit_row``. Updates
and deletes go through ``/gemstones/{id}`` and are additionally covered by
the middleware's ``gemstones`` family.

Log lines carry ids only: stone descriptions are design IP and costs are
financial data (CLAUDE.md).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, List, Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.errors import DomainValidationError, NotFoundError
from goldsmith_erp.db.models import Gemstone
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models._common import DecimalLike, dec, money
from goldsmith_erp.models.gemstone import GemstoneCreate, GemstoneUpdate
from goldsmith_erp.services.customer_update_service import write_financial_audit_row

logger = logging.getLogger(__name__)

ENTITY = "gemstone"
_CUSTOMER_STONE_COST_ERROR = (
    "Ein Kundenstein hat keinen Einkaufspreis. Bitte den Preis auf 0 setzen "
    "oder „Kundenstein“ abwählen."
)


def _total_cost(cost: Optional[DecimalLike], quantity: Optional[int]) -> Decimal:
    return money(dec(cost) * int(quantity or 1))


class GemstoneService:
    """Static-method service; every method takes the AsyncSession first."""

    @staticmethod
    async def _require_order(db: AsyncSession, order_id: int) -> None:
        result = await db.execute(
            select(OrderModel.id).where(
                OrderModel.id == order_id, OrderModel.is_deleted.is_not(True)
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError(
                "Auftrag nicht gefunden.",
                code="order.not_found",
                extra={"order_id": order_id},
            )

    @staticmethod
    async def _get(db: AsyncSession, gemstone_id: int) -> Gemstone:
        result = await db.execute(select(Gemstone).where(Gemstone.id == gemstone_id))
        stone = result.scalar_one_or_none()
        if stone is None:
            raise NotFoundError(
                "Stein nicht gefunden.",
                code="gemstone.not_found",
                extra={"gemstone_id": gemstone_id},
            )
        return stone

    @staticmethod
    async def _audit(
        db: AsyncSession,
        *,
        action: str,
        stone_id: Optional[int],
        order_id: int,
        user: UserModel,
        endpoint: str,
        method: str,
    ) -> None:
        await write_financial_audit_row(
            db,
            action=action,
            entity=ENTITY,
            entity_id=stone_id,
            order_id=order_id,
            user_id=cast(int, user.id),
            endpoint=endpoint,
            http_method=method,
        )

    @staticmethod
    async def list_for_order(
        db: AsyncSession, order_id: int, user: UserModel
    ) -> List[Gemstone]:
        """All stones of an order, oldest first. 404 if the order is missing."""
        await GemstoneService._require_order(db, order_id)
        result = await db.execute(
            select(Gemstone).where(Gemstone.order_id == order_id).order_by(Gemstone.id)
        )
        stones = list(result.scalars().all())
        await GemstoneService._audit(
            db,
            action="list_accessed_financial",
            stone_id=None,
            order_id=order_id,
            user=user,
            endpoint=f"/api/v1/orders/{order_id}/gemstones",
            method="GET",
        )
        return stones

    @staticmethod
    async def create(
        db: AsyncSession, order_id: int, data: GemstoneCreate, user: UserModel
    ) -> Gemstone:
        """Add a stone to an order."""
        await GemstoneService._require_order(db, order_id)
        values = data.model_dump()
        async with transactional(db):
            stone = Gemstone(
                order_id=order_id,
                **values,
                total_cost=_total_cost(values["cost"], values["quantity"]),
            )
            db.add(stone)
        await db.refresh(stone)
        logger.info(
            "Gemstone created",
            extra={"gemstone_id": stone.id, "order_id": order_id, "user_id": user.id},
        )
        await GemstoneService._audit(
            db,
            action="created",
            stone_id=cast(int, stone.id),
            order_id=order_id,
            user=user,
            endpoint=f"/api/v1/orders/{order_id}/gemstones",
            method="POST",
        )
        return stone

    @staticmethod
    async def update(
        db: AsyncSession, gemstone_id: int, data: GemstoneUpdate, user: UserModel
    ) -> Gemstone:
        """Change the sent fields of a stone; keeps total_cost in step."""
        stone = await GemstoneService._get(db, gemstone_id)
        changes = data.model_dump(exclude_unset=True)
        for field in ("type", "quantity", "cost", "is_customer_stone"):
            if field in changes and changes[field] is None:
                raise DomainValidationError(
                    f"Feld „{field}“ darf nicht leer sein.",
                    code="gemstone.required_field",
                )
        is_customer = changes.get("is_customer_stone", stone.is_customer_stone)
        cost = changes.get("cost", stone.cost)
        if is_customer and (cost or 0) > 0:
            raise DomainValidationError(
                _CUSTOMER_STONE_COST_ERROR, code="gemstone.customer_stone_cost"
            )
        async with transactional(db):
            for field, value in changes.items():
                setattr(stone, field, value)
            row = cast(Any, stone)  # legacy Column() typing
            row.total_cost = _total_cost(row.cost, row.quantity)
        await db.refresh(stone)
        logger.info(
            "Gemstone updated",
            extra={
                "gemstone_id": gemstone_id,
                "order_id": stone.order_id,
                "user_id": user.id,
                "changed_fields": sorted(changes),
            },
        )
        return stone

    @staticmethod
    async def delete(db: AsyncSession, gemstone_id: int, user: UserModel) -> int:
        """Remove a stone. Returns the order id it belonged to."""
        stone = await GemstoneService._get(db, gemstone_id)
        order_id = cast(int, stone.order_id)
        async with transactional(db):
            await db.delete(stone)
        logger.info(
            "Gemstone deleted",
            extra={
                "gemstone_id": gemstone_id,
                "order_id": order_id,
                "user_id": user.id,
            },
        )
        return order_id
