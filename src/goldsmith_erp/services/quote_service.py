# src/goldsmith_erp/services/quote_service.py
"""
Quote service (Kostenvoranschlag-Service).

Handles:
- Sequential quote number generation (KV-YYYY-NNNN)
- Auto-generation of line items from order cost data (mirrors invoice_service)
- Total calculation (subtotal, 19% MwSt, Gesamtbetrag)
- Status transitions: DRAFT -> SENT -> APPROVED / REJECTED -> CONVERTED
- Conversion of approved quote into a confirmed order

Financial data access MUST be audit-logged per CLAUDE.md.
All service methods are async and accept AsyncSession as first parameter.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, cast

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import Customer as CustomerModel
from goldsmith_erp.db.models import InvoiceLineType, MetalType
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.models import OrderStatusEnum
from goldsmith_erp.db.models import Quote as QuoteModel
from goldsmith_erp.db.models import QuoteLineItem as QuoteLineItemModel
from goldsmith_erp.db.models import QuoteLineType, QuoteStatus
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.quote import (
    ApproveQuoteRequest,
    QuoteCreate,
    QuoteLineItemCreate,
    QuoteUpdate,
)

logger = logging.getLogger(__name__)


def _log_quote_access(
    action: str,
    quote_id: Optional[int],
    user_id: int,
    user_role: str,
    extra: Optional[dict] = None,
) -> None:
    """
    Structured audit log for quote financial data access.

    Follows the same pattern as invoice_service._log_financial_access.
    user_email intentionally excluded (CLAUDE.md PII rule).
    """
    logger.info(
        "Quote financial data access",
        extra={
            "audit": True,
            "action": action,
            "entity": "quote",
            "quote_id": quote_id,
            "user_id": user_id,
            "user_role": user_role,
            "timestamp": datetime.utcnow().isoformat(),
            **(extra or {}),
        },
    )


def _user_role_str(user: UserModel) -> str:
    """Extract role string safely from a User ORM object."""
    return user.role.value if hasattr(user.role, "value") else str(user.role)


# -----------------------------------------------------------------------------
# Typed exceptions — line-item editing (Task 1, editable-quotes plan).
#
# Follows the ``ConsultationNotFoundError`` / ``CostChangeNotFoundError``
# precedent (consultation_service.py / cost_change_service.py): typed
# subclasses of ``ValueError`` so the router dispatches on type instead of
# string-matching, and messages carry IDs only — never free-text business
# data — so they are safe to surface verbatim in both the HTTP response and
# the log line.
# -----------------------------------------------------------------------------


class QuoteNotFoundError(ValueError):
    """No Quote row with this id — maps to 404."""

    def __init__(self, quote_id: int) -> None:
        super().__init__(f"Kostenvoranschlag {quote_id} nicht gefunden")


class QuoteLineItemNotFoundError(QuoteNotFoundError):
    """No QuoteLineItem row with this id on the given quote — maps to 404.

    Subclasses ``QuoteNotFoundError`` (mirrors the
    ``SentCostChangeConflictError(InvalidCostChangeStateError)`` precedent in
    cost_change_service.py) so a single ``isinstance(exc, QuoteNotFoundError)``
    check in the router catches both cases without a second branch.
    """

    def __init__(self, quote_id: int, item_id: int) -> None:
        ValueError.__init__(
            self,
            f"Position {item_id} in Kostenvoranschlag {quote_id} nicht gefunden",
        )


class QuoteNotEditableError(ValueError):
    """A forbidden mutation on a non-DRAFT (or otherwise immutable) quote.
    Maps to 409.

    Generic German message with no quote_id — a SENT/APPROVED/CONVERTED
    Kostenvoranschlag is legally relevant and must stay immutable (CLAUDE.md
    / plan Global Constraints). The default message covers line-item and
    tax_rate edits; a caller may pass a more specific reason (e.g. the
    status-change-via-PUT guard) — every message here is a fixed template
    with no user free-text, so it is safe to surface verbatim.
    """

    def __init__(self, message: str = "Nur Entwürfe können bearbeitet werden") -> None:
        super().__init__(message)


class QuoteService:
    # -------------------------------------------------------------------------
    # Quote number generation
    # -------------------------------------------------------------------------

    @staticmethod
    async def generate_quote_number(db: AsyncSession) -> str:
        """
        Generate the next sequential quote number for the current year.

        Format: KV-YYYY-NNNN (e.g. KV-2026-0001)

        Uses SELECT MAX inside the current transaction — safe for the ERP's
        low-concurrency usage. A DB sequence would be preferable at scale.
        """
        year = datetime.utcnow().year
        prefix = f"KV-{year}-"

        result = await db.execute(
            select(func.max(QuoteModel.quote_number)).where(
                QuoteModel.quote_number.like(f"{prefix}%")
            )
        )
        last_number: Optional[str] = result.scalar_one_or_none()

        if last_number:
            try:
                seq = int(last_number.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1

        return f"{prefix}{seq:04d}"

    # -------------------------------------------------------------------------
    # Total calculation
    # -------------------------------------------------------------------------

    @staticmethod
    def calculate_totals(
        line_items: List[QuoteLineItemCreate],
        tax_rate: float,
    ) -> dict:
        """
        Calculate quote totals from line items.

        Returns a dict with:
          subtotal   - Zwischensumme (netto)
          tax_amount - MwSt-Betrag
          total      - Gesamtbetrag (brutto)
        """
        subtotal = sum(item.quantity * item.unit_price for item in line_items)
        tax_amount = round(subtotal * (tax_rate / 100), 2)
        total = round(subtotal + tax_amount, 2)
        subtotal = round(subtotal, 2)
        return {"subtotal": subtotal, "tax_amount": tax_amount, "total": total}

    @staticmethod
    def _recompute_totals_from_items(quote: QuoteModel) -> None:
        """
        Recompute subtotal/tax_amount/total from the quote's CURRENT
        ``line_items`` collection, via ``calculate_totals`` — never
        hand-roll the arithmetic (Global Constraints).

        Must be called after the line_items collection reflects the desired
        end state (item appended/mutated/removed) and any pending flush, and
        while still inside the open ``transactional(db)`` block so the
        recomputed totals commit atomically with the mutation.
        """
        # cast(): mypy sees Column[T] at class level for these attributes
        # (classic Column() style, no Mapped[] here) — at runtime, on a
        # loaded instance, they are plain float/str (cost_change_service.py
        # precedent for this exact false-positive class).
        tax_rate = cast(float, quote.tax_rate)
        items = [
            QuoteLineItemCreate(
                line_type=cast(QuoteLineType, li.line_type),
                description=cast(str, li.description),
                quantity=cast(float, li.quantity),
                unit_price=cast(float, li.unit_price),
            )
            for li in quote.line_items
        ]
        totals = QuoteService.calculate_totals(items, tax_rate)
        quote.subtotal = totals["subtotal"]
        quote.tax_amount = totals["tax_amount"]
        quote.total = totals["total"]

    # -------------------------------------------------------------------------
    # Auto-generate line items from order data (mirrors invoice_service)
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_line_items_from_order(order: OrderModel) -> List[QuoteLineItemCreate]:
        """
        Build standard quote line items from an order's cost fields.

        Generates items for material, labor, and gemstones — same logic as
        InvoiceService._build_line_items_from_order so the quote is consistent
        with the eventual invoice.
        """
        items: List[QuoteLineItemCreate] = []

        # --- Material cost ---
        material_cost = order.material_cost_override or order.material_cost_calculated
        if material_cost and material_cost > 0:
            metal_desc = (
                f"Material: {order.metal_type.value}"
                if order.metal_type
                else "Material"
            )
            if order.actual_weight_g:
                metal_desc += f", {order.actual_weight_g:.2f}g"
            elif order.estimated_weight_g:
                metal_desc += f", ~{order.estimated_weight_g:.2f}g (geschaetzt)"
            items.append(
                QuoteLineItemCreate(
                    line_type=QuoteLineType.MATERIAL,
                    description=metal_desc,
                    quantity=1.0,
                    unit_price=round(material_cost, 2),
                )
            )

        # --- Labor cost ---
        if order.labor_hours and order.labor_hours > 0:
            hourly_rate = order.hourly_rate or 75.0
            items.append(
                QuoteLineItemCreate(
                    line_type=QuoteLineType.LABOR,
                    description=f"Arbeitszeit: {order.labor_hours:.2f}h x {hourly_rate:.2f} EUR/h",
                    quantity=order.labor_hours,
                    unit_price=round(hourly_rate, 2),
                )
            )
        elif order.labor_cost and order.labor_cost > 0:
            items.append(
                QuoteLineItemCreate(
                    line_type=QuoteLineType.LABOR,
                    description="Arbeitszeit",
                    quantity=1.0,
                    unit_price=round(order.labor_cost, 2),
                )
            )

        # --- Gemstones ---
        for gemstone in order.gemstones or []:
            gemstone_desc = gemstone.type.capitalize()
            if gemstone.carat:
                gemstone_desc += f" {gemstone.carat:.2f}ct"
            if gemstone.quality:
                gemstone_desc += f" {gemstone.quality}"
            if gemstone.color:
                gemstone_desc += f" {gemstone.color}"
            if gemstone.cut:
                gemstone_desc += f" {gemstone.cut}"
            items.append(
                QuoteLineItemCreate(
                    line_type=QuoteLineType.GEMSTONE,
                    description=gemstone_desc,
                    quantity=float(gemstone.quantity or 1),
                    unit_price=round(gemstone.cost, 2),
                )
            )

        # --- Fallback ---
        if not items:
            fallback_price = order.price or order.calculated_price or 0.0
            items.append(
                QuoteLineItemCreate(
                    line_type=QuoteLineType.OTHER,
                    description=f"Auftrag: {order.title}",
                    quantity=1.0,
                    unit_price=round(fallback_price, 2),
                )
            )

        return items

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @staticmethod
    async def _get_order_with_relations(
        db: AsyncSession, order_id: int
    ) -> Optional[OrderModel]:
        """Load order with all relationships needed for quote generation."""
        result = await db.execute(
            select(OrderModel)
            .options(
                selectinload(OrderModel.customer),
                selectinload(OrderModel.gemstones),
                selectinload(OrderModel.materials),
            )
            .where(OrderModel.id == order_id)
            .where(OrderModel.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _load_editable_quote_locked(
        db: AsyncSession, quote_id: int
    ) -> QuoteModel:
        """
        Load a quote FOR UPDATE with line items eagerly loaded, enforcing the
        DRAFT-only line-item edit gate shared by add/update/delete_line_item.

        MUST be called INSIDE an open ``transactional(db)`` block: the
        ``with_for_update()`` row lock is held until that block commits, so
        the DRAFT check, the mutation, and the total recompute all execute
        against a row no concurrent request can transition out of DRAFT in
        between (closes the check-then-mutate race; mirrors the FOR UPDATE
        precedent in cost_change_service.py). On SQLite the clause is a
        silent no-op — correctness there rests on SQLite's whole-database
        write lock instead.

        The typed raises here surface inside the transactional block; both
        messages are ID-only / fixed templates (never user free-text), so
        transactional()'s ``str(exc)`` rollback logger stays PII-clean.

        Raises:
            QuoteNotFoundError: no such quote (404).
            QuoteNotEditableError: quote.status != DRAFT (409).
        """
        result = await db.execute(
            select(QuoteModel)
            .options(selectinload(QuoteModel.line_items))
            .where(QuoteModel.id == quote_id)
            .with_for_update()
        )
        quote = result.scalar_one_or_none()
        if not quote:
            raise QuoteNotFoundError(quote_id)
        if quote.status != QuoteStatus.DRAFT:
            raise QuoteNotEditableError()
        return quote

    @staticmethod
    async def create_quote(
        db: AsyncSession,
        quote_in: QuoteCreate,
        current_user: UserModel,
    ) -> QuoteModel:
        """
        Create a new Kostenvoranschlag.

        When order_id is provided:
          - Loads the order and auto-generates line items from cost data
        When only customer_id is provided:
          - Creates an empty quote (caller must supply additional_line_items)

        Steps:
        1. Validate customer exists
        2. Optionally load order and build auto line items
        3. Append caller-supplied additional line items
        4. Calculate totals
        5. Generate sequential KV number
        6. Persist Quote + QuoteLineItem rows in a single transaction
        """
        # Validate customer exists
        cust_result = await db.execute(
            select(CustomerModel.id).where(CustomerModel.id == quote_in.customer_id)
        )
        if not cust_result.scalar_one_or_none():
            raise HTTPException(
                status_code=404,
                detail=f"Kunde {quote_in.customer_id} nicht gefunden",
            )

        auto_items: List[QuoteLineItemCreate] = []

        if quote_in.order_id:
            order = await QuoteService._get_order_with_relations(db, quote_in.order_id)
            if not order:
                raise HTTPException(
                    status_code=404,
                    detail=f"Auftrag {quote_in.order_id} nicht gefunden",
                )
            auto_items = QuoteService._build_line_items_from_order(order)

        all_line_items = auto_items + (quote_in.additional_line_items or [])

        # A quote with no line items is valid (DRAFT) but note it explicitly
        if not all_line_items:
            logger.info(
                "Creating quote with no line items",
                extra={"customer_id": quote_in.customer_id, "user_id": current_user.id},
            )

        totals = QuoteService.calculate_totals(all_line_items, quote_in.tax_rate)

        valid_until = datetime.utcnow() + timedelta(days=quote_in.valid_days)

        async with transactional(db):
            quote_number = await QuoteService.generate_quote_number(db)

            db_quote = QuoteModel(
                quote_number=quote_number,
                order_id=quote_in.order_id,
                customer_id=quote_in.customer_id,
                created_by=current_user.id,
                status=QuoteStatus.DRAFT,
                valid_until=valid_until,
                subtotal=totals["subtotal"],
                tax_rate=quote_in.tax_rate,
                tax_amount=totals["tax_amount"],
                total=totals["total"],
                notes=quote_in.notes,
            )
            db.add(db_quote)
            await db.flush()

            for item in all_line_items:
                db_line = QuoteLineItemModel(
                    quote_id=db_quote.id,
                    line_type=item.line_type,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total=round(item.quantity * item.unit_price, 2),
                )
                db.add(db_line)

        _log_quote_access(
            action="created",
            quote_id=db_quote.id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={"quote_number": quote_number, "total": totals["total"]},
        )

        return await QuoteService.get_quote(db, db_quote.id, current_user)

    @staticmethod
    async def get_quote(
        db: AsyncSession,
        quote_id: int,
        current_user: UserModel,
    ) -> Optional[QuoteModel]:
        """Retrieve a single quote by ID with line items eagerly loaded."""
        result = await db.execute(
            select(QuoteModel)
            .options(selectinload(QuoteModel.line_items))
            .where(QuoteModel.id == quote_id)
        )
        quote = result.scalar_one_or_none()

        if quote:
            _log_quote_access(
                action="viewed",
                quote_id=quote_id,
                user_id=current_user.id,
                user_role=_user_role_str(current_user),
            )

        return quote

    @staticmethod
    async def list_quotes(
        db: AsyncSession,
        current_user: UserModel,
        skip: int = 0,
        limit: int = 50,
        status: Optional[QuoteStatus] = None,
        customer_id: Optional[int] = None,
    ) -> tuple[List[QuoteModel], int]:
        """
        List quotes with optional filters.

        Returns (items, total_count) for pagination.
        """
        base_query = select(QuoteModel).options(selectinload(QuoteModel.line_items))
        count_query = select(func.count(QuoteModel.id))

        if status is not None:
            base_query = base_query.where(QuoteModel.status == status)
            count_query = count_query.where(QuoteModel.status == status)
        if customer_id is not None:
            base_query = base_query.where(QuoteModel.customer_id == customer_id)
            count_query = count_query.where(QuoteModel.customer_id == customer_id)

        base_query = (
            base_query.order_by(QuoteModel.created_at.desc()).offset(skip).limit(limit)
        )

        items_result = await db.execute(base_query)
        count_result = await db.execute(count_query)
        items = items_result.scalars().all()
        total = count_result.scalar_one()

        _log_quote_access(
            action="listed",
            quote_id=None,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={
                "filters": {"status": status, "customer_id": customer_id},
                "result_count": len(items),
            },
        )

        return list(items), total

    @staticmethod
    async def update_quote(
        db: AsyncSession,
        quote_id: int,
        quote_in: QuoteUpdate,
        current_user: UserModel,
    ) -> Optional[QuoteModel]:
        """
        Update mutable quote fields (valid_until, notes, and — DRAFT only —
        tax_rate).

        Returns None if not found.
        Raises 422 if attempting to update a CONVERTED quote.

        Status is NOT mutable here (security review round 1, HIGH): a status
        change via PUT would let a caller send/approve a quote, flip it back
        to DRAFT, edit the now-"legal" line items, and flip it forward again
        — defeating the SENT/APPROVED/CONVERTED immutability premise and
        leaving a re-approved quote with a stale customer_signature_data.
        Any status change must go through the dedicated
        send/approve/reject/convert actions. A ``status`` in the payload that
        differs from the current status → QuoteNotEditableError (409); an
        identical status is a harmless no-op and is allowed.

        tax_rate (security review round 1, MEDIUM): only editable while
        DRAFT. Writing tax_rate on a non-DRAFT quote would store a new rate
        while subtotal/tax_amount/total stay old — the PDF would then print a
        mismatched "MwSt X%" label. tax_rate in the payload on a non-DRAFT
        quote → QuoteNotEditableError (409). On a DRAFT quote, totals are
        recomputed from the existing line items via calculate_totals — never
        hand-rolled (bug fix: the rate used to be saved without recomputing).
        """
        result = await db.execute(
            select(QuoteModel)
            .options(selectinload(QuoteModel.line_items))
            .where(QuoteModel.id == quote_id)
        )
        quote = result.scalar_one_or_none()
        if not quote:
            return None

        immutable_statuses = {QuoteStatus.CONVERTED}
        if quote.status in immutable_statuses:
            raise HTTPException(
                status_code=422,
                detail=f"Umgewandelte Kostenvoranschlaege koennen nicht bearbeitet werden",
            )

        update_data = quote_in.model_dump(exclude_unset=True)
        if not update_data:
            return await QuoteService.get_quote(db, quote_id, current_user)

        # HIGH: reject status transitions via PUT — dedicated actions only.
        if "status" in update_data and update_data["status"] != quote.status:
            raise QuoteNotEditableError(
                "Statuswechsel nur über die dedizierten Aktionen "
                "(Versenden/Genehmigen/Ablehnen/Umwandeln)"
            )

        # MEDIUM: tax_rate is DRAFT-only (mirrors the line-item edit gate).
        if "tax_rate" in update_data and quote.status != QuoteStatus.DRAFT:
            raise QuoteNotEditableError()

        recompute_totals = (
            "tax_rate" in update_data and quote.status == QuoteStatus.DRAFT
        )

        async with transactional(db):
            for field, value in update_data.items():
                setattr(quote, field, value)
            if recompute_totals:
                QuoteService._recompute_totals_from_items(quote)

        _log_quote_access(
            action="updated",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={
                "updated_fields": list(update_data.keys()),
                "recomputed_totals": recompute_totals,
            },
        )

        return await QuoteService.get_quote(db, quote_id, current_user)

    # -------------------------------------------------------------------------
    # Line-item CRUD (editable-quotes plan, Task 1)
    # -------------------------------------------------------------------------

    @staticmethod
    async def add_line_item(
        db: AsyncSession,
        quote_id: int,
        item: QuoteLineItemCreate,
        current_user: UserModel,
    ) -> QuoteModel:
        """
        Add an Angebotsposition to a DRAFT quote and recompute totals.

        The FOR UPDATE load, DRAFT check, mutation, and recompute all run in
        one transactional block so the row lock is held through commit
        (security review round 1, MEDIUM: closes the check-then-mutate race).

        Raises:
            QuoteNotFoundError: no such quote (404).
            QuoteNotEditableError: quote.status != DRAFT (409).
        """
        async with transactional(db):
            quote = await QuoteService._load_editable_quote_locked(db, quote_id)
            db_line = QuoteLineItemModel(
                quote_id=quote.id,
                line_type=item.line_type,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total=round(item.quantity * item.unit_price, 2),
            )
            quote.line_items.append(db_line)
            await db.flush()
            QuoteService._recompute_totals_from_items(quote)
            new_item_id = db_line.id
            new_total = quote.total

        _log_quote_access(
            action="line_item_added",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={"item_id": new_item_id, "new_total": new_total},
        )

        reloaded = await QuoteService.get_quote(db, quote_id, current_user)
        if reloaded is None:
            raise QuoteNotFoundError(quote_id)
        return reloaded

    @staticmethod
    async def update_line_item(
        db: AsyncSession,
        quote_id: int,
        item_id: int,
        item: QuoteLineItemCreate,
        current_user: UserModel,
    ) -> QuoteModel:
        """
        Update an Angebotsposition on a DRAFT quote and recompute totals.

        The FOR UPDATE load, DRAFT check, mutation, and recompute all run in
        one transactional block (security review round 1, MEDIUM).

        Raises:
            QuoteNotFoundError: no such quote, or no such item on the quote (404).
            QuoteNotEditableError: quote.status != DRAFT (409).
        """
        async with transactional(db):
            quote = await QuoteService._load_editable_quote_locked(db, quote_id)
            db_line = next((li for li in quote.line_items if li.id == item_id), None)
            if db_line is None:
                raise QuoteLineItemNotFoundError(quote_id, item_id)
            db_line.line_type = item.line_type
            db_line.description = item.description
            db_line.quantity = item.quantity
            db_line.unit_price = item.unit_price
            db_line.total = round(item.quantity * item.unit_price, 2)
            QuoteService._recompute_totals_from_items(quote)
            new_total = quote.total

        _log_quote_access(
            action="line_item_updated",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={"item_id": item_id, "new_total": new_total},
        )

        reloaded = await QuoteService.get_quote(db, quote_id, current_user)
        if reloaded is None:
            raise QuoteNotFoundError(quote_id)
        return reloaded

    @staticmethod
    async def delete_line_item(
        db: AsyncSession,
        quote_id: int,
        item_id: int,
        current_user: UserModel,
    ) -> QuoteModel:
        """
        Delete an Angebotsposition from a DRAFT quote and recompute totals.

        The FOR UPDATE load, DRAFT check, deletion, and recompute all run in
        one transactional block (security review round 1, MEDIUM).

        Raises:
            QuoteNotFoundError: no such quote, or no such item on the quote (404).
            QuoteNotEditableError: quote.status != DRAFT (409).
        """
        async with transactional(db):
            quote = await QuoteService._load_editable_quote_locked(db, quote_id)
            db_line = next((li for li in quote.line_items if li.id == item_id), None)
            if db_line is None:
                raise QuoteLineItemNotFoundError(quote_id, item_id)
            quote.line_items.remove(db_line)
            await db.flush()
            QuoteService._recompute_totals_from_items(quote)
            new_total = quote.total

        _log_quote_access(
            action="line_item_deleted",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={"item_id": item_id, "new_total": new_total},
        )

        reloaded = await QuoteService.get_quote(db, quote_id, current_user)
        if reloaded is None:
            raise QuoteNotFoundError(quote_id)
        return reloaded

    # -------------------------------------------------------------------------
    # Status transitions
    # -------------------------------------------------------------------------

    @staticmethod
    async def send_quote(
        db: AsyncSession,
        quote_id: int,
        current_user: UserModel,
    ) -> Optional[QuoteModel]:
        """
        Mark a quote as SENT (Versendet).

        Only DRAFT quotes can be sent. Records audit log.
        """
        result = await db.execute(select(QuoteModel).where(QuoteModel.id == quote_id))
        quote = result.scalar_one_or_none()
        if not quote:
            return None

        if quote.status != QuoteStatus.DRAFT:
            raise HTTPException(
                status_code=422,
                detail=f"Nur Entwuerfe koennen versendet werden. "
                f"Aktueller Status: {quote.status.value}",
            )

        async with transactional(db):
            quote.status = QuoteStatus.SENT

        _log_quote_access(
            action="sent",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
        )

        return await QuoteService.get_quote(db, quote_id, current_user)

    @staticmethod
    async def approve_quote(
        db: AsyncSession,
        quote_id: int,
        request: ApproveQuoteRequest,
        current_user: UserModel,
    ) -> Optional[QuoteModel]:
        """
        Mark a quote as APPROVED (Genehmigt) and optionally store signature.

        Only SENT quotes can be approved.
        """
        result = await db.execute(select(QuoteModel).where(QuoteModel.id == quote_id))
        quote = result.scalar_one_or_none()
        if not quote:
            return None

        if quote.status not in (QuoteStatus.SENT, QuoteStatus.DRAFT):
            raise HTTPException(
                status_code=422,
                detail=f"Nur gesendete oder Entwurf-Angebote koennen genehmigt werden. "
                f"Aktueller Status: {quote.status.value}",
            )

        now = datetime.utcnow()

        async with transactional(db):
            quote.status = QuoteStatus.APPROVED
            quote.approved_at = now
            if request.signature_data:
                quote.customer_signature_data = request.signature_data

        _log_quote_access(
            action="approved",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={"has_signature": bool(request.signature_data)},
        )

        return await QuoteService.get_quote(db, quote_id, current_user)

    @staticmethod
    async def reject_quote(
        db: AsyncSession,
        quote_id: int,
        current_user: UserModel,
        reason: Optional[str] = None,
    ) -> Optional[QuoteModel]:
        """
        Mark a quote as REJECTED (Abgelehnt).

        Only SENT or DRAFT quotes can be rejected.
        """
        result = await db.execute(select(QuoteModel).where(QuoteModel.id == quote_id))
        quote = result.scalar_one_or_none()
        if not quote:
            return None

        if quote.status not in (QuoteStatus.SENT, QuoteStatus.DRAFT):
            raise HTTPException(
                status_code=422,
                detail=f"Nur gesendete oder Entwurf-Angebote koennen abgelehnt werden. "
                f"Aktueller Status: {quote.status.value}",
            )

        now = datetime.utcnow()
        notes_update = quote.notes or ""
        if reason:
            notes_update = f"{notes_update}\n[Ablehnungsgrund] {reason}".strip()

        async with transactional(db):
            quote.status = QuoteStatus.REJECTED
            quote.rejected_at = now
            if reason:
                quote.notes = notes_update

        _log_quote_access(
            action="rejected",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={"reason": reason},
        )

        return await QuoteService.get_quote(db, quote_id, current_user)

    @staticmethod
    async def convert_quote(
        db: AsyncSession,
        quote_id: int,
        current_user: UserModel,
    ) -> Optional[QuoteModel]:
        """
        Convert an APPROVED quote to a confirmed order (CONVERTED status).

        Creates a new Order in CONFIRMED status using the quote data, then
        marks the quote as CONVERTED and links it to the new order.

        Only APPROVED quotes can be converted.
        """
        result = await db.execute(
            select(QuoteModel)
            .options(selectinload(QuoteModel.line_items))
            .where(QuoteModel.id == quote_id)
        )
        quote = result.scalar_one_or_none()
        if not quote:
            return None

        if quote.status != QuoteStatus.APPROVED:
            raise HTTPException(
                status_code=422,
                detail=f"Nur genehmigte Angebote koennen umgewandelt werden. "
                f"Aktueller Status: {quote.status.value}",
            )

        now = datetime.utcnow()

        # Build order title from quote number
        order_title = f"Auftrag aus {quote.quote_number}"

        # Calculate estimated price from quote total (gross)
        estimated_price = quote.total

        async with transactional(db):
            new_order = OrderModel(
                title=order_title,
                description=quote.notes or "",
                price=estimated_price,
                status=OrderStatusEnum.CONFIRMED,
                customer_id=quote.customer_id,
            )
            db.add(new_order)
            await db.flush()

            quote.status = QuoteStatus.CONVERTED
            quote.converted_at = now
            quote.order_id = new_order.id

        _log_quote_access(
            action="converted",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={"new_order_id": new_order.id, "total": quote.total},
        )

        return await QuoteService.get_quote(db, quote_id, current_user)

    @staticmethod
    async def delete_quote(
        db: AsyncSession,
        quote_id: int,
        current_user: UserModel,
    ) -> bool:
        """
        Delete a DRAFT or REJECTED quote.

        SENT, APPROVED, or CONVERTED quotes cannot be deleted.
        Returns True if deleted, False if not found.
        """
        result = await db.execute(select(QuoteModel).where(QuoteModel.id == quote_id))
        quote = result.scalar_one_or_none()
        if not quote:
            return False

        protected_statuses = {
            QuoteStatus.SENT,
            QuoteStatus.APPROVED,
            QuoteStatus.CONVERTED,
        }
        if quote.status in protected_statuses:
            raise HTTPException(
                status_code=422,
                detail=f"Angebote mit Status '{quote.status.value}' koennen nicht geloescht werden. "
                f"Nur Entwuerfe und abgelehnte Angebote sind loeschbar.",
            )

        async with transactional(db):
            await db.delete(quote)

        _log_quote_access(
            action="deleted",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
        )

        return True
