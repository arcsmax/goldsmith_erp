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
from datetime import datetime, date
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, extract
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Invoice as InvoiceModel,
    InvoiceLineItem as InvoiceLineItemModel,
    InvoiceStatus,
    InvoiceLineType,
    Order as OrderModel,
    Customer as CustomerModel,
    User as UserModel,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.invoice import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceLineItemCreate,
    MarkPaidRequest,
)

logger = logging.getLogger(__name__)


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
    def _build_line_items_from_order(order: OrderModel) -> List[InvoiceLineItemCreate]:
        """
        Build standard line items from an order's cost fields.

        Generates:
        1. Material line item (if material_cost_calculated or material_cost_override)
        2. Labor line item (if labor_hours > 0)
        3. One line item per gemstone (if gemstones are attached)
        4. Falls back to a single line item from order.price if no cost breakdown exists
        """
        items: List[InvoiceLineItemCreate] = []

        # --- Material cost ---
        material_cost = order.material_cost_override or order.material_cost_calculated
        if material_cost and material_cost > 0:
            metal_desc = f"Material: {order.metal_type.value}" if order.metal_type else "Material"
            if order.actual_weight_g:
                metal_desc += f", {order.actual_weight_g:.2f}g"
            elif order.estimated_weight_g:
                metal_desc += f", ~{order.estimated_weight_g:.2f}g (geschaetzt)"
            items.append(
                InvoiceLineItemCreate(
                    line_type=InvoiceLineType.MATERIAL,
                    description=metal_desc,
                    quantity=1.0,
                    unit_price=round(material_cost, 2),
                )
            )

        # --- Labor cost ---
        if order.labor_hours and order.labor_hours > 0:
            hourly_rate = order.hourly_rate or 75.0
            labor_cost = round(order.labor_hours * hourly_rate, 2)
            items.append(
                InvoiceLineItemCreate(
                    line_type=InvoiceLineType.LABOR,
                    description=f"Arbeitszeit: {order.labor_hours:.2f}h x {hourly_rate:.2f} EUR/h",
                    quantity=order.labor_hours,
                    unit_price=round(hourly_rate, 2),
                )
            )
        elif order.labor_cost and order.labor_cost > 0:
            items.append(
                InvoiceLineItemCreate(
                    line_type=InvoiceLineType.LABOR,
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
                InvoiceLineItemCreate(
                    line_type=InvoiceLineType.GEMSTONE,
                    description=gemstone_desc,
                    quantity=float(gemstone.quantity or 1),
                    unit_price=round(gemstone.cost, 2),
                )
            )

        # --- Fallback: use order.price or calculated_price if no breakdown available ---
        if not items:
            fallback_price = order.price or order.calculated_price or 0.0
            items.append(
                InvoiceLineItemCreate(
                    line_type=InvoiceLineType.OTHER,
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
    async def _get_order_with_relations(db: AsyncSession, order_id: int) -> Optional[OrderModel]:
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
            raise HTTPException(status_code=404, detail=f"Auftrag {invoice_in.order_id} nicht gefunden")

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

        # Build line items
        auto_items = InvoiceService._build_line_items_from_order(order)
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

        # Audit log AFTER successful commit
        _log_financial_access(
            action="created",
            invoice_id=db_invoice.id,
            user_id=current_user.id,
            user_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
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
            _log_financial_access(
                action="viewed",
                invoice_id=invoice_id,
                user_id=current_user.id,
                user_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
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

        base_query = base_query.order_by(InvoiceModel.issue_date.desc()).offset(skip).limit(limit)

        items_result = await db.execute(base_query)
        count_result = await db.execute(count_query)
        items = items_result.scalars().all()
        total = count_result.scalar_one()

        _log_financial_access(
            action="listed",
            invoice_id=None,
            user_id=current_user.id,
            user_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            extra={"filters": {"status": status, "customer_id": customer_id}, "result_count": len(items)},
        )

        return list(items), total

    @staticmethod
    async def update_invoice(
        db: AsyncSession,
        invoice_id: int,
        invoice_in: InvoiceUpdate,
        current_user: UserModel,
    ) -> Optional[InvoiceModel]:
        """
        Update mutable invoice fields (status, due_date, notes, payment_method).

        Returns None if invoice not found.
        Raises 422 if attempting to update a CANCELLED invoice.
        """
        result = await db.execute(
            select(InvoiceModel).where(InvoiceModel.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            return None

        if invoice.status == InvoiceStatus.CANCELLED:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=422,
                detail="Stornierte Rechnungen koennen nicht bearbeitet werden",
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
            user_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            extra={"updated_fields": list(update_data.keys())},
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

        allowed_transitions = {InvoiceStatus.DRAFT, InvoiceStatus.SENT, InvoiceStatus.OVERDUE}
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
            user_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            extra={"paid_date": paid_at.isoformat(), "payment_method": request.payment_method},
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
            raise HTTPException(status_code=422, detail="Rechnung ist bereits storniert")

        async with transactional(db):
            invoice.status = InvoiceStatus.CANCELLED

        _log_financial_access(
            action="cancelled",
            invoice_id=invoice_id,
            user_id=current_user.id,
            user_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        )

        return await InvoiceService.get_invoice(db, invoice_id, current_user)
