# src/goldsmith_erp/api/routers/invoices.py
"""
Invoice/billing API router (Rechnungswesen).

All endpoints are restricted to ADMIN and GOLDSMITH roles.
Financial data access is audit-logged by the service layer.

Endpoints:
  POST   /api/v1/invoices                  - Create invoice from order
  GET    /api/v1/invoices                  - List invoices (with filters)
  GET    /api/v1/invoices/{invoice_id}     - Get single invoice
  PUT    /api/v1/invoices/{invoice_id}     - Update invoice status/notes
  POST   /api/v1/invoices/{invoice_id}/mark-paid   - Mark as paid
  POST   /api/v1/invoices/{invoice_id}/cancel      - Cancel invoice
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User, InvoiceStatus
from goldsmith_erp.models.invoice import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    InvoiceListResponse,
    MarkPaidRequest,
)
from goldsmith_erp.services.invoice_service import InvoiceService
from goldsmith_erp.core.permissions import Permission, require_permission

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
