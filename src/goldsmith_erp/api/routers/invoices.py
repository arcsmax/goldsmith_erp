# src/goldsmith_erp/api/routers/invoices.py
"""
Invoice/billing API router (Rechnungswesen).

All endpoints are restricted to ADMIN and GOLDSMITH roles.
Financial data access is audit-logged by the service layer.

Endpoints:
  POST   /api/v1/invoices                      - Create invoice from order
  GET    /api/v1/invoices                      - List invoices (with filters)
  GET    /api/v1/invoices/export/datev         - DATEV Buchungsstapel CSV (ADMIN)
  GET    /api/v1/invoices/export/lexoffice     - Lexoffice CSV (ADMIN)
  GET    /api/v1/invoices/{invoice_id}         - Get single invoice
  PUT    /api/v1/invoices/{invoice_id}         - Update invoice status/notes
  POST   /api/v1/invoices/{invoice_id}/mark-paid   - Mark as paid
  POST   /api/v1/invoices/{invoice_id}/cancel      - Cancel invoice
  GET    /api/v1/invoices/{invoice_id}/pdf         - Download invoice as PDF

IMPORTANT: The /export/* routes MUST be registered before /{invoice_id} routes
to prevent FastAPI from treating "export" as an invoice_id path parameter.
"""

import io
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import Customer, Invoice, InvoiceStatus, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.invoice import (
    InvoiceCreate,
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceUpdate,
    MarkPaidRequest,
)
from goldsmith_erp.services.invoice_service import InvoiceService
from goldsmith_erp.services.pdf_service import PDFService
from goldsmith_erp.services.accounting_export_service import (
    export_datev_csv,
    export_lexoffice_csv,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
@require_permission(Permission.INVOICE_CREATE)
async def create_invoice(
    invoice_in: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rechnung erstellen (Create invoice from order).

    Auto-populates line items from the order's material costs, labor time,
    and gemstones. The order must have status COMPLETED or DELIVERED.

    Returns the full invoice including all line items (Rechnungspositionen).
    """
    return await InvoiceService.create_invoice_from_order(db, invoice_in, current_user)


@router.get("/", response_model=InvoiceListResponse)
@require_permission(Permission.INVOICE_VIEW)
async def list_invoices(
    skip: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=50, ge=1, le=200, description="Page size (max 200)"),
    status_filter: Optional[InvoiceStatus] = Query(
        default=None,
        alias="status",
        description="Filter by invoice status (draft, sent, paid, overdue, cancelled)",
    ),
    customer_id: Optional[int] = Query(
        default=None, ge=1, description="Filter by customer ID"
    ),
    date_from: Optional[datetime] = Query(
        default=None, description="Filter invoices issued on or after this date (ISO 8601)"
    ),
    date_to: Optional[datetime] = Query(
        default=None, description="Filter invoices issued on or before this date (ISO 8601)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rechnungsliste (List invoices with optional filters).

    Supports filtering by status, customer, and date range.
    Results are sorted by issue_date descending (newest first).
    """
    items, total = await InvoiceService.list_invoices(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        status=status_filter,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
    )
    return InvoiceListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/export/datev")
@require_permission(Permission.INVOICE_VIEW)
async def export_invoices_datev(
    date_from: Optional[datetime] = Query(
        default=None,
        description="Filter invoices issued on or after this date (ISO 8601)",
    ),
    date_to: Optional[datetime] = Query(
        default=None,
        description="Filter invoices issued on or before this date (ISO 8601)",
    ),
    status_filter: Optional[InvoiceStatus] = Query(
        default=None,
        alias="status",
        description="Filter by invoice status",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    DATEV Buchungsstapel CSV-Export (ADMIN only).

    Exports invoices in DATEV format 510 (Buchungsstapel), ready for import
    into DATEV Unternehmen Online or DATEV Kanzlei-Rechnungswesen.

    Access is restricted to ADMIN role (financial data export).
    Each export call is audit-logged.

    Query parameters:
      date_from  - ISO 8601 datetime, filters by issue_date
      date_to    - ISO 8601 datetime, filters by issue_date
      status     - Invoice status filter (e.g. PAID, SENT)

    Returns a StreamingResponse with Content-Type text/csv and a
    Content-Disposition attachment header (datev_export_YYYYMMDD.csv).
    """
    if not current_user or current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="DATEV-Export ist nur für Administratoren verfügbar.",
        )

    logger.info(
        "Financial data export — DATEV",
        extra={
            "audit": True,
            "action": "export_datev",
            "user_id": current_user.id,
            "user_role": current_user.role.value,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "status_filter": status_filter.value if status_filter else None,
        },
    )

    invoices, _ = await InvoiceService.list_invoices(
        db=db,
        current_user=current_user,
        skip=0,
        limit=10_000,
        status=status_filter,
        customer_id=None,
        date_from=date_from,
        date_to=date_to,
    )

    invoice_ids = [inv.id for inv in invoices]
    if not invoice_ids:
        csv_content = export_datev_csv([])
    else:
        result = await db.execute(
            select(Invoice).where(Invoice.id.in_(invoice_ids))
        )
        orm_invoices = result.scalars().all()
        csv_content = export_datev_csv(list(orm_invoices))

    filename = f"datev_export_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(csv_content.encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/export/lexoffice")
@require_permission(Permission.INVOICE_VIEW)
async def export_invoices_lexoffice(
    date_from: Optional[datetime] = Query(
        default=None,
        description="Filter invoices issued on or after this date (ISO 8601)",
    ),
    date_to: Optional[datetime] = Query(
        default=None,
        description="Filter invoices issued on or before this date (ISO 8601)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lexoffice CSV-Export (ADMIN only).

    Exports invoices as a simplified CSV suitable for import into Lexoffice
    (Haufe lexware). Columns: Datum, Belegnummer, Beschreibung, Netto,
    MwSt-Satz, Brutto.

    Access is restricted to ADMIN role (financial data export).
    Each export call is audit-logged.

    Returns a StreamingResponse with Content-Type text/csv and a
    Content-Disposition attachment header (lexoffice_export_YYYYMMDD.csv).
    """
    if not current_user or current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lexoffice-Export ist nur für Administratoren verfügbar.",
        )

    logger.info(
        "Financial data export — Lexoffice",
        extra={
            "audit": True,
            "action": "export_lexoffice",
            "user_id": current_user.id,
            "user_role": current_user.role.value,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    )

    invoices, _ = await InvoiceService.list_invoices(
        db=db,
        current_user=current_user,
        skip=0,
        limit=10_000,
        status=None,
        customer_id=None,
        date_from=date_from,
        date_to=date_to,
    )

    invoice_ids = [inv.id for inv in invoices]
    if not invoice_ids:
        csv_content = export_lexoffice_csv([])
    else:
        result = await db.execute(
            select(Invoice).where(Invoice.id.in_(invoice_ids))
        )
        orm_invoices = result.scalars().all()
        csv_content = export_lexoffice_csv(list(orm_invoices))

    filename = f"lexoffice_export_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.BytesIO(csv_content.encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
@require_permission(Permission.INVOICE_VIEW)
async def get_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rechnung abrufen (Get a single invoice by ID).

    Returns the full invoice including all line items.
    """
    invoice = await InvoiceService.get_invoice(db, invoice_id, current_user)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rechnung {invoice_id} nicht gefunden",
        )
    return invoice


@router.put("/{invoice_id}", response_model=InvoiceResponse)
@require_permission(Permission.INVOICE_EDIT)
async def update_invoice(
    invoice_id: int,
    invoice_in: InvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rechnung aktualisieren (Update invoice status, due date, notes, or payment method).

    Invoice number, order_id, and customer_id are immutable.
    To mark as paid use the dedicated mark-paid endpoint.
    Cancelled invoices cannot be updated.
    """
    invoice = await InvoiceService.update_invoice(db, invoice_id, invoice_in, current_user)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rechnung {invoice_id} nicht gefunden",
        )
    return invoice


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceResponse)
@require_permission(Permission.INVOICE_EDIT)
async def mark_invoice_paid(
    invoice_id: int,
    request: MarkPaidRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rechnung als bezahlt markieren (Mark invoice as paid).

    Sets status to PAID and records the payment date.
    Optionally records the payment method (Zahlungsart).

    Only invoices in status DRAFT, SENT, or OVERDUE can be marked as paid.
    """
    invoice = await InvoiceService.mark_as_paid(db, invoice_id, request, current_user)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rechnung {invoice_id} nicht gefunden",
        )
    return invoice


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
@require_permission(Permission.INVOICE_DELETE)
async def cancel_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rechnung stornieren (Cancel/void an invoice).

    Sets status to CANCELLED. PAID invoices cannot be cancelled —
    a credit note process is required.

    Requires INVOICE_DELETE permission (ADMIN only).
    """
    invoice = await InvoiceService.cancel_invoice(db, invoice_id, current_user)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rechnung {invoice_id} nicht gefunden",
        )
    return invoice


@router.get("/{invoice_id}/pdf")
@require_permission(Permission.INVOICE_VIEW)
async def download_invoice_pdf(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rechnung als PDF herunterladen (Download invoice as PDF).

    Generates a German-format Rechnung PDF including all Rechnungspositionen,
    MwSt breakdown, and payment instructions.

    Restricted to ADMIN and GOLDSMITH roles (INVOICE_VIEW permission).
    Access is audit-logged by the service layer as financial data.

    Returns a streaming PDF response (application/pdf).
    """
    invoice = await InvoiceService.get_invoice(db, invoice_id, current_user)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rechnung {invoice_id} nicht gefunden",
        )

    # Load the associated customer — customer_id is stored on the invoice.
    customer_result = await db.execute(
        select(Customer).where(Customer.id == invoice.customer_id)
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kunde {invoice.customer_id} nicht gefunden",
        )

    # Build a thin adapter so PDFService sees a uniform .name, .address, .city
    # without depending on the ORM model's internal field names.
    class _CustomerAdapter:
        name: str
        address: str
        city: str
        email: str
        phone: str

        def __init__(self, c: Customer) -> None:
            self.name = f"{c.first_name} {c.last_name}".strip()
            parts = []
            if c.street:
                parts.append(c.street)
            self.address = ", ".join(parts)
            city_parts = []
            if c.postal_code:
                city_parts.append(c.postal_code)
            if c.city:
                city_parts.append(c.city)
            self.city = " ".join(city_parts)
            self.email = c.email or ""
            self.phone = c.phone or ""

    try:
        pdf_bytes = PDFService.render_invoice_pdf(
            invoice=invoice,
            customer=_CustomerAdapter(customer),
            line_items=invoice.line_items,
            workshop_name=settings.WORKSHOP_NAME,
        )
    except Exception:
        logger.exception(
            "PDF generation failed for invoice",
            extra={"invoice_id": invoice_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF-Generierung fehlgeschlagen. Bitte versuchen Sie es später erneut.",
        )

    filename = f"rechnung_{invoice.invoice_number}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
