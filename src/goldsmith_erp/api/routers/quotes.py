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
  POST   /api/v1/quotes/{quote_id}/send          - Send (email PDF or PDF_MANUAL)
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
from datetime import datetime
from typing import List, NoReturn, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import Customer, Quote, QuoteStatus, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.pagination import (
    Page,
    PageParams,
    legacy_list_response,
    make_page_params,
    page_response,
)
from goldsmith_erp.models.quote import (
    ApproveQuoteRequest,
    QuoteCreate,
    QuoteLineItemCreate,
    QuoteListItem,
    QuoteListResponse,
    QuoteResponse,
    QuoteUpdate,
    RejectQuoteRequest,
)
from goldsmith_erp.services import list_queries
from goldsmith_erp.services.quote_delivery import render_quote_pdf_bytes
from goldsmith_erp.services.quote_service import (
    QuoteNotEditableError,
    QuoteNotFoundError,
    QuoteService,
    _log_quote_access,
    _user_role_str,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _raise_quote_error(exc: ValueError) -> NoReturn:
    """
    Map a typed quote-service ValueError to 404 or 409 — typed dispatch via
    ``isinstance``, no string matching (pattern precedent:
    ``_raise_not_found_or_conflict`` in consultations.py). Shared by the
    line-item endpoints AND update_quote (the status-change / tax_rate
    guards both raise ``QuoteNotEditableError``).

    ``QuoteNotFoundError`` (and its ``QuoteLineItemNotFoundError`` subclass)
    -> 404; ``QuoteNotEditableError`` -> 409. Both raises use ``from None``
    so the original exception's chain (and any ``str(exc)`` FastAPI/logging
    might otherwise render from it) never leaks past the generic detail.
    ``NoReturn`` documents that this always raises — callers can treat the
    post-call state as unreachable.
    """
    if isinstance(exc, QuoteNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from None
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None


async def _with_delivery(db: AsyncSession, quote: Quote) -> QuoteResponse:
    """QuoteResponse plus how/when the quote reached the customer (DOM-11)."""
    response = QuoteResponse.model_validate(quote)
    delivery = await QuoteService.get_delivery(db, quote)
    if delivery is None:
        return response
    return response.model_copy(
        update={
            "delivery_method": delivery.delivery_method,
            "sent_at": delivery.sent_at,
        }
    )


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


@router.get(
    "/",
    # W3-08: Page[...] when ``offset`` is sent, the legacy envelope otherwise.
    response_model=Union[Page[QuoteListItem], QuoteListResponse],
)
@require_permission(Permission.QUOTE_VIEW)
async def list_quotes(
    page: PageParams = Depends(
        make_page_params(
            legacy_default_limit=50,
            legacy_max_limit=200,
            sort_fields=tuple(list_queries.QUOTE_SORT_FIELDS),
        )
    ),
    status_filter: Optional[QuoteStatus] = Query(
        default=None,
        alias="status",
        description="Filter by quote status (draft, sent, approved, rejected, expired, converted)",
    ),
    customer_id: Optional[int] = Query(
        default=None, ge=1, description="Filter by customer ID"
    ),
    created_from: Optional[datetime] = Query(
        default=None, description="Angelegt ab (nur mit offset)"
    ),
    created_to: Optional[datetime] = Query(
        default=None, description="Angelegt bis (nur mit offset)"
    ),
    q: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=100,
        description="Suche in KV-Nummer und Kundenname/E-Mail (nur mit offset)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Angebotsliste (List quotes with optional filters).

    Supports filtering by status and customer.
    Results are sorted by created_at descending (newest first).

    With ``offset``: a ``Page`` (``items, total, limit, offset,
    next_offset``) with date range and ``q`` search. Without it
    (deprecated, one release): the legacy ``{items, total, skip, limit}``
    envelope, flagged with ``X-Deprecated-List: true``.
    """
    if page.is_paged:
        return await _list_quotes_paged(
            db,
            current_user,
            page,
            status=status_filter,
            customer_id=customer_id,
            created_from=created_from,
            created_to=created_to,
            q=q,
        )
    items, total = await QuoteService.list_quotes(
        db=db,
        current_user=current_user,
        skip=page.offset,
        limit=page.limit,
        status=status_filter,
        customer_id=customer_id,
    )
    legacy = QuoteListResponse.model_validate(
        {"items": items, "total": total, "skip": page.offset, "limit": page.limit},
        from_attributes=True,
    )
    return legacy_list_response(legacy.model_dump())


async def _list_quotes_paged(
    db: AsyncSession,
    current_user: User,
    page: PageParams,
    *,
    status: Optional[QuoteStatus],
    customer_id: Optional[int],
    created_from: Optional[datetime],
    created_to: Optional[datetime],
    q: Optional[str],
):
    stmt = await list_queries.quotes_statement(
        db,
        status=status,
        customer_id=customer_id,
        created_from=created_from,
        created_to=created_to,
        q=q,
        sort=page.sort,
    )
    result = await list_queries.fetch_page(
        db, stmt, page, list_queries.QUOTE_LIST_OPTIONS
    )
    # Same financial-access audit line as QuoteService.list_quotes; the
    # search text is never logged (it may be a customer name).
    _log_quote_access(
        action="listed",
        quote_id=None,
        user_id=current_user.id,
        user_role=_user_role_str(current_user),
        extra={
            "filters": {
                "status": status,
                "customer_id": customer_id,
                "has_search": bool(q),
            },
            "result_count": len(result.items),
        },
    )
    rows = [QuoteListItem.model_validate(r).model_dump() for r in result.items]
    return page_response(rows, result.total, page)


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
    return await _with_delivery(db, quote)


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

    Editable fields: valid_until, notes, and — DRAFT only — tax_rate.
    Quote number, customer_id, and order_id are immutable. Status is NOT
    editable here: a status change goes through the dedicated
    send/approve/reject/convert actions (a status flip in the payload that
    differs from the current status → 409). tax_rate is DRAFT-only (→ 409 on
    a non-DRAFT quote). CONVERTED quotes cannot be updated at all (→ 422).
    """
    try:
        quote = await QuoteService.update_quote(db, quote_id, quote_in, current_user)
    except ValueError as exc:
        _raise_quote_error(exc)
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
    Angebot versenden (DOM-11).

    With SMTP configured and a customer email the quote PDF is emailed
    (delivery_method "email"); otherwise the hand-over is recorded as
    "pdf_manual" and the client downloads the PDF. Only DRAFT quotes can be
    sent (422). An SMTP failure returns 502 and the quote stays a DRAFT.
    """
    try:
        quote = await QuoteService.send_quote(db, quote_id, current_user)
    except QuoteNotFoundError as exc:
        _raise_quote_error(exc)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kostenvoranschlag {quote_id} nicht gefunden",
        )
    return await _with_delivery(db, quote)


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
        _raise_quote_error(exc)


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
        _raise_quote_error(exc)


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
        _raise_quote_error(exc)


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
        pdf_bytes = render_quote_pdf_bytes(quote, customer)
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
