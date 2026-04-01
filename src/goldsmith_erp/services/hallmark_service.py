# src/goldsmith_erp/services/hallmark_service.py
"""
Business logic for the Punzierung (Hallmarking) module.

German law (Edelmetallgesetz, §1) requires pieces above threshold weights
(e.g. rings > 0.5 g gold) to carry a Feingehaltsstempel.  This service
manages the lifecycle of each hallmark application per order:

  PENDING -> SUBMITTED -> APPROVED -> STAMPED
  PENDING -> SUBMITTED -> REJECTED  (triggers rework)

All write operations are audit-logged because hallmark records are
legal documentation.
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    HallmarkStatus,
    HallmarkType,
    Order,
    OrderHallmark,
    User,
)

logger = logging.getLogger(__name__)

# Valid forward status transitions — backward moves are not permitted.
_VALID_TRANSITIONS: dict[HallmarkStatus, list[HallmarkStatus]] = {
    HallmarkStatus.PENDING: [HallmarkStatus.SUBMITTED],
    HallmarkStatus.SUBMITTED: [HallmarkStatus.APPROVED, HallmarkStatus.REJECTED],
    HallmarkStatus.APPROVED: [HallmarkStatus.STAMPED],
    HallmarkStatus.REJECTED: [HallmarkStatus.SUBMITTED],  # Re-submission after rework
    HallmarkStatus.STAMPED: [],
}


class HallmarkService:
    """CRUD + status-transition logic for OrderHallmark records."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_hallmarks_for_order(
        db: AsyncSession,
        order_id: int,
    ) -> List[OrderHallmark]:
        """Return all hallmark records for an order, newest first."""
        result = await db.execute(
            select(OrderHallmark)
            .where(OrderHallmark.order_id == order_id)
            .options(
                selectinload(OrderHallmark.creator),
                selectinload(OrderHallmark.order),
            )
            .order_by(OrderHallmark.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_hallmark(
        db: AsyncSession,
        hallmark_id: int,
    ) -> Optional[OrderHallmark]:
        """Return a single hallmark record by id, or None."""
        result = await db.execute(
            select(OrderHallmark)
            .where(OrderHallmark.id == hallmark_id)
            .options(
                selectinload(OrderHallmark.creator),
                selectinload(OrderHallmark.order),
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    async def create_hallmark(
        db: AsyncSession,
        order_id: int,
        hallmark_type: HallmarkType,
        created_by_id: int,
        assay_office: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> OrderHallmark:
        """
        Create a new hallmark record for an order.

        Verifies the order exists before creating the record.
        The new record always starts in PENDING status.
        """
        # Verify order exists
        order_result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = order_result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id} not found")

        hallmark = OrderHallmark(
            order_id=order_id,
            hallmark_type=hallmark_type,
            status=HallmarkStatus.PENDING,
            assay_office=assay_office,
            notes=notes,
            created_by=created_by_id,
        )
        db.add(hallmark)
        await db.commit()
        await db.refresh(hallmark)

        logger.info(
            "Hallmark record created",
            extra={
                "hallmark_id": hallmark.id,
                "order_id": order_id,
                "hallmark_type": hallmark_type.value,
                "created_by": created_by_id,
            },
        )
        return hallmark

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @staticmethod
    async def update_hallmark(
        db: AsyncSession,
        hallmark_id: int,
        assay_office: Optional[str] = None,
        certificate_number: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> OrderHallmark:
        """Update mutable fields on a hallmark record (no status change)."""
        hallmark = await HallmarkService.get_hallmark(db, hallmark_id)
        if hallmark is None:
            raise ValueError(f"Hallmark {hallmark_id} not found")

        if assay_office is not None:
            hallmark.assay_office = assay_office
        if certificate_number is not None:
            hallmark.certificate_number = certificate_number
        if notes is not None:
            hallmark.notes = notes

        await db.commit()
        await db.refresh(hallmark)
        return hallmark

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    @staticmethod
    async def transition_status(
        db: AsyncSession,
        hallmark_id: int,
        new_status: HallmarkStatus,
        certificate_number: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> OrderHallmark:
        """
        Advance the hallmark lifecycle to a new status.

        Validates the transition against _VALID_TRANSITIONS.
        Automatically sets the relevant timestamp column (submitted_at,
        approved_at, stamped_at) when transitioning.

        Raises ValueError on invalid transitions.
        """
        hallmark = await HallmarkService.get_hallmark(db, hallmark_id)
        if hallmark is None:
            raise ValueError(f"Hallmark {hallmark_id} not found")

        allowed = _VALID_TRANSITIONS.get(hallmark.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition hallmark from "
                f"{hallmark.status.value!r} to {new_status.value!r}. "
                f"Allowed next states: {[s.value for s in allowed]}"
            )

        now = datetime.utcnow()
        hallmark.status = new_status

        if new_status == HallmarkStatus.SUBMITTED:
            hallmark.submitted_at = now
        elif new_status == HallmarkStatus.APPROVED:
            hallmark.approved_at = now
            if certificate_number:
                hallmark.certificate_number = certificate_number
        elif new_status == HallmarkStatus.STAMPED:
            hallmark.stamped_at = now

        if notes is not None:
            hallmark.notes = notes

        await db.commit()
        await db.refresh(hallmark)

        logger.info(
            "Hallmark status updated",
            extra={
                "hallmark_id": hallmark_id,
                "new_status": new_status.value,
                "order_id": hallmark.order_id,
            },
        )
        return hallmark

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    @staticmethod
    async def delete_hallmark(
        db: AsyncSession,
        hallmark_id: int,
    ) -> None:
        """
        Hard-delete a hallmark record.

        Only PENDING records may be deleted — submitted or later records are
        legal documentation and must be preserved.
        """
        hallmark = await HallmarkService.get_hallmark(db, hallmark_id)
        if hallmark is None:
            raise ValueError(f"Hallmark {hallmark_id} not found")
        if hallmark.status != HallmarkStatus.PENDING:
            raise ValueError(
                f"Cannot delete hallmark in status {hallmark.status.value!r}. "
                "Only PENDING records may be deleted."
            )

        await db.delete(hallmark)
        await db.commit()
        logger.info(
            "Hallmark record deleted",
            extra={"hallmark_id": hallmark_id, "order_id": hallmark.order_id},
        )
