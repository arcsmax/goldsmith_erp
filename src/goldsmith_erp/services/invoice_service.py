# src/goldsmith_erp/services/invoice_service.py
"""
Invoice/billing service (Rechnungswesen).

Handles:
- Sequential invoice number generation (RE-YYYY-NNNN)
- Auto-generation of line items from order data (material, labor, gemstones)
- Total calculation (subtotal, 19% MwSt, Gesamtbetrag)
- Status transitions (DRAFT -> SENT -> PAID / OVERDUE / CANCELLED)

Financial data access MUST be audit-logged per CLAUDE.md.
All service methods are async and accept AsyncSession as first parameter.
"""

import logging
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import extract, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import Customer as CustomerModel
from goldsmith_erp.db.models import Invoice as InvoiceModel
from goldsmith_erp.db.models import InvoiceLineItem as InvoiceLineItemModel
from goldsmith_erp.db.models import InvoiceLineType, InvoiceStatus
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.models import Quote as QuoteModel
from goldsmith_erp.db.models import QuoteStatus
from goldsmith_erp.db.models import ScrapGold as ScrapGoldModel
from goldsmith_erp.db.models import ScrapGoldStatus
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.invoice import (
    InvoiceCreate,
    InvoiceLineItemCreate,
    InvoiceUpdate,
    MarkPaidRequest,
)

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")
_DEFAULT_VAT_RATE = 19.0


def _to_cents(value: float | Decimal) -> Decimal:
    """Convert a money amount to Decimal rounded half-up to cents."""
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def net_from_gross(gross: float | Decimal, vat_rate_percent: float) -> Decimal:
    """
    Derive the net amount from a gross (VAT-inclusive) amount.

    net = gross / (1 + vat_rate/100), rounded half-up to cents, computed in
    Decimal (never float). See ADR-2026-09-25-price-semantics.
    """
    divisor = Decimal("1") + Decimal(str(vat_rate_percent)) / Decimal("100")
    return (Decimal(str(gross)) / divisor).quantize(_CENT, rounding=ROUND_HALF_UP)


def _log_financial_access(
    action: str,
    invoice_id: Optional[int],
    user_id: int,
    user_role: str,
    extra: Optional[dict] = None,
) -> None:
    """
    Structured audit log for financial data access.

    All invoice operations are recorded with WHO (user_id), WHAT (invoice_id),
    WHEN (timestamp), and HOW (action) to satisfy CLAUDE.md financial audit requirements.

    user_email is intentionally excluded — PII must not appear in log messages
    (CLAUDE.md: "NEVER log customer PII in plaintext").
    """
    logger.info(
        "Financial data access",
        extra={
            "audit": True,
            "action": action,
            "entity": "invoice",
            "invoice_id": invoice_id,
            "user_id": user_id,
            "user_role": user_role,
            "timestamp": datetime.utcnow().isoformat(),
            **(extra or {}),
        },
    )


class InvoiceService:
    # -------------------------------------------------------------------------
    # Invoice number generation
    # -------------------------------------------------------------------------

    @staticmethod
    async def generate_invoice_number(db: AsyncSession) -> str:
        """
        Generate the next sequential invoice number for the current year.

        Format: RE-YYYY-NNNN (e.g. RE-2026-0001)

        Uses a SELECT MAX query inside the current transaction to determine
        the highest existing sequence number for this year, then increments it.
        This is safe for low-concurrency ERP usage; a DB sequence would be
        preferable for high-throughput scenarios.
        """
        year = datetime.utcnow().year
        prefix = f"RE-{year}-"

        result = await db.execute(
            select(func.max(InvoiceModel.invoice_number)).where(
                InvoiceModel.invoice_number.like(f"{prefix}%")
            )
        )
        last_number: Optional[str] = result.scalar_one_or_none()

        if last_number:
            # Extract the sequence portion: "RE-2026-0042" -> 42
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
        line_items: List[InvoiceLineItemCreate],
        tax_rate: float,
    ) -> dict:
        """
        Calculate invoice totals from line items.

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

    # -------------------------------------------------------------------------
    # Auto-generate line items from order data
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_line_items_from_order(
        order: OrderModel,
        converted_quote: Optional[QuoteModel] = None,
    ) -> List[InvoiceLineItemCreate]:
        """
        Build invoice line items from the AGREED price of an order (BE-01/BE-02).

        Precedence (all amounts NET, see ADR-2026-09-25-price-semantics):
        1. Line items of the CONVERTED quote linked to this order
        2. ``order.price`` (net) as a single line
        3. ``order.calculated_price`` (stored GROSS by CostCalculationService),
           converted to net with ``order.vat_rate``

        The cost breakdown (material purchase cost, labor_hours x rate,
        gemstone cost) is internal Soll/Ist data and is never billed: it
        omits the margin. Raises 422 if no agreed price exists.
        """
        if converted_quote is not None and converted_quote.line_items:
            return [
                InvoiceLineItemCreate(
                    line_type=InvoiceLineType(line.line_type.value),
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=float(_to_cents(line.unit_price)),
                )
                for line in converted_quote.line_items
            ]

        if order.price is not None and order.price > 0:
            net_price = _to_cents(order.price)
        elif order.calculated_price is not None and order.calculated_price > 0:
            vat_rate = (
                order.vat_rate if order.vat_rate is not None else _DEFAULT_VAT_RATE
            )
            net_price = net_from_gross(order.calculated_price, vat_rate)
        else:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail=(
                    f"Auftrag {order.id} hat keinen vereinbarten Preis "
                    "(Preis, Kalkulation oder umgewandelter Kostenvoranschlag). "
                    "Bitte zuerst einen Preis festlegen."
                ),
            )

        return [
            InvoiceLineItemCreate(
                line_type=InvoiceLineType.OTHER,
                description=f"Auftrag: {order.title}",
                quantity=1.0,
                unit_price=float(net_price),
            )
        ]

    @staticmethod
    async def _get_converted_quote(
        db: AsyncSession, order_id: int
    ) -> Optional[QuoteModel]:
        """Return the most recently CONVERTED quote for this order, if any."""
        result = await db.execute(
            select(QuoteModel)
            .options(selectinload(QuoteModel.line_items))
            .where(
                QuoteModel.order_id == order_id,
                QuoteModel.status == QuoteStatus.CONVERTED,
            )
            .order_by(QuoteModel.converted_at.desc(), QuoteModel.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # Scrap gold credit
    # -------------------------------------------------------------------------

    @staticmethod
    async def _get_scrap_gold_credit(
        db: AsyncSession,
        order_id: int,
    ) -> List[ScrapGoldModel]:
        """
        Return the ScrapGold records for this order that qualify for an
        Altgold credit (SIGNED or CREDITED).

        CREDITED is included so that idempotent re-generation of a cancelled
        invoice does not silently drop an already-applied credit.
        """
        result = await db.execute(
            select(ScrapGoldModel).where(
                ScrapGoldModel.order_id == order_id,
                ScrapGoldModel.status.in_(
                    [ScrapGoldStatus.SIGNED, ScrapGoldStatus.CREDITED]
                ),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def _scrap_gold_credit_amount(records: Iterable[ScrapGoldModel]) -> Decimal:
        """Sum the EUR value of Altgold records (Decimal, cents, half-up)."""
        return sum(
            (_to_cents(record.total_value_eur or 0.0) for record in records),
            Decimal("0.00"),
        )

    @staticmethod
    def _set_payment_summary(invoice: InvoiceModel, credit: Decimal) -> None:
        """
        Attach the Altgold credit and the resulting amount due (BE-03).

        The credit is a POST-TAX deduction: the VAT base stays the full sale
        price, so ``subtotal``/``tax_amount``/``total`` are untouched and the
        credit only reduces what the customer pays. A negative amount_due
        means the workshop owes the customer the difference. These are
        derived, non-persisted attributes read by InvoiceResponse.
        """
        amount_due = _to_cents(invoice.total or 0.0) - credit
        setattr(invoice, "scrap_gold_credit", float(credit))
        setattr(invoice, "amount_due", float(amount_due))

    @staticmethod
    async def _attach_payment_summaries(
        db: AsyncSession, invoices: List[InvoiceModel]
    ) -> None:
        """Batch-load Altgold credits for invoices (one query, no N+1)."""
        if not invoices:
            return
        order_ids = {inv.order_id for inv in invoices}
        result = await db.execute(
            select(ScrapGoldModel).where(
                ScrapGoldModel.order_id.in_(order_ids),
                ScrapGoldModel.status.in_(
                    [ScrapGoldStatus.SIGNED, ScrapGoldStatus.CREDITED]
                ),
            )
        )
        # Keyed by order_id (typed Any: ORM Column[int] vs runtime int)
        by_order: Dict[Any, List[ScrapGoldModel]] = {}
        for record in result.scalars().all():
            by_order.setdefault(record.order_id, []).append(record)
        for invoice in invoices:
            credit = (
                Decimal("0.00")
                if invoice.status == InvoiceStatus.CANCELLED
                else InvoiceService._scrap_gold_credit_amount(
                    by_order.get(invoice.order_id, [])
                )
            )
            InvoiceService._set_payment_summary(invoice, credit)

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @staticmethod
    async def _get_order_with_relations(
        db: AsyncSession, order_id: int
    ) -> Optional[OrderModel]:
        """Load order with all relationships needed for invoice generation."""
        result = await db.execute(
            select(OrderModel)
            .options(
                selectinload(OrderModel.customer),
                selectinload(OrderModel.gemstones),
                selectinload(OrderModel.materials),
                selectinload(OrderModel.material_usage_records),
            )
            .where(OrderModel.id == order_id)
            .where(OrderModel.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_invoice_from_order(
        db: AsyncSession,
        invoice_in: InvoiceCreate,
        current_user: UserModel,
    ) -> InvoiceModel:
        """
        Create a Rechnung from an order.

        Steps:
        1. Load the order (must be COMPLETED or DELIVERED)
        2. Auto-generate line items from order cost data
        3. Append any caller-supplied additional line items
        4. Calculate totals (Zwischensumme, MwSt, Gesamtbetrag)
        5. Generate sequential invoice number (RE-YYYY-NNNN)
        6. Persist Invoice + InvoiceLineItem rows in a single transaction
        """
        order = await InvoiceService._get_order_with_relations(db, invoice_in.order_id)
        if not order:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=404, detail=f"Auftrag {invoice_in.order_id} nicht gefunden"
            )

        # Guard: only invoice completed/delivered orders
        from goldsmith_erp.db.models import OrderStatusEnum

        if order.status not in (OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail=f"Rechnung kann nur fuer abgeschlossene Auftraege erstellt werden. "
                f"Aktueller Status: {order.status.value}",
            )

        # Guard: no duplicate invoices per order
        existing = await db.execute(
            select(InvoiceModel.id).where(
                InvoiceModel.order_id == invoice_in.order_id,
                InvoiceModel.status != InvoiceStatus.CANCELLED,
            )
        )
        if existing.scalar_one_or_none():
            from fastapi import HTTPException

            raise HTTPException(
                status_code=409,
                detail=f"Fuer Auftrag {invoice_in.order_id} existiert bereits eine aktive Rechnung",
            )

        # Build line items from the agreed price (never purchase cost)
        converted_quote = await InvoiceService._get_converted_quote(
            db, invoice_in.order_id
        )
        auto_items = InvoiceService._build_line_items_from_order(order, converted_quote)

        # Scrap gold credit (Gutschrift Altgold) is a post-tax deduction and
        # is NOT a line item: it must not shrink the VAT base (BE-03).
        scrap_golds = await InvoiceService._get_scrap_gold_credit(
            db, invoice_in.order_id
        )
        for scrap_gold in scrap_golds:
            logger.info(
                "Scrap gold credit applied to invoice",
                extra={
                    "audit": True,
                    "entity": "scrap_gold",
                    "scrap_gold_id": scrap_gold.id,
                    "order_id": invoice_in.order_id,
                    "credit_eur": scrap_gold.total_value_eur,
                },
            )

        all_line_items = auto_items + (invoice_in.additional_line_items or [])

        # Calculate totals
        totals = InvoiceService.calculate_totals(all_line_items, invoice_in.tax_rate)

        async with transactional(db):
            invoice_number = await InvoiceService.generate_invoice_number(db)

            db_invoice = InvoiceModel(
                invoice_number=invoice_number,
                order_id=invoice_in.order_id,
                customer_id=order.customer_id,
                created_by=current_user.id,
                status=InvoiceStatus.DRAFT,
                issue_date=datetime.utcnow(),
                due_date=invoice_in.due_date,
                subtotal=totals["subtotal"],
                tax_rate=invoice_in.tax_rate,
                tax_amount=totals["tax_amount"],
                total=totals["total"],
                notes=invoice_in.notes,
                payment_method=invoice_in.payment_method,
            )
            db.add(db_invoice)
            await db.flush()  # Populate db_invoice.id before adding line items

            for item in all_line_items:
                db_line = InvoiceLineItemModel(
                    invoice_id=db_invoice.id,
                    line_type=item.line_type,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total=round(item.quantity * item.unit_price, 2),
                )
                db.add(db_line)

            # Transition scrap gold status to CREDITED atomically with the
            # invoice creation so the two records are always consistent.
            for scrap_gold in scrap_golds:
                if scrap_gold.status != ScrapGoldStatus.CREDITED:
                    scrap_gold.status = ScrapGoldStatus.CREDITED
                    db.add(scrap_gold)

        # Audit log AFTER successful commit
        _log_financial_access(
            action="created",
            invoice_id=db_invoice.id,
            user_id=current_user.id,
            user_role=(
                current_user.role.value
                if hasattr(current_user.role, "value")
                else str(current_user.role)
            ),
            extra={"invoice_number": invoice_number, "total": totals["total"]},
        )

        return await InvoiceService.get_invoice(db, db_invoice.id, current_user)

    @staticmethod
    async def get_invoice(
        db: AsyncSession,
        invoice_id: int,
        current_user: UserModel,
    ) -> Optional[InvoiceModel]:
        """
        Retrieve a single invoice by ID with line items eagerly loaded.

        All access is audit-logged (financial data rule).
        """
        result = await db.execute(
            select(InvoiceModel)
            .options(selectinload(InvoiceModel.line_items))
            .where(InvoiceModel.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()

        if invoice:
            await InvoiceService._attach_payment_summaries(db, [invoice])
            _log_financial_access(
                action="viewed",
                invoice_id=invoice_id,
                user_id=current_user.id,
                user_role=(
                    current_user.role.value
                    if hasattr(current_user.role, "value")
                    else str(current_user.role)
                ),
            )

        return invoice

    @staticmethod
    async def list_invoices(
        db: AsyncSession,
        current_user: UserModel,
        skip: int = 0,
        limit: int = 50,
        status: Optional[InvoiceStatus] = None,
        customer_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> tuple[List[InvoiceModel], int]:
        """
        List invoices with optional filters.

        Returns (items, total_count) for pagination.
        All list access is audit-logged.
        """
        base_query = select(InvoiceModel).options(selectinload(InvoiceModel.line_items))
        count_query = select(func.count(InvoiceModel.id))

        if status is not None:
            base_query = base_query.where(InvoiceModel.status == status)
            count_query = count_query.where(InvoiceModel.status == status)
        if customer_id is not None:
            base_query = base_query.where(InvoiceModel.customer_id == customer_id)
            count_query = count_query.where(InvoiceModel.customer_id == customer_id)
        if date_from is not None:
            base_query = base_query.where(InvoiceModel.issue_date >= date_from)
            count_query = count_query.where(InvoiceModel.issue_date >= date_from)
        if date_to is not None:
            base_query = base_query.where(InvoiceModel.issue_date <= date_to)
            count_query = count_query.where(InvoiceModel.issue_date <= date_to)

        base_query = (
            base_query.order_by(InvoiceModel.issue_date.desc())
            .offset(skip)
            .limit(limit)
        )

        items_result = await db.execute(base_query)
        count_result = await db.execute(count_query)
        items = list(items_result.scalars().all())
        total = count_result.scalar_one()
        await InvoiceService._attach_payment_summaries(db, items)

        _log_financial_access(
            action="listed",
            invoice_id=None,
            user_id=current_user.id,
            user_role=(
                current_user.role.value
                if hasattr(current_user.role, "value")
                else str(current_user.role)
            ),
            extra={
                "filters": {"status": status, "customer_id": customer_id},
                "result_count": len(items),
            },
        )

        return items, total

    @staticmethod
    async def update_invoice(
        db: AsyncSession,
        invoice_id: int,
        invoice_in: InvoiceUpdate,
        current_user: UserModel,
    ) -> Optional[InvoiceModel]:
        """
        Update mutable invoice fields (due_date, notes, payment_method).

        Status is NOT editable here (BE-05); use send / mark-paid / cancel.
        Returns None if invoice not found.
        Raises 409 if the invoice is PAID or CANCELLED (final documents).
        """
        result = await db.execute(
            select(InvoiceModel).where(InvoiceModel.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            return None

        if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=409,
                detail=(
                    "Bezahlte oder stornierte Rechnungen koennen nicht "
                    "bearbeitet werden"
                ),
            )

        update_data = invoice_in.model_dump(exclude_unset=True)
        if not update_data:
            return await InvoiceService.get_invoice(db, invoice_id, current_user)

        async with transactional(db):
            for field, value in update_data.items():
                setattr(invoice, field, value)

        _log_financial_access(
            action="updated",
            invoice_id=invoice_id,
            user_id=current_user.id,
            user_role=(
                current_user.role.value
                if hasattr(current_user.role, "value")
                else str(current_user.role)
            ),
            extra={"updated_fields": list(update_data.keys())},
        )

        return await InvoiceService.get_invoice(db, invoice_id, current_user)

    @staticmethod
    async def mark_as_sent(
        db: AsyncSession,
        invoice_id: int,
        current_user: UserModel,
    ) -> Optional[InvoiceModel]:
        """
        Mark a DRAFT invoice as SENT (versendet).

        Returns None if not found; raises 409 for any other current status.
        """
        result = await db.execute(
            select(InvoiceModel).where(InvoiceModel.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            return None

        if invoice.status != InvoiceStatus.DRAFT:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=409,
                detail=(
                    f"Nur Entwuerfe koennen versendet werden. "
                    f"Aktueller Status: {invoice.status.value}"
                ),
            )

        async with transactional(db):
            invoice.status = InvoiceStatus.SENT

        _log_financial_access(
            action="sent",
            invoice_id=invoice_id,
            user_id=current_user.id,
            user_role=(
                current_user.role.value
                if hasattr(current_user.role, "value")
                else str(current_user.role)
            ),
        )

        return await InvoiceService.get_invoice(db, invoice_id, current_user)

    @staticmethod
    async def mark_as_paid(
        db: AsyncSession,
        invoice_id: int,
        request: MarkPaidRequest,
        current_user: UserModel,
    ) -> Optional[InvoiceModel]:
        """
        Mark an invoice as PAID (bezahlt).

        Sets status=PAID, paid_date (defaults to now), and optionally payment_method.
        Only DRAFT, SENT, or OVERDUE invoices can be marked as paid.
        """
        result = await db.execute(
            select(InvoiceModel).where(InvoiceModel.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            return None

        allowed_transitions = {
            InvoiceStatus.DRAFT,
            InvoiceStatus.SENT,
            InvoiceStatus.OVERDUE,
        }
        if invoice.status not in allowed_transitions:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail=f"Rechnung mit Status '{invoice.status.value}' kann nicht als bezahlt markiert werden. "
                f"Erlaubt: {', '.join(s.value for s in allowed_transitions)}",
            )

        paid_at = request.paid_date or datetime.utcnow()

        async with transactional(db):
            invoice.status = InvoiceStatus.PAID
            invoice.paid_date = paid_at
            if request.payment_method:
                invoice.payment_method = request.payment_method

        _log_financial_access(
            action="marked_paid",
            invoice_id=invoice_id,
            user_id=current_user.id,
            user_role=(
                current_user.role.value
                if hasattr(current_user.role, "value")
                else str(current_user.role)
            ),
            extra={
                "paid_date": paid_at.isoformat(),
                "payment_method": request.payment_method,
            },
        )

        return await InvoiceService.get_invoice(db, invoice_id, current_user)

    @staticmethod
    async def cancel_invoice(
        db: AsyncSession,
        invoice_id: int,
        current_user: UserModel,
    ) -> Optional[InvoiceModel]:
        """
        Cancel (stornieren) an invoice.

        PAID invoices cannot be cancelled — a credit note (Storno) process
        would be needed; that is out of scope for this implementation.
        """
        result = await db.execute(
            select(InvoiceModel).where(InvoiceModel.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            return None

        if invoice.status == InvoiceStatus.PAID:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422,
                detail="Bezahlte Rechnungen koennen nicht storniert werden. "
                "Bitte kontaktieren Sie den Administrator fuer eine Storno-Gutschrift.",
            )

        if invoice.status == InvoiceStatus.CANCELLED:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=422, detail="Rechnung ist bereits storniert"
            )

        async with transactional(db):
            invoice.status = InvoiceStatus.CANCELLED

        _log_financial_access(
            action="cancelled",
            invoice_id=invoice_id,
            user_id=current_user.id,
            user_role=(
                current_user.role.value
                if hasattr(current_user.role, "value")
                else str(current_user.role)
            ),
        )

        return await InvoiceService.get_invoice(db, invoice_id, current_user)
