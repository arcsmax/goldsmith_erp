# src/goldsmith_erp/api/routers/quotes.py
"""
Quote/estimate API router (Kostenvoranschlag).

All endpoints are restricted to ADMIN and GOLDSMITH roles.
Financial data access is audit-logged by the service layer.

Endpoints:
  POST   /api/v1/quotes                          - Create new quote
  GET    /api/v1/quotes                          - List quotes (with filters)
  GET    /api/v1/quotes/{quote_id}               - Get single quote
  PUT    /api/v1/quotes/{quote_id}               - Update quote fields
  POST   /api/v1/quotes/{quote_id}/send          - Mark as SENT
  POST   /api/v1/quotes/{quote_id}/approve       - Mark as APPROVED (+ signature)
  POST   /api/v1/quotes/{quote_id}/reject        - Mark as REJECTED
  POST   /api/v1/quotes/{quote_id}/convert       - Convert to order (CONVERTED)
  DELETE /api/v1/quotes/{quote_id}               - Delete DRAFT or REJECTED quote
  GET    /api/v1/quotes/{quote_id}/pdf           - Download quote as PDF
  POST   /api/v1/quotes/{quote_id}/line-items              - Add a line item (DRAFT only)
  PATCH  /api/v1/quotes/{quote_id}/line-items/{item_id}     - Update a line item (DRAFT only)
  DELETE /api/v1/quotes/{quote_id}/line-items/{item_id}     - Delete a line item (DRAFT only)

IMPORTANT: Static sub-paths (/export/*) must be registered BEFORE /{quote_id}
to avoid FastAPI treating string segments as integer path params. The
line-item routes below do not collide with /{quote_id}/pdf, /send,
/approve, /reject, or /convert — Starlette matches by literal segment text
and segment count, and every one of those sub-paths has a distinct literal
second segment ("pdf" vs "line-items") or segment count (2 vs 3 for
/line-items/{item_id}), so registration order does not matter here
(precedent/rationale: consultations.py module docstring, photo routes).
"""

import io
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import Customer, Quote, QuoteStatus, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.quote import (
    ApproveQuoteRequest,
    QuoteCreate,
    QuoteLineItemCreate,
    QuoteListResponse,
    QuoteResponse,
    QuoteUpdate,
    RejectQuoteRequest,
)
from goldsmith_erp.services.pdf_service import PDFService
from goldsmith_erp.services.quote_service import (
    QuoteNotEditableError,
    QuoteNotFoundError,
    QuoteService,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _raise_line_item_error(exc: ValueError) -> None:
    """
    Map a line-item service ValueError to 404 or 409 — typed dispatch via
    ``isinstance``, no string matching (pattern precedent:
    ``_raise_not_found_or_conflict`` in consultations.py).

    ``QuoteNotFoundError`` (and its ``QuoteLineItemNotFoundError`` subclass)
    -> 404; ``QuoteNotEditableError`` -> 409. Both raises use ``from None``
    so the original exception's chain (and any ``str(exc)`` FastAPI/logging
    might otherwise render from it) never leaks past the generic detail.
    """
    if isinstance(exc, QuoteNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from None
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None


# ─────────────────────────────────────────────────────────────────────────────
# Customer adapter — mirrors pattern in invoices.py
# ─────────────────────────────────────────────────────────────────────────────


class _CustomerAdapter:
    """Thin adapter so PDFService sees uniform .name/.address/.city/.email/.phone."""

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


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
@require_permission(Permission.QUOTE_CREATE)
async def create_quote(
    quote_in: QuoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Kostenvoranschlag erstellen (Create a new quote).

    When order_id is supplied the service auto-populates line items from the
    order's material costs, labor time, and gemstones. The order must belong
    to the same customer_id supplied in the request body.

    Returns the full quote including all line items (Angebotspositionen).
    """
    return await QuoteService.create_quote(db, quote_in, current_user)


@router.get("/", response_model=QuoteListResponse)
@require_permission(Permission.QUOTE_VIEW)
async def list_quotes(
    skip: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=50, ge=1, le=200, description="Page size (max 200)"),
    status_filter: Optional[QuoteStatus] = Query(
        default=None,
        alias="status",
        description="Filter by quote status (draft, sent, approved, rejected, expired, converted)",
    ),
    customer_id: Optional[int] = Query(
        default=None, ge=1, description="Filter by customer ID"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Angebotsliste (List quotes with optional filters).

    Supports filtering by status and customer.
    Results are sorted by created_at descending (newest first).
    """
    items, total = await QuoteService.list_quotes(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        status=status_filter,
        customer_id=customer_id,
    )
    return QuoteListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{quote_id}", response_model=QuoteResponse)
@require_permission(Permission.QUOTE_VIEW)
async def get_quote(
    quote_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Kostenvoranschlag abrufen (Get a single quote by ID).

    Returns the full quote including all line items.
    """
    quote = await QuoteService.get_quote(db, quote_id, current_user)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kostenvoranschlag {quote_id} nicht gefunden",
        )
    return quote


@router.put("/{quote_id}", response_model=QuoteResponse)
@require_permission(Permission.QUOTE_EDIT)
async def update_quote(
    quote_id: int,
    quote_in: QuoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Kostenvoranschlag aktualisieren (Update quote fields).

    Editable fields: status, valid_until, notes, tax_rate.
    Quote number, customer_id, and order_id are immutable.
    CONVERTED quotes cannot be updated.
    """
    quote = await QuoteService.update_quote(db, quote_id, quote_in, current_user)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kostenvoranschlag {quote_id} nicht gefunden",
        )
    return quote


@router.post("/{quote_id}/send", response_model=QuoteResponse)
@require_permission(Permission.QUOTE_EDIT)
async def send_quote(
    quote_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Angebot versenden (Mark quote as SENT).

    Only DRAFT quotes can be transitioned to SENT.
    """
    quote = await QuoteService.send_quote(db, quote_id, current_user)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kostenvoranschlag {quote_id} nicht gefunden",
        )
    return quote


@router.post("/{quote_id}/approve", response_model=QuoteResponse)
@require_permission(Permission.QUOTE_EDIT)
async def approve_quote(
    quote_id: int,
    request: ApproveQuoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Angebot genehmigen (Mark quote as APPROVED).

    Optionally stores the customer's digital signature (base64 PNG).
    Only SENT or DRAFT quotes can be approved.
    """
    quote = await QuoteService.approve_quote(db, quote_id, request, current_user)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kostenvoranschlag {quote_id} nicht gefunden",
        )
    return quote


@router.post("/{quote_id}/reject", response_model=QuoteResponse)
@require_permission(Permission.QUOTE_EDIT)
async def reject_quote(
    quote_id: int,
    request: RejectQuoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Angebot ablehnen (Mark quote as REJECTED).

    An optional rejection reason can be supplied and is appended to the notes.
    Only SENT or DRAFT quotes can be rejected.
    """
    quote = await QuoteService.reject_quote(
        db, quote_id, current_user, reason=request.reason
    )
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kostenvoranschlag {quote_id} nicht gefunden",
        )
    return quote


@router.post("/{quote_id}/convert", response_model=QuoteResponse)
@require_permission(Permission.QUOTE_EDIT)
async def convert_quote(
    quote_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Angebot in Auftrag umwandeln (Convert approved quote to an order).

    Creates a new confirmed Order from the quote data, links it, and marks
    the quote as CONVERTED. Only APPROVED quotes can be converted.
    """
    quote = await QuoteService.convert_quote(db, quote_id, current_user)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kostenvoranschlag {quote_id} nicht gefunden",
        )
    return quote


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permission(Permission.QUOTE_DELETE)
async def delete_quote(
    quote_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Kostenvoranschlag loeschen (Delete a DRAFT or REJECTED quote).

    SENT, APPROVED, and CONVERTED quotes cannot be deleted.
    Requires QUOTE_DELETE permission (ADMIN only).
    """
    deleted = await QuoteService.delete_quote(db, quote_id, current_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kostenvoranschlag {quote_id} nicht gefunden",
        )


@router.post(
    "/{quote_id}/line-items",
    response_model=QuoteResponse,
    status_code=status.HTTP_201_CREATED,
)
@require_permission(Permission.QUOTE_EDIT)
async def add_quote_line_item(
    quote_id: int,
    item_in: QuoteLineItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Angebotsposition hinzufuegen (Add a line item to a DRAFT quote).

    Only DRAFT quotes can be edited (a SENT/APPROVED/CONVERTED quote is
    legally relevant and stays immutable). subtotal/tax_amount/total are
    recomputed from ALL current line items and returned in the response.
    """
    try:
        return await QuoteService.add_line_item(db, quote_id, item_in, current_user)
    except ValueError as exc:
        _raise_line_item_error(exc)


@router.patch(
    "/{quote_id}/line-items/{item_id}",
    response_model=QuoteResponse,
)
@require_permission(Permission.QUOTE_EDIT)
async def update_quote_line_item(
    quote_id: int,
    item_id: int,
    item_in: QuoteLineItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Angebotsposition aktualisieren (Update a line item on a DRAFT quote).

    Only DRAFT quotes can be edited. subtotal/tax_amount/total are
    recomputed from ALL current line items and returned in the response.
    """
    try:
        return await QuoteService.update_line_item(
            db, quote_id, item_id, item_in, current_user
        )
    except ValueError as exc:
        _raise_line_item_error(exc)


@router.delete(
    "/{quote_id}/line-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@require_permission(Permission.QUOTE_EDIT)
async def delete_quote_line_item(
    quote_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Angebotsposition loeschen (Delete a line item from a DRAFT quote).

    Only DRAFT quotes can be edited. subtotal/tax_amount/total are
    recomputed from the remaining line items.
    """
    try:
        await QuoteService.delete_line_item(db, quote_id, item_id, current_user)
    except ValueError as exc:
        _raise_line_item_error(exc)


@router.get("/{quote_id}/pdf")
@require_permission(Permission.QUOTE_VIEW)
async def download_quote_pdf(
    quote_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Kostenvoranschlag als PDF herunterladen (Download quote as PDF).

    Generates a German-format Kostenvoranschlag PDF including all
    Angebotspositionen, MwSt breakdown, validity date, signature line,
    and legal disclaimer.

    Returns a streaming PDF response (application/pdf).
    """
    quote = await QuoteService.get_quote(db, quote_id, current_user)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kostenvoranschlag {quote_id} nicht gefunden",
        )

    # Load the associated customer
    customer_result = await db.execute(
        select(Customer).where(Customer.id == quote.customer_id)
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kunde {quote.customer_id} nicht gefunden",
        )

    try:
        pdf_bytes = PDFService.render_quote_pdf(
            quote=quote,
            customer=_CustomerAdapter(customer),
            line_items=quote.line_items,
            workshop_name=settings.WORKSHOP_NAME,
        )
    except Exception:
        logger.exception(
            "PDF generation failed for quote",
            extra={"quote_id": quote_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF-Generierung fehlgeschlagen. Bitte versuchen Sie es spaeter erneut.",
        )

    filename = f"kostenvoranschlag_{quote.quote_number}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
