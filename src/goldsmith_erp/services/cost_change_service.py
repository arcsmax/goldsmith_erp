# src/goldsmith_erp/services/cost_change_service.py
"""
CostChangeService — §649 BGB change-order lifecycle (V1.2 Task 5).

create() -> DRAFT CostChangeRequest, original_amount derived from
CostWatchService's quote reference (never client-supplied — spec: "a
customer-facing 'prior amount' can't be spoofed by the request body").
send() -> creates+sends a linked CustomerUpdate(kind=cost_change) via
CustomerUpdateService.send (shared delivery/failure-notification/SMTP-
unset machinery — no duplication of that state machine here).
record_response() -> evidence logging, not click-tracking (spec): only
valid from SENT, sets approved/declined + method/evidence/responded_at/
recorded_by.

Typed exceptions raised OUTSIDE transactional(db) — see
customer_update_service module docstring for the rationale
(transactional() logs str(exc) at ERROR; pre-flight raises keep that
logger ID-only).

Financial-data audit logging: structured "audit": True logging
(mirrors invoice_service._log_financial_access) rather than DB
CustomerAuditLog rows — see customer_update_service's module docstring
for why (the /orders/{id}/... GETs and every mutation here are outside
what AuditLoggingMiddleware's first-path-segment keying can see).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    CostChangeRequest,
    CostChangeStatus,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Order,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.customer_update import (
    CostChangeCreate,
    CostChangeRecordResponse,
    CustomerUpdateSendResult,
)
from goldsmith_erp.services.cost_watch_service import CostWatchService
from goldsmith_erp.services.customer_update_service import CustomerUpdateService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed exceptions — ID-only / fixed messages (see module docstring).
# ---------------------------------------------------------------------------


class CostChangeNotFoundError(ValueError):
    """No CostChangeRequest row with this id — maps to 404."""

    def __init__(self, cost_change_id: int) -> None:
        super().__init__(f"Kostenänderungsanfrage #{cost_change_id} nicht gefunden")


class NoQuoteAvailableError(ValueError):
    """
    The order has no referenceable Quote to derive original_amount from.

    Maps to 409 (not 404): the order itself exists, but the operation is
    impossible in the order's CURRENT state — matches the plan's explicit
    "'Kein Kostenvoranschlag' -> 409" mapping, distinguishing it from a
    plain not-found (404).
    """

    def __init__(self, order_id: int) -> None:
        super().__init__(f"Kein Kostenvoranschlag vorhanden für Auftrag #{order_id}")


class InvalidCostChangeStateError(ValueError):
    """The request's current status forbids the requested action — maps to 409."""

    def __init__(self, cost_change_id: int, current_status: str) -> None:
        super().__init__(
            f"Kostenänderungsanfrage #{cost_change_id} hat Status "
            f"'{current_status}' — Aktion nicht erlaubt"
        )


# ---------------------------------------------------------------------------
# Formatting + audit helpers
# ---------------------------------------------------------------------------


def _format_eur(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


def _compose_cost_change_body(cost_change: CostChangeRequest, order_ref: str) -> str:
    """
    Plain-text summary of the change-order notice — becomes
    ``CustomerUpdate.body`` for kind=cost_change rows. NOT used for the
    outgoing email (that renders via ``EmailService.send_cost_change``
    with the CostChangeRequest's own fields directly) — this is the
    history/PDF-fallback record, so ``PDFService.render_customer_update_pdf``
    (which only knows about ``update.subject``/``update.body``, not
    CostChangeRequest) still produces a complete, self-contained document.
    """
    # cast(): mypy sees Column[float]/Column[str] at class level for these
    # attributes (classic Column() style, no Mapped[] here) — at runtime,
    # on a loaded instance, they are plain float/str (cost_watch_service.py
    # precedent for this exact false-positive class).
    original_amount = cast(float, cost_change.original_amount)
    new_amount = cast(float, cost_change.new_amount)
    delta_percent = cast(float, cost_change.delta_percent)
    reason = cast(str, cost_change.reason)
    line_items = cast(Optional[List[Dict[str, Any]]], cost_change.line_items)

    lines = [
        f"Kostenaenderung zu {order_ref}",
        "",
        f"Ursprünglicher Betrag (netto): {_format_eur(original_amount)}",
        f"Neuer Betrag (netto): {_format_eur(new_amount)}",
        f"Abweichung: {delta_percent:.1f} %",
        "",
        f"Begründung: {reason}",
    ]
    if line_items:
        lines.append("")
        lines.append("Im Einzelnen:")
        for item in line_items:
            lines.append(
                f"- {item['label']}: {_format_eur(item['amount'])} ({item['kind']})"
            )
    return "\n".join(lines)


def _log_financial_access(
    action: str,
    cost_change_id: Optional[int],
    order_id: Optional[int],
    user_id: int,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    logger.info(
        "Financial data access",
        extra={
            "audit": True,
            "action": action,
            "entity": "cost_change",
            "entity_id": cost_change_id,
            "order_id": order_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            **(extra or {}),
        },
    )


class CostChangeService:
    """Static-method service — all methods accept AsyncSession as first arg."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        db: AsyncSession, order_id: int, data: CostChangeCreate, user_id: int
    ) -> CostChangeRequest:
        """
        Create a DRAFT CostChangeRequest. Any existing SENT request for
        this order is superseded in the SAME transaction (spec: a newer
        request replaces one still awaiting a customer response).

        Raises:
            ValueError: order does not exist (404).
            NoQuoteAvailableError: no referenceable Quote to compare
                against (409).
        """
        order = (
            await db.execute(select(Order).where(Order.id == order_id))
        ).scalar_one_or_none()
        if order is None:
            raise ValueError(f"Auftrag #{order_id} nicht gefunden")

        projected = await CostWatchService.get_projected_cost(db, order_id)
        if projected.quote_id is None or projected.quote_total is None:
            raise NoQuoteAvailableError(order_id)

        original_amount = projected.quote_total
        new_amount = data.new_amount
        delta_percent = (
            ((new_amount - original_amount) / original_amount) * 100.0
            if original_amount
            else 0.0
        )
        line_items = (
            [item.model_dump() for item in data.line_items] if data.line_items else None
        )

        async with transactional(db):
            existing_result = await db.execute(
                select(CostChangeRequest).where(
                    CostChangeRequest.order_id == order_id,
                    CostChangeRequest.status == CostChangeStatus.SENT,
                )
            )
            for existing in existing_result.scalars().all():
                existing.status = cast(Any, CostChangeStatus.SUPERSEDED)

            cost_change = CostChangeRequest(
                order_id=order_id,
                quote_id=projected.quote_id,
                original_amount=original_amount,
                new_amount=new_amount,
                delta_percent=round(delta_percent, 2),
                reason=data.reason,
                line_items=line_items,
                status=CostChangeStatus.DRAFT,
                created_by=user_id,
            )
            db.add(cost_change)

        await db.refresh(cost_change)
        _log_financial_access("created", cast(int, cost_change.id), order_id, user_id)
        return cost_change

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    @staticmethod
    async def send(
        db: AsyncSession, cost_change_id: int, user_id: int
    ) -> CustomerUpdateSendResult:
        """
        Create+send the linked CustomerUpdate(kind=cost_change) for this
        request. Only valid from DRAFT.

        Raises:
            CostChangeNotFoundError: no such request (404).
            InvalidCostChangeStateError: request not in DRAFT status (409).
        """
        cost_change = (
            await db.execute(
                select(CostChangeRequest).where(CostChangeRequest.id == cost_change_id)
            )
        ).scalar_one_or_none()
        if cost_change is None:
            raise CostChangeNotFoundError(cost_change_id)
        if cost_change.status != CostChangeStatus.DRAFT:
            raise InvalidCostChangeStateError(cost_change_id, cost_change.status.value)

        order = (
            await db.execute(select(Order).where(Order.id == cost_change.order_id))
        ).scalar_one_or_none()
        order_ref = (
            (cast(Optional[str], order.title) or f"Auftrag #{order.id}")
            if order is not None
            else f"Auftrag #{cost_change.order_id}"
        )
        subject = f"Kostenaenderung zu {order_ref}"
        body = _compose_cost_change_body(cost_change, order_ref)

        async with transactional(db):
            update = CustomerUpdate(
                order_id=cost_change.order_id,
                kind=CustomerUpdateKind.COST_CHANGE,
                subject=subject,
                body=body,
                cost_change_request_id=cost_change.id,
                status=CustomerUpdateStatus.DRAFT,
                sent_by=user_id,
            )
            db.add(update)
            cost_change.status = cast(Any, CostChangeStatus.SENT)

        await db.refresh(update)
        await db.refresh(cost_change)

        result = await CustomerUpdateService.send(db, cast(int, update.id), user_id)
        _log_financial_access(
            "sent",
            cost_change_id,
            cast(Optional[int], cost_change.order_id),
            user_id,
            extra={"delivered": result.delivered},
        )
        return result

    # ------------------------------------------------------------------
    # Record response (evidence logging)
    # ------------------------------------------------------------------

    @staticmethod
    async def record_response(
        db: AsyncSession,
        cost_change_id: int,
        data: CostChangeRecordResponse,
        user_id: int,
    ) -> CostChangeRequest:
        """
        Log the customer's approval/decline. Only valid from SENT.

        Raises:
            CostChangeNotFoundError: no such request (404).
            InvalidCostChangeStateError: request not in SENT status (409).
        """
        cost_change = (
            await db.execute(
                select(CostChangeRequest).where(CostChangeRequest.id == cost_change_id)
            )
        ).scalar_one_or_none()
        if cost_change is None:
            raise CostChangeNotFoundError(cost_change_id)
        if cost_change.status != CostChangeStatus.SENT:
            raise InvalidCostChangeStateError(cost_change_id, cost_change.status.value)

        new_status = (
            CostChangeStatus.APPROVED
            if data.status == "approved"
            else CostChangeStatus.DECLINED
        )

        async with transactional(db):
            cost_change.status = cast(Any, new_status)
            cost_change.response_method = cast(Any, data.response_method)
            cost_change.response_evidence = cast(Any, data.response_evidence)
            cost_change.responded_at = cast(Any, datetime.utcnow())
            cost_change.recorded_by = cast(Any, user_id)

        await db.refresh(cost_change)
        _log_financial_access(
            "response_recorded",
            cost_change_id,
            cast(Optional[int], cost_change.order_id),
            user_id,
            extra={"status": new_status.value},
        )
        return cost_change

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    @staticmethod
    async def list_for_order(
        db: AsyncSession, order_id: int, user_id: int
    ) -> List[CostChangeRequest]:
        """History of cost-change requests for an order, newest first."""
        result = await db.execute(
            select(CostChangeRequest)
            .where(CostChangeRequest.order_id == order_id)
            .order_by(CostChangeRequest.created_at.desc())
        )
        requests = list(result.scalars().all())
        _log_financial_access("list_accessed", None, order_id, user_id)
        return requests
