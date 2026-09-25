# src/goldsmith_erp/services/invoice_service.py
"""
Invoice/billing service (Rechnungswesen).

Handles:
- Sequential invoice number generation (RE-YYYY-NNNN), gap-free per
  Europe/Berlin year from ``number_sequences`` (W2-04, BE-16)
- Stornorechnung: an issued invoice is never edited; cancelling it emits a
  negative invoice with its own number that links to it (W2-04, DOM-24b)
- Auto-generation of line items from order data (material, labor, gemstones)
- Total calculation (subtotal, 19% MwSt, Gesamtbetrag)
- Status transitions (DRAFT -> SENT -> PAID / OVERDUE / CANCELLED)

Financial data access MUST be audit-logged per CLAUDE.md.
All service methods are async and accept AsyncSession as first parameter.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Union

from sqlalchemy import extract, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from goldsmith_erp.core.timeutil import ensure_utc
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
    InvoiceCreateBase,
    InvoiceLineItemCreate,
    InvoiceUpdate,
    MarkPaidRequest,
    StornoRequest,
)
from goldsmith_erp.services.invoice_snapshot_service import InvoiceSnapshotService
from goldsmith_erp.services.job_service import JobService
from goldsmith_erp.services.number_sequence_service import (
    INVOICE_KIND,
    NumberSequenceService,
)
from goldsmith_erp.services.workshop_settings_service import WorkshopSettingsService

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")
_DEFAULT_VAT_RATE = 19.0


@dataclass(frozen=True)
class InvoiceSubject:
    """What an invoice bills: an order or a repair (ARCH phase 5).

    ``title`` / ``completed_at`` feed the snapshot (``order_title``,
    Leistungsdatum default); ``reference`` / ``reference_label`` replace
    the "Auftragsnummer" row on the PDF when set (repairs).
    """

    order_id: Optional[int]
    customer_id: int
    customer: Any
    title: Optional[str]
    completed_at: Optional[datetime]
    reference: Optional[str] = None
    reference_label: Optional[str] = None
    # W2-06-14-16-11 open item #1: the order's gemstones, carried through so
    # InvoiceSnapshotService.build() can capture them into the frozen
    # snapshot. Empty for a repair-billed invoice (repairs have none).
    gemstones: Any = None

    @staticmethod
    def for_order(order: Any) -> "InvoiceSubject":
        return InvoiceSubject(
            order_id=int(order.id),
            customer_id=order.customer_id,
            customer=order.customer,
            title=order.title,
            completed_at=order.completed_at,
            gemstones=getattr(order, "gemstones", None),
        )


JobSync = Callable[[AsyncSession], Awaitable[Any]]


def _to_cents(value: float | int | Decimal) -> Decimal:
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


def _http_error(status_code: int, detail: str) -> Exception:
    from fastapi import HTTPException

    return HTTPException(status_code=status_code, detail=detail)


def _role(user: UserModel) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


def _is_storno(invoice: InvoiceModel) -> bool:
    return invoice.cancels_invoice_id is not None


def _require_not_storno(invoice: InvoiceModel) -> None:
    if _is_storno(invoice):
        raise _http_error(
            422,
            "Eine Stornorechnung ist endgültig und kann nicht geändert, "
            "bezahlt oder storniert werden.",
        )


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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
        Next sequential invoice number for the current Europe/Berlin year.

        Format: RE-YYYY-NNNN (e.g. RE-2026-0001; RE-2026-10000 after 9999).

        W2-04 (BE-16): drawn from the row-locked ``number_sequences`` counter
        inside the caller's transaction, so concurrent creates get distinct
        numbers and a rolled back create gives its number back.
        """
        return await NumberSequenceService.next_number(db, INVOICE_KIND)

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

        A1: computed in Decimal with ROUND_HALF_UP to cents (ADR
        2026-09-25), never float ``round()`` (``round(0.145, 2) == 0.14``).
        ``total - subtotal == tax_amount`` holds exactly.
        """
        raw_subtotal = sum(
            (
                Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
                for item in line_items
            ),
            Decimal("0"),
        )
        subtotal = _to_cents(raw_subtotal)
        tax_amount = _to_cents(subtotal * Decimal(str(tax_rate)) / Decimal("100"))
        total = subtotal + tax_amount
        return {
            "subtotal": float(subtotal),
            "tax_amount": float(tax_amount),
            "total": float(total),
        }

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
                    unit_price=_to_cents(line.unit_price),
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

            raise DomainValidationError(
                (
                    f"Auftrag {order.id} hat keinen vereinbarten Preis "
                    "(Preis, Kalkulation oder umgewandelter Kostenvoranschlag). "
                    "Bitte zuerst einen Preis festlegen."
                ),
                code="invoice.order_price_missing",
            )

        return [
            InvoiceLineItemCreate(
                line_type=InvoiceLineType.OTHER,
                description=f"Auftrag: {order.title}",
                quantity=1.0,
                unit_price=net_price,
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
        setattr(invoice, "scrap_gold_credit", credit)
        setattr(invoice, "amount_due", amount_due)

    @staticmethod
    async def _attach_payment_summaries(
        db: AsyncSession, invoices: List[InvoiceModel]
    ) -> None:
        """Batch-load Altgold credits for invoices (one query, no N+1)."""
        if not invoices:
            return
        order_ids = {inv.order_id for inv in invoices if inv.order_id is not None}
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
        storno_of = await InvoiceService._storno_ids_for(
            db, [inv.id for inv in invoices]
        )
        for invoice in invoices:
            # A Stornorechnung carries no Altgold credit: the credit belongs
            # to the order's live invoice (W2-04).
            credit = (
                Decimal("0.00")
                if invoice.status == InvoiceStatus.CANCELLED or _is_storno(invoice)
                else InvoiceService._scrap_gold_credit_amount(
                    by_order.get(invoice.order_id, [])
                )
            )
            InvoiceService._set_payment_summary(invoice, credit)
            setattr(invoice, "cancelled_by_invoice_id", storno_of.get(invoice.id))

    @staticmethod
    async def _storno_ids_for(
        db: AsyncSession, invoice_ids: List[Any]
    ) -> Dict[Any, int]:
        """Map original invoice id -> id of its Stornorechnung (one query)."""
        if not invoice_ids:
            return {}
        rows = await db.execute(
            select(InvoiceModel.cancels_invoice_id, InvoiceModel.id).where(
                InvoiceModel.cancels_invoice_id.in_(invoice_ids)
            )
        )
        return {original: storno for original, storno in rows.all()}

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

            raise NotFoundError(
                f"Auftrag {invoice_in.order_id} nicht gefunden",
                code="invoice.order_not_found",
            )

        # Guard: only invoice completed/delivered orders
        from goldsmith_erp.db.models import OrderStatusEnum

        if order.status not in (OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED):

            raise DomainValidationError(
                f"Rechnung kann nur fuer abgeschlossene Auftraege erstellt werden. "
                f"Aktueller Status: {order.status.value}",
                code="invoice.order_not_completed",
            )

        # Guard: no duplicate invoices per order (Stornorechnungen do not
        # count; the partial unique index uq_invoices_one_active_per_order
        # backs this check against races).
        existing = await db.execute(
            select(InvoiceModel.id).where(
                InvoiceModel.order_id == invoice_in.order_id,
                InvoiceModel.status != InvoiceStatus.CANCELLED,
                InvoiceModel.cancels_invoice_id.is_(None),
            )
        )
        if existing.scalar_one_or_none():

            raise ConflictError(
                f"Fuer Auftrag {invoice_in.order_id} existiert bereits eine aktive Rechnung",
                code="invoice.duplicate_active",
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

        # W2-04: default rate from the Werkstatt-Stammdaten; 0 for a
        # Kleinunternehmer (§19 UStG).
        tax_rate = await WorkshopSettingsService.vat_rate_for_new_invoice(
            db, invoice_in.tax_rate
        )
        seller = await WorkshopSettingsService.seller_block(db)
        totals = InvoiceService.calculate_totals(all_line_items, tax_rate)

        async def sync_job(session: AsyncSession) -> Any:
            return await JobService.sync_order(session, order)

        try:
            db_invoice = await InvoiceService._persist_new_invoice(
                db,
                invoice_in,
                InvoiceSubject.for_order(order),
                current_user,
                all_line_items,
                totals,
                tax_rate,
                seller,
                scrap_golds,
                sync_job=sync_job,
            )
        except IntegrityError as exc:
            logger.warning(
                "Concurrent invoice create for the same order rejected",
                extra={"order_id": invoice_in.order_id},
            )
            raise _http_error(
                409,
                f"Fuer Auftrag {invoice_in.order_id} existiert bereits eine "
                "aktive Rechnung",
            ) from exc

        # Audit log AFTER successful commit
        _log_financial_access(
            action="created",
            invoice_id=db_invoice.id,
            user_id=current_user.id,
            user_role=_role(current_user),
            extra={
                "invoice_number": db_invoice.invoice_number,
                "total": totals["total"],
            },
        )

        return await InvoiceService.get_invoice(db, db_invoice.id, current_user)

    @staticmethod
    async def _persist_new_invoice(
        db: AsyncSession,
        invoice_in: Union[InvoiceCreate, InvoiceCreateBase],
        subject: InvoiceSubject,
        current_user: UserModel,
        all_line_items: List[InvoiceLineItemCreate],
        totals: dict,
        tax_rate: float,
        seller: Dict[str, Any],
        scrap_golds: List[ScrapGoldModel],
        *,
        sync_job: JobSync,
    ) -> InvoiceModel:
        """Insert invoice + lines + snapshot in one transaction.

        ``sync_job`` creates/refreshes the billed job inside the same
        transaction (ARCH phase 5); the invoice gets its ``job_id``.
        """
        async with transactional(db):
            job = await sync_job(db)
            invoice_number = await InvoiceService.generate_invoice_number(db)

            db_invoice = InvoiceModel(
                invoice_number=invoice_number,
                order_id=subject.order_id,
                job_id=job.id,
                customer_id=subject.customer_id,
                created_by=current_user.id,
                status=InvoiceStatus.DRAFT,
                issue_date=datetime.now(timezone.utc),
                due_date=invoice_in.due_date,
                service_date=invoice_in.service_date or subject.completed_at,
                subtotal=totals["subtotal"],
                tax_rate=tax_rate,
                tax_amount=totals["tax_amount"],
                total=totals["total"],
                notes=invoice_in.notes,
                payment_method=invoice_in.payment_method,
            )
            db.add(db_invoice)
            await db.flush()  # Populate db_invoice.id before adding line items

            db_lines = []
            for item in all_line_items:
                db_line = InvoiceLineItemModel(
                    invoice_id=db_invoice.id,
                    line_type=item.line_type,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total=_to_cents(
                        Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
                    ),
                )
                db.add(db_line)
                db_lines.append(db_line)

            # W1-10: immutable snapshot of recipient/seller/lines/totals,
            # taken now so later customer changes never reach this invoice.
            db_invoice.snapshot = InvoiceSnapshotService.dump(
                InvoiceSnapshotService.build(
                    db_invoice,
                    db_lines,
                    subject.customer,
                    subject,
                    scrap_gold_credit=InvoiceService._scrap_gold_credit_amount(
                        scrap_golds
                    ),
                    seller=seller,
                )
            )

            # Transition scrap gold status to CREDITED atomically with the
            # invoice creation so the two records are always consistent.
            for scrap_gold in scrap_golds:
                if scrap_gold.status != ScrapGoldStatus.CREDITED:
                    scrap_gold.status = ScrapGoldStatus.CREDITED
                    db.add(scrap_gold)
        return db_invoice

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
        Raises 409 unless the invoice is a DRAFT: an issued Rechnung is
        locked (W2-04, §14 UStG / GoBD); corrections go through a Storno.
        """
        result = await db.execute(
            select(InvoiceModel).where(InvoiceModel.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            return None

        if invoice.status != InvoiceStatus.DRAFT:
            raise ConflictError(
                (
                    "Ausgestellte, bezahlte oder stornierte Rechnungen koennen nicht "
                    "bearbeitet werden. Bitte stattdessen stornieren."
                ),
                code="invoice.locked",
            )

        update_data = invoice_in.model_dump(exclude_unset=True)
        if not update_data:
            return await InvoiceService.get_invoice(db, invoice_id, current_user)

        async with transactional(db):
            for field, value in update_data.items():
                setattr(invoice, field, value)
            # DRAFT snapshot follows the invoice's own fields; frozen ones
            # are write-once (W1-10).
            InvoiceSnapshotService.sync_draft_fields(invoice)

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

            raise ConflictError(
                (
                    f"Nur Entwuerfe koennen versendet werden. "
                    f"Aktueller Status: {invoice.status.value}"
                ),
                code="invoice.not_draft",
            )

        async with transactional(db):
            invoice.status = InvoiceStatus.SENT
            # W1-10: the issued document is frozen (PDF bytes + SHA-256).
            await InvoiceSnapshotService.freeze(db, invoice)

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

        _require_not_storno(invoice)
        allowed_transitions = {
            InvoiceStatus.DRAFT,
            InvoiceStatus.SENT,
            InvoiceStatus.OVERDUE,
        }
        if invoice.status not in allowed_transitions:

            raise DomainValidationError(
                f"Rechnung mit Status '{invoice.status.value}' kann nicht als bezahlt markiert werden. "
                f"Erlaubt: {', '.join(s.value for s in allowed_transitions)}",
                code="invoice.invalid_payment_transition",
            )

        paid_at = request.paid_date or datetime.now(timezone.utc)

        async with transactional(db):
            was_draft = invoice.status == InvoiceStatus.DRAFT
            invoice.status = InvoiceStatus.PAID
            invoice.paid_date = paid_at
            if request.payment_method:
                invoice.payment_method = request.payment_method
            if was_draft:
                # Issued straight from DRAFT (e.g. paid cash at pickup):
                # freeze now, with the payment method on the document.
                await InvoiceSnapshotService.freeze(db, invoice)

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

        - DRAFT: voided (never issued, so no Storno document is needed).
        - SENT / OVERDUE: a Stornorechnung is emitted (W2-04, DOM-24b); the
          original moves to CANCELLED and is otherwise untouched.
        - PAID: refused (422); a paid invoice is reversed explicitly with
          ``create_storno`` (POST /invoices/{id}/storno) so the refund is a
          deliberate step.
        """
        result = await db.execute(
            select(InvoiceModel).where(InvoiceModel.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            return None
        _require_not_storno(invoice)

        if invoice.status == InvoiceStatus.PAID:

            raise DomainValidationError(
                "Bezahlte Rechnungen koennen nicht storniert werden. "
                "Bitte kontaktieren Sie den Administrator fuer eine Storno-Gutschrift.",
                code="invoice.cancel_paid",
            )

        if invoice.status == InvoiceStatus.CANCELLED:

            raise DomainValidationError(
                "Rechnung ist bereits storniert",
                code="invoice.already_cancelled",
            )

        if invoice.status in (InvoiceStatus.SENT, InvoiceStatus.OVERDUE):
            await InvoiceService.create_storno(
                db, invoice_id, StornoRequest(reason=None), current_user
            )
            return await InvoiceService.get_invoice(db, invoice_id, current_user)

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

    # -------------------------------------------------------------------------
    # Storno (W2-04, DOM-24b)
    # -------------------------------------------------------------------------

    @staticmethod
    async def create_storno(
        db: AsyncSession,
        invoice_id: int,
        request: StornoRequest,
        current_user: UserModel,
    ) -> Optional[InvoiceModel]:
        """
        Reverse an issued invoice with a Stornorechnung.

        The original is never edited: its frozen PDF stays as issued and only
        its status moves to CANCELLED. The Storno is a new invoice with its
        own RE number, the same recipient (from the original's snapshot, not
        the live customer), the negated lines and totals, a link
        ``cancels_invoice_id`` and the current seller data. It is issued
        (SENT, PDF frozen) at once.

        Returns None if not found. 422 for a DRAFT (void it with cancel), an
        already cancelled invoice, or a Stornorechnung itself.
        """
        original = (
            await db.execute(
                select(InvoiceModel)
                .options(selectinload(InvoiceModel.line_items))
                .where(InvoiceModel.id == invoice_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if original is None:
            return None
        InvoiceService._require_reversible(original)

        async with transactional(db):
            # The issued original keeps exactly the document it was issued as.
            await InvoiceSnapshotService.freeze(db, original)
            storno = await InvoiceService._build_storno(
                db, original, request, current_user
            )
            original.status = InvoiceStatus.CANCELLED
            await InvoiceSnapshotService.freeze(db, storno)

        _log_financial_access(
            action="storno_created",
            invoice_id=storno.id,
            user_id=current_user.id,
            user_role=_role(current_user),
            extra={
                "cancels_invoice_id": original.id,
                "invoice_number": storno.invoice_number,
                "total": storno.total,
            },
        )
        return await InvoiceService.get_invoice(db, storno.id, current_user)

    @staticmethod
    def _require_reversible(invoice: InvoiceModel) -> None:
        _require_not_storno(invoice)
        if invoice.status == InvoiceStatus.DRAFT:
            raise _http_error(
                422,
                "Ein Entwurf wurde nie ausgestellt und wird nicht storniert, "
                "sondern verworfen (Stornieren ohne Stornorechnung).",
            )
        if invoice.status == InvoiceStatus.CANCELLED:
            raise _http_error(422, "Rechnung ist bereits storniert")

    @staticmethod
    async def _build_storno(
        db: AsyncSession,
        original: InvoiceModel,
        request: StornoRequest,
        current_user: UserModel,
    ) -> InvoiceModel:
        """Insert the negated copy of ``original`` (flush only)."""
        original_snapshot = InvoiceSnapshotService.load(original) or {}
        header = original_snapshot.get("invoice", {})
        now = datetime.now(timezone.utc)
        storno = InvoiceModel(
            invoice_number=await InvoiceService.generate_invoice_number(db),
            order_id=original.order_id,
            job_id=original.job_id,
            customer_id=original.customer_id,
            created_by=current_user.id,
            status=InvoiceStatus.SENT,
            issue_date=now,
            due_date=now,
            service_date=(
                ensure_utc(datetime.fromisoformat(header["service_date"]))
                if header.get("service_date")
                else original.service_date or original.issue_date
            ),
            subtotal=-_to_cents(original.subtotal or 0),
            tax_rate=original.tax_rate,
            tax_amount=-_to_cents(original.tax_amount or 0),
            total=-_to_cents(original.total or 0),
            notes=request.reason,
            cancels_invoice_id=original.id,
        )
        db.add(storno)
        await db.flush()
        lines = [
            InvoiceLineItemModel(
                invoice_id=storno.id,
                line_type=line.line_type,
                description=line.description,
                quantity=line.quantity,
                unit_price=-_to_cents(line.unit_price or 0),
                total=-_to_cents(line.total or 0),
            )
            for line in original.line_items
        ]
        db.add_all(lines)
        snapshot = InvoiceSnapshotService.build(
            storno,
            lines,
            None,
            None,
            seller=await WorkshopSettingsService.seller_block(db),
            cancels=original,
            storno_reason=request.reason,
        )
        if original_snapshot.get("recipient"):
            snapshot["recipient"] = original_snapshot["recipient"]
        snapshot["invoice"]["order_title"] = header.get("order_title")
        if header.get("reference"):
            snapshot["invoice"]["reference"] = header["reference"]
            snapshot["invoice"]["reference_label"] = header.get("reference_label")
        storno.snapshot = InvoiceSnapshotService.dump(snapshot)
        await db.flush()
        return storno
