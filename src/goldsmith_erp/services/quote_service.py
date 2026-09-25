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

from sqlalchemy import func, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    UpstreamError,
)
from goldsmith_erp.db.models import CostChangeResponseMethod
from goldsmith_erp.db.models import Customer as CustomerModel
from goldsmith_erp.db.models import CustomerUpdateStatus, InvoiceLineType, MetalType
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.models import OrderStatusEnum
from goldsmith_erp.db.models import Quote as QuoteModel
from goldsmith_erp.db.models import QuoteLineItem as QuoteLineItemModel
from goldsmith_erp.db.models import QuoteLineType, QuoteStatus, UpdateDeliveryMethod
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.quote import (
    ApproveQuoteRequest,
    QuoteCreate,
    QuoteLineItemCreate,
    QuoteUpdate,
)
from goldsmith_erp.services import consultation_carry, order_workflow, quote_delivery
from goldsmith_erp.services.number_sequence_service import (
    QUOTE_KIND,
    NumberSequenceService,
)
from goldsmith_erp.services.outbox_service import is_worker_mode

logger = logging.getLogger(__name__)

# DOM-11d: German evidence text for how the customer approved a quote.
_APPROVAL_METHOD_LABELS: dict[CostChangeResponseMethod, str] = {
    CostChangeResponseMethod.IN_PERSON: "persönlich vor Ort",
    CostChangeResponseMethod.EMAIL_REPLY: "per E-Mail",
    CostChangeResponseMethod.PHONE: "telefonisch",
}


def _soll_from_quote_lines(line_items: list) -> dict:
    """Order Soll (planned cost) from quote lines (DOM-11b).

    LABOR lines give hours (quantity) and their total gives the labour cost
    and the effective hourly rate; MATERIAL lines give the planned material
    cost. Metal weight and stones have no quote-line columns and stay for
    the order form (W2-06).
    """
    labor = [li for li in line_items if li.line_type == QuoteLineType.LABOR]
    hours = round(sum(float(li.quantity or 0.0) for li in labor), 2)
    labor_total = round(sum(float(li.total or 0.0) for li in labor), 2)
    material_total = round(
        sum(
            float(li.total or 0.0)
            for li in line_items
            if li.line_type == QuoteLineType.MATERIAL
        ),
        2,
    )
    soll: dict = {}
    if hours > 0 and labor_total > 0:
        soll["labor_hours"] = hours
        soll["hourly_rate"] = round(labor_total / hours, 2)
        soll["labor_cost"] = labor_total
    if material_total > 0:
        soll["material_cost_override"] = material_total
    return soll


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
        Next sequential quote number for the current Europe/Berlin year.

        Format: KV-YYYY-NNNN (e.g. KV-2026-0001).

        W2-04 (BE-16): drawn from the row-locked ``number_sequences`` counter
        inside the caller's transaction (see number_sequence_service).
        """
        return await NumberSequenceService.next_number(db, QUOTE_KIND)

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
            raise NotFoundError(
                f"Kunde {quote_in.customer_id} nicht gefunden",
                code="quote.customer_not_found",
            )

        auto_items: List[QuoteLineItemCreate] = []

        if quote_in.order_id:
            order = await QuoteService._get_order_with_relations(db, quote_in.order_id)
            if not order:
                raise NotFoundError(
                    f"Auftrag {quote_in.order_id} nicht gefunden",
                    code="quote.order_not_found",
                )
            if order.customer_id != quote_in.customer_id:
                raise DomainValidationError(
                    f"Auftrag {quote_in.order_id} gehoert zu einem anderen "
                    f"Kunden; Angebot und Auftrag muessen denselben Kunden haben.",
                    code="quote.order_customer_mismatch",
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
            raise DomainValidationError(
                f"Umgewandelte Kostenvoranschlaege koennen nicht bearbeitet werden",
                code="quote.converted_immutable",
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
                estimator_metadata=item.estimator_metadata,
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
            # estimator_metadata is immutable after creation — do NOT update it
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
        Versenden: deliver a DRAFT quote to the customer and mark it SENT.

        DOM-11. With SMTP configured and a customer email, the quote PDF is
        emailed; otherwise the hand-over is recorded as PDF_MANUAL (the UI
        downloads the PDF). Status becomes SENT only after a successful send
        or the manual record. An SMTP failure keeps the DRAFT, records
        SEND_FAILED and raises 502 (see services/quote_delivery.py).

        Returns None if not found. 422 if the quote is not a DRAFT.
        """
        quote = await QuoteService._load_quote(db, quote_id)
        if not quote:
            return None
        QuoteService._require_draft_for_send(quote)

        customer = await quote_delivery.load_customer(db, int(quote.customer_id))
        recipient = (
            quote_delivery.customer_email(customer)
            if quote_delivery.email_delivery_enabled()
            else None
        )
        method = UpdateDeliveryMethod.PDF_MANUAL
        queue_email = recipient is not None and is_worker_mode()
        if recipient is not None:
            method = UpdateDeliveryMethod.EMAIL
        if recipient is not None and not queue_email:
            if not await quote_delivery.email_quote(quote, customer, recipient):
                await QuoteService._record_send_failure(db, quote, current_user)
                raise UpstreamError(
                    quote_delivery.SMTP_FAILED_DETAIL,
                    code="quote.send_failed",
                )

        async with transactional(db):
            locked = await QuoteService._load_quote(db, quote_id, for_update=True)
            if locked is None:
                raise QuoteNotFoundError(quote_id)
            QuoteService._require_draft_for_send(locked)
            locked.status = QuoteStatus.SENT
            if queue_email:  # ARCH-04: the mail job commits with SENT
                await quote_delivery.enqueue_quote_email(
                    db, locked, int(current_user.id)
                )
            else:
                db.add(
                    quote_delivery.build_record(
                        locked,
                        int(current_user.id),
                        CustomerUpdateStatus.SENT,
                        method,
                        datetime.utcnow(),
                    )
                )

        _log_quote_access(
            action="sent",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={"delivery_method": method.value},
        )

        return await QuoteService.get_quote(db, quote_id, current_user)

    @staticmethod
    async def _load_quote(
        db: AsyncSession, quote_id: int, for_update: bool = False
    ) -> Optional[QuoteModel]:
        """Load a quote with line items (optionally FOR UPDATE)."""
        stmt = (
            select(QuoteModel)
            .options(selectinload(QuoteModel.line_items))
            .where(QuoteModel.id == quote_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def _require_draft_for_send(quote: QuoteModel) -> None:
        if quote.status != QuoteStatus.DRAFT:
            raise DomainValidationError(
                f"Nur Entwuerfe koennen versendet werden. "
                f"Aktueller Status: {quote.status.value}",
                code="quote.not_draft",
            )

    @staticmethod
    async def _record_send_failure(
        db: AsyncSession, quote: QuoteModel, current_user: UserModel
    ) -> None:
        """Record a failed email attempt; the quote itself stays a DRAFT."""
        async with transactional(db):
            db.add(
                quote_delivery.build_record(
                    quote,
                    int(current_user.id),
                    CustomerUpdateStatus.SEND_FAILED,
                    None,
                    None,
                )
            )
        logger.error(
            "Quote email delivery failed; quote stays DRAFT",
            extra={"quote_id": quote.id, "user_id": current_user.id},
        )

    @staticmethod
    async def get_delivery(
        db: AsyncSession, quote: QuoteModel
    ) -> Optional[quote_delivery.QuoteDelivery]:
        """How and when ``quote`` was delivered (None if never sent)."""
        return await quote_delivery.get_delivery(db, quote)

    @staticmethod
    def _approval_note(request: ApproveQuoteRequest, now: datetime) -> str:
        label = _APPROVAL_METHOD_LABELS[request.response_method]
        if request.signature_data:
            label += " mit Unterschrift"
        return f"[Freigabe] {label} am {now:%d.%m.%Y}"

    @staticmethod
    async def approve_quote(
        db: AsyncSession,
        quote_id: int,
        request: ApproveQuoteRequest,
        current_user: UserModel,
    ) -> Optional[QuoteModel]:
        """
        Mark a quote as APPROVED (Genehmigt) and optionally store signature.

        SENT or DRAFT quotes can be approved. DOM-11d: the request says how
        the customer agreed; that evidence is appended to the notes (same
        pattern as the rejection reason) and audit-logged.
        """
        result = await db.execute(select(QuoteModel).where(QuoteModel.id == quote_id))
        quote = result.scalar_one_or_none()
        if not quote:
            return None

        if quote.status not in (QuoteStatus.SENT, QuoteStatus.DRAFT):
            raise DomainValidationError(
                f"Nur gesendete oder Entwurf-Angebote koennen genehmigt werden. "
                f"Aktueller Status: {quote.status.value}",
                code="quote.approve_invalid_status",
            )

        now = datetime.utcnow()
        note = QuoteService._approval_note(request, now)

        async with transactional(db):
            quote.status = QuoteStatus.APPROVED
            quote.approved_at = now
            quote.notes = f"{quote.notes or ''}\n{note}".strip()
            if request.signature_data:
                quote.customer_signature_data = request.signature_data

        _log_quote_access(
            action="approved",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={
                "has_signature": bool(request.signature_data),
                "response_method": request.response_method.value,
            },
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
            raise DomainValidationError(
                f"Nur gesendete oder Entwurf-Angebote koennen abgelehnt werden. "
                f"Aktueller Status: {quote.status.value}",
                code="quote.reject_invalid_status",
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
        Convert an APPROVED quote into a confirmed order (CONVERTED status).

        - If the quote was built from an existing order (``quote.order_id``),
          that order is confirmed and priced from the quote; no duplicate
          order is created (BE-17). Its customer must still match (A3.4).
        - Otherwise a new CONFIRMED order is created. Its Soll (labour hours,
          rate, material cost) comes from the quote lines (DOM-11b).
        - If the quote came from a consultation, the consultation's deadline,
          order type, alloy, ring size and photos reach the order (DOM-03);
          on an existing order only empty fields are filled.

        ``Order.price`` is NET: it receives ``quote.subtotal``, never the
        gross ``quote.total`` (BE-01, ADR-2026-09-25-price-semantics). A
        quote without an agreed price cannot be converted (A3.1).

        The APPROVED -> CONVERTED step is a compare-and-set UPDATE, so two
        concurrent conversions create one order on every database (A3.3);
        the FOR UPDATE row lock is kept for Postgres.
        """
        quote = await QuoteService._load_quote(db, quote_id, for_update=True)
        if not quote:
            return None

        now = datetime.utcnow()
        QuoteService._require_convertible(quote, now)
        existing_order = await QuoteService._linked_order_for_conversion(db, quote)
        net_price = QuoteService._agreed_net_price(quote)

        consultation = await consultation_carry.consultation_for_quote(db, quote_id)
        carried = (
            await consultation_carry.fields_from_consultation(db, consultation)
            if consultation is not None
            else consultation_carry.CarriedOrderFields()
        )

        async with transactional(db):
            await QuoteService._claim_for_conversion(db, quote, now)
            if existing_order is not None:
                target_order = existing_order
                target_order.price = net_price
                if target_order.status in (
                    OrderStatusEnum.DRAFT,
                    OrderStatusEnum.NEW,
                ):
                    await order_workflow.transition(  # W2-07: table + event
                        db,
                        target_order,
                        OrderStatusEnum.CONFIRMED,
                        current_user,
                        meta={"origin": "quote_conversion", "quote_id": quote.id},
                    )
                consultation_carry.fill_empty_order_fields(target_order, carried)
            else:
                target_order = OrderModel(
                    **QuoteService._new_order_kwargs(quote, net_price, carried)
                )
                db.add(target_order)
                await db.flush()

            quote.status = QuoteStatus.CONVERTED
            quote.converted_at = now
            quote.order_id = target_order.id
            if consultation is not None:
                consultation_carry.link_consultation_to_order(
                    consultation, int(target_order.id)
                )

        _log_quote_access(
            action="converted",
            quote_id=quote_id,
            user_id=current_user.id,
            user_role=_user_role_str(current_user),
            extra={
                "order_id": target_order.id,
                "reused_existing_order": existing_order is not None,
                "consultation_id": consultation.id if consultation else None,
                "carried_fields": sorted(carried.as_order_kwargs()),
                "net_price": net_price,
                "total": quote.total,
            },
        )

        return await QuoteService.get_quote(db, quote_id, current_user)

    @staticmethod
    def _require_convertible(quote: QuoteModel, now: datetime) -> None:
        if quote.status != QuoteStatus.APPROVED:
            raise DomainValidationError(
                f"Nur genehmigte Angebote koennen umgewandelt werden. "
                f"Aktueller Status: {quote.status.value}",
                code="quote.convert_not_approved",
            )
        if quote.valid_until is not None and quote.valid_until < now:
            raise DomainValidationError(
                f"Angebot {quote.quote_number} ist abgelaufen "
                f"(gueltig bis {quote.valid_until:%d.%m.%Y}) und kann nicht "
                f"umgewandelt werden.",
                code="quote.expired",
            )

    @staticmethod
    async def _linked_order_for_conversion(
        db: AsyncSession, quote: QuoteModel
    ) -> Optional[OrderModel]:
        """The order the quote was built from; must exist and share the customer."""
        if quote.order_id is None:
            return None
        order = (
            await db.execute(
                select(OrderModel)
                .where(OrderModel.id == quote.order_id)
                .where(OrderModel.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if order is None:
            raise DomainValidationError(
                f"Verknuepfter Auftrag {quote.order_id} existiert nicht "
                f"mehr; Angebot kann nicht umgewandelt werden.",
                code="quote.linked_order_missing",
            )
        if order.customer_id != quote.customer_id:
            raise DomainValidationError(
                f"Auftrag {quote.order_id} gehoert zu einem anderen Kunden "
                f"als Angebot {quote.quote_number}; Umwandlung abgebrochen.",
                code="quote.linked_order_customer_mismatch",
            )
        return order

    @staticmethod
    def _agreed_net_price(quote: QuoteModel) -> float:
        """Net agreed price; 422 when the quote has none (same rule as invoices)."""
        net_price = round(float(quote.subtotal or 0.0), 2)
        if net_price <= 0:
            raise DomainValidationError(
                (
                    f"Angebot {quote.quote_number} hat keinen vereinbarten Preis. "
                    "Bitte zuerst Positionen mit Preis erfassen."
                ),
                code="quote.price_missing",
            )
        return net_price

    @staticmethod
    async def _claim_for_conversion(
        db: AsyncSession, quote: QuoteModel, now: datetime
    ) -> None:
        """Compare-and-set APPROVED -> CONVERTED; 409 if another call won."""
        result = await db.execute(
            update(QuoteModel)
            .where(QuoteModel.id == quote.id)
            .where(QuoteModel.status == QuoteStatus.APPROVED)
            .values(status=QuoteStatus.CONVERTED, converted_at=now)
            .execution_options(synchronize_session=False)
        )
        if cast(CursorResult, result).rowcount != 1:
            raise ConflictError(
                f"Angebot {quote.quote_number} wurde bereits umgewandelt.",
                code="quote.already_converted",
            )

    @staticmethod
    def _new_order_kwargs(
        quote: QuoteModel,
        net_price: float,
        carried: "consultation_carry.CarriedOrderFields",
    ) -> dict:
        """Columns for an order created from an unlinked quote."""
        return {
            "title": f"Auftrag aus {quote.quote_number}",
            "description": quote.notes or "",
            "price": net_price,
            "vat_rate": quote.tax_rate,
            "status": OrderStatusEnum.CONFIRMED,
            "customer_id": quote.customer_id,
            **_soll_from_quote_lines(list(quote.line_items)),
            **carried.as_order_kwargs(),
        }

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
            raise DomainValidationError(
                f"Angebote mit Status '{quote.status.value}' koennen nicht geloescht werden. "
                f"Nur Entwuerfe und abgelehnte Angebote sind loeschbar.",
                code="quote.delete_protected",
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
