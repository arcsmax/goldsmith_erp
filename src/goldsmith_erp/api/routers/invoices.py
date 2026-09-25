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
  PUT    /api/v1/invoices/{invoice_id}         - Update due date/notes (no status)
  POST   /api/v1/invoices/{invoice_id}/send        - Mark DRAFT as sent
  POST   /api/v1/invoices/{invoice_id}/mark-paid   - Mark as paid
  POST   /api/v1/invoices/{invoice_id}/cancel      - Cancel (DRAFT: void;
                                                   SENT/OVERDUE: Storno)
  POST   /api/v1/invoices/{invoice_id}/storno      - Stornorechnung (W2-04)
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
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import Invoice, InvoiceStatus, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.invoice import (
    InvoiceCreate,
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceUpdate,
    MarkPaidRequest,
    StornoRequest,
)
from goldsmith_erp.services.accounting_export_service import (
    AccountingExportError,
    export_datev_csv,
    export_lexoffice_csv,
)
from goldsmith_erp.services.invoice_service import InvoiceService
from goldsmith_erp.services.invoice_snapshot_service import InvoiceSnapshotService

logger = logging.getLogger(__name__)

router = APIRouter()

# Invoice statuses treated as "issued" (a legal document exists) for the
# accounting export — booked as normal revenue. See BE-13 /
# accounting_export_service.py module docstring for the CANCELLED handling.
_ISSUED_INVOICE_STATUSES = (
    InvoiceStatus.SENT,
    InvoiceStatus.PAID,
    InvoiceStatus.OVERDUE,
)


def _partition_invoices_for_accounting_export(
    invoices: List[Invoice],
) -> tuple[List[Invoice], List[Invoice]]:
    """Split invoices into (issued, cancelled) for the accounting export.

    Issued invoices (SENT/PAID/OVERDUE) get a normal revenue booking.
    CANCELLED invoices get a Storno reversal booking. DRAFT invoices are
    excluded entirely — no legal document was ever issued, so there is
    nothing to book or reverse (BE-13).

    W2-04: a Stornorechnung (``cancels_invoice_id`` set) is not booked as
    revenue; the cancelled original's reversal row already books it, so
    including it would reverse the sale twice.
    """
    issued = [
        inv
        for inv in invoices
        if inv.status in _ISSUED_INVOICE_STATUSES
        and getattr(inv, "cancels_invoice_id", None) is None
    ]
    cancelled = [inv for inv in invoices if inv.status == InvoiceStatus.CANCELLED]
    return issued, cancelled


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

    Only issued invoices (SENT/PAID/OVERDUE) are booked as revenue;
    CANCELLED invoices produce a Storno reversal booking instead of being
    silently omitted, and the revenue account is chosen per the invoice's
    VAT rate (BE-13, W1-09 — see accounting_export_service.py docstring).

    Access is restricted to ADMIN role (financial data export).
    Each export call is audit-logged.

    Query parameters:
      date_from  - ISO 8601 datetime, filters by issue_date
      date_to    - ISO 8601 datetime, filters by issue_date
      status     - Invoice status filter (e.g. PAID, SENT); unset exports
                   every issued/cancelled invoice in the date range

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
    issued_invoices, cancelled_invoices = _partition_invoices_for_accounting_export(
        invoices
    )

    try:
        csv_content = export_datev_csv(
            issued_invoices, reversal_invoices=cancelled_invoices
        )
    except AccountingExportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

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

    Only issued invoices (SENT/PAID/OVERDUE) are booked as revenue;
    CANCELLED invoices produce a negative Storno row instead of being
    silently omitted (BE-13, W1-09 — see accounting_export_service.py
    docstring).

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
    issued_invoices, cancelled_invoices = _partition_invoices_for_accounting_export(
        invoices
    )

    csv_content = export_lexoffice_csv(
        issued_invoices, reversal_invoices=cancelled_invoices
    )

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
    Rechnung aktualisieren (Update due date, notes, or payment method).

    Invoice number, order_id, customer_id and status are not editable here.
    Status changes go through /send, /mark-paid and /cancel (BE-05), each
    with its own permission. PAID or CANCELLED invoices return 409.
    """
    invoice = await InvoiceService.update_invoice(
        db, invoice_id, invoice_in, current_user
    )
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rechnung {invoice_id} nicht gefunden",
        )
    return invoice


@router.post("/{invoice_id}/send", response_model=InvoiceResponse)
@require_permission(Permission.INVOICE_EDIT)
async def send_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rechnung als versendet markieren (Mark a DRAFT invoice as SENT).

    Only DRAFT invoices can be sent; any other status returns 409.
    """
    invoice = await InvoiceService.mark_as_sent(db, invoice_id, current_user)
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
    Rechnung stornieren (Cancel an invoice).

    DRAFT: voided (status CANCELLED, no document was issued). SENT/OVERDUE:
    a Stornorechnung is emitted (W2-04); the response is the original with
    ``cancelled_by_invoice_id``. PAID: 422, use ``POST /{id}/storno``.

    Requires INVOICE_DELETE permission (ADMIN only).
    """
    invoice = await InvoiceService.cancel_invoice(db, invoice_id, current_user)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rechnung {invoice_id} nicht gefunden",
        )
    return invoice


@router.post(
    "/{invoice_id}/storno",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
@require_permission(Permission.INVOICE_DELETE)
async def create_storno_invoice(
    invoice_id: int,
    request: Optional[StornoRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stornorechnung erstellen (W2-04, DOM-24b).

    Reverses an issued invoice (SENT, OVERDUE or PAID) with a negative
    invoice that has its own number and links to the original; the
    original is not edited, only set to CANCELLED. Returns the Storno.

    Requires INVOICE_DELETE permission (ADMIN only).
    """
    storno = await InvoiceService.create_storno(
        db, invoice_id, request or StornoRequest(reason=None), current_user
    )
    if not storno:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rechnung {invoice_id} nicht gefunden",
        )
    return storno


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

    W1-10 (GDPR-01, BE-23): rendered from the invoice snapshot, never from
    the live customer row. DRAFT is re-rendered per request; SENT, PAID,
    OVERDUE and CANCELLED invoices serve the PDF frozen at issue time after
    a SHA-256 integrity check.
    """
    invoice = await InvoiceService.get_invoice(db, invoice_id, current_user)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rechnung {invoice_id} nicht gefunden",
        )

    try:
        pdf_bytes = await InvoiceSnapshotService.pdf_for_download(db, invoice)
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
