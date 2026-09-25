# src/goldsmith_erp/api/routers/orders.py
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.api.role_projection import (
    ExcludeSpec,
    build_excludes,
    can_view_design,
    can_view_financial,
)
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import OrderPhoto, OrderStatusEnum, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.order import (
    LocationChangeRequest,
    LocationHistoryRead,
    OrderCreate,
    OrderListRead,
    OrderRead,
    OrderStatusChange,
    OrderTimelineRead,
    OrderUpdate,
)
from goldsmith_erp.models.pagination import (
    Page,
    PageParams,
    legacy_list_response,
    make_page_params,
    page_response,
)
from goldsmith_erp.services import list_queries
from goldsmith_erp.services.cost_calculation_service import CostCalculationService
from goldsmith_erp.services.customer_update_service import write_financial_audit_row
from goldsmith_erp.services.handover_service import build_handover_data, can_hand_over
from goldsmith_erp.services.label_service import LabelService
from goldsmith_erp.services.order_service import OrderService
from goldsmith_erp.services.order_timeline import build_order_timeline
from goldsmith_erp.services.order_workflow import counts_for_deadline
from goldsmith_erp.services.status_report_service import (
    StatusReportNotFoundError,
    render_order_status_report_pdf,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ── C5: VIEWER-role financial-field projection ───────────────────────────────
# CLAUDE.md "Data Privacy Rules → Financial Data":
#   Pricing, payment info, material costs → visible only to ADMIN and GOLDSMITH
#
# Every GET handler that returns an OrderRead (single or list) routes through
# ``_project_order_for_user`` / ``_project_order_rows`` so VIEWERs never
# receive these seven fields. The scanner service already had the allow-list
# pattern (scanner_service.ORDER_FIELDS_BY_ROLE); this brings the REST API in
# line.
#
# Exhaustiveness: any future financial column added to OrderRead MUST also be
# added to ``_FINANCIAL_FIELDS`` below. The companion test
# ``tests/integration/test_order_viewer_projection.py`` pins the exact behavior.
#
# Ref: docs/fix-plan/2026-04-23/C5-viewer-financial-projection.md
_FINANCIAL_FIELDS: frozenset[str] = frozenset(
    {
        "price",
        "material_cost_calculated",
        "material_cost_override",
        "labor_cost",
        "hourly_rate",
        "profit_margin_percent",
        "calculated_price",
    }
)


# SEC-09 / GDPR-04: design IP. CLAUDE.md: "Design descriptions in orders are
# business-confidential" and design data is GOLDSMITH/ADMIN only.
_DESIGN_FIELDS: frozenset[str] = frozenset({"description", "special_instructions"})

# GDPR-03: ``OrderRead.materials[]`` carries each material's ``unit_price``,
# which bypassed the seven top-level fields above.
_NESTED_FINANCIAL_FIELDS: dict[str, frozenset[str]] = {
    "materials": frozenset({"unit_price"}),
}


def _order_excludes_for_user(user: User) -> ExcludeSpec:
    """Return the pydantic exclude spec for the caller.

    FINANCIAL_VIEW holders (ADMIN, GOLDSMITH) keep the seven financial fields
    and nested material prices; DESIGN_VIEW holders (ADMIN, GOLDSMITH) keep
    ``description`` / ``special_instructions``. Everyone else (VIEWER and any
    future read-only role) gets them stripped. ADMIN/GOLDSMITH therefore see
    the unredacted response exactly as before (empty spec).
    """
    return build_excludes(
        user,
        financial=_FINANCIAL_FIELDS,
        design=_DESIGN_FIELDS,
        nested_financial=_NESTED_FINANCIAL_FIELDS,
    )


def _project_order_for_user(order, user: User) -> JSONResponse:
    """Serialize a single ORM Order into a role-aware JSON response."""
    excludes = _order_excludes_for_user(user)
    data = OrderRead.model_validate(order).model_dump(exclude=excludes or None)
    return JSONResponse(content=jsonable_encoder(data))


async def _first_photo_ids(db: AsyncSession, order_ids: List[int]) -> Dict[int, str]:
    """Map order id -> id of its oldest photo, in one query (no N+1).

    W2-01 / FE-13: lets the orders list show a thumbnail through
    ``/photos/{id}/thumbnail``. Ties on ``timestamp`` resolve to the
    smallest photo id so the result is deterministic.
    """
    if not order_ids:
        return {}
    oldest = (
        select(
            OrderPhoto.order_id.label("order_id"),
            func.min(OrderPhoto.timestamp).label("first_ts"),
        )
        .where(OrderPhoto.order_id.in_(order_ids))
        .group_by(OrderPhoto.order_id)
        .subquery()
    )
    rows = await db.execute(
        select(OrderPhoto.order_id, func.min(OrderPhoto.id))
        .join(
            oldest,
            (OrderPhoto.order_id == oldest.c.order_id)
            & (OrderPhoto.timestamp == oldest.c.first_ts),
        )
        .group_by(OrderPhoto.order_id)
    )
    return {int(order_id): str(photo_id) for order_id, photo_id in rows.all()}


def _project_order_rows(
    orders: Any,
    user: User,
    first_photo_ids: Optional[Dict[int, str]] = None,
) -> List[Dict[str, Any]]:
    """Role-aware list rows for ORM Orders.

    ``first_photo_id`` is design IP (DESIGN_VIEW): it is only filled for
    callers that may see photos; everyone else gets ``None`` (W2-01).
    """
    excludes = _order_excludes_for_user(user) or None
    photo_ids = first_photo_ids if can_view_design(user) else None
    data = []
    for order in orders:
        row = OrderListRead.model_validate(order).model_dump(exclude=excludes)
        row["first_photo_id"] = (photo_ids or {}).get(order.id)
        data.append(row)
    return data


@router.get(
    "/",
    # W3-08: Page[...] when ``offset`` is sent, the legacy list otherwise.
    response_model=Union[Page[OrderListRead], List[OrderListRead]],
    # C5: VIEWER responses strip financial fields — the actual projection
    # happens in _project_order_rows. ``response_model`` still documents
    # the maximal shape for ADMIN/GOLDSMITH in the OpenAPI schema.
    response_model_exclude_none=False,
)
@require_permission(Permission.ORDER_VIEW)
async def list_orders(
    page: PageParams = Depends(
        make_page_params(
            legacy_default_limit=100,
            sort_fields=tuple(list_queries.ORDER_SORT_FIELDS),
        )
    ),
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    status: Optional[OrderStatusEnum] = Query(
        None, description="Nach Status filtern (nur mit offset)"
    ),
    created_from: Optional[datetime] = Query(
        None, description="Angelegt ab (nur mit offset)"
    ),
    created_to: Optional[datetime] = Query(
        None, description="Angelegt bis (nur mit offset)"
    ),
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=100,
        description="Suche in Nummer, Titel, Kundenname/E-Mail (nur mit offset)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste aller Aufträge.

    With ``offset``: a ``Page`` with server-side filters and search. Without
    it (deprecated, one release): the legacy plain list, flagged with
    ``X-Deprecated-List: true``; only ``customer_id`` filters there.

    VIEWER-role callers receive the list WITHOUT the seven financial fields
    (``price``, ``material_cost_*``, ``labor_cost``, ``hourly_rate``,
    ``profit_margin_percent``, ``calculated_price``). See C5 fix-plan.
    """
    total = 0
    if page.is_paged:
        stmt = await list_queries.orders_statement(
            db,
            status=status,
            customer_id=customer_id,
            created_from=created_from,
            created_to=created_to,
            q=q,
            sort=page.sort,
        )
        result = await list_queries.fetch_page(
            db, stmt, page, list_queries.ORDER_LIST_OPTIONS
        )
        orders, total = result.items, result.total
    else:
        orders = await OrderService.get_orders(
            db, page.offset, page.limit, customer_id=customer_id
        )
    # Finding 2.2: the seven financial fields (price / hourly_rate / margins /
    # calculated_price / material+labor cost) ride on OrderRead and are served
    # to ADMIN/GOLDSMITH here. CLAUDE.md requires every financial-data access to
    # be audit-logged. The AuditLoggingMiddleware cannot cover this: ``/orders``
    # is deliberately NOT a registered family — a blanket "orders" entry would
    # audit every unrelated order fetch app-wide (calendar/label/location-history
    # serialize NO financial field, and VIEWER reads have the fields stripped),
    # drowning the financial_read stream. So we write the row at the service
    # layer, but ONLY when the response actually carries the fields — i.e. for
    # financial roles. VIEWERs get them stripped (C5), so their read exposes no
    # financial data and needs no row. Safe to commit mid-handler: get_db's
    # session factory uses expire_on_commit=False (see scrap_gold precedent).
    if can_view_financial(current_user):
        await write_financial_audit_row(
            db,
            action="list_accessed_financial",
            entity="order",
            entity_id=None,
            order_id=None,
            user_id=current_user.id,
            endpoint="/api/v1/orders/",
        )
    # W2-01: the photo lookup is skipped entirely for callers without
    # DESIGN_VIEW — they always receive ``first_photo_id: null``.
    first_photo_ids = (
        await _first_photo_ids(db, [o.id for o in orders])
        if can_view_design(current_user)
        else None
    )
    rows = _project_order_rows(orders, current_user, first_photo_ids)
    if page.is_paged:
        return page_response(rows, total, page)
    return legacy_list_response(rows)


@router.get("/calendar/deadlines")
@require_permission(Permission.ORDER_VIEW)
async def get_calendar_deadlines(
    start: Optional[str] = Query(None, description="Start date (ISO format)"),
    end: Optional[str] = Query(None, description="End date (ISO format)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auftraege mit Deadlines fuer Kalender-Ansicht mit Ampel-Status."""
    try:
        orders = await OrderService.get_orders_with_deadlines(db, start, end)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Ungültiges Datumsformat. ISO-Format erwartet."
        )
    now = datetime.now(timezone.utc)
    result = []
    for order in orders:
        if not order.deadline:
            continue
        days_until = (order.deadline - now).days
        # W2-07: finished, paused (on_hold) and cancelled orders raise no
        # deadline alarm.
        if not counts_for_deadline(order.status):
            traffic_light = "grey"
        elif days_until < 2:
            traffic_light = "red"
        elif days_until <= 5:
            traffic_light = "yellow"
        else:
            traffic_light = "green"

        result.append(
            {
                "id": order.id,
                "title": order.title,
                "status": (
                    order.status.value
                    if hasattr(order.status, "value")
                    else order.status
                ),
                "deadline": order.deadline.isoformat(),
                "customer_name": (
                    f"{order.customer.first_name} {order.customer.last_name}"
                    if order.customer
                    else None
                ),
                "traffic_light": traffic_light,
                "days_until_deadline": days_until,
            }
        )
    return result


@router.post("/", response_model=OrderRead)
@require_permission(Permission.ORDER_CREATE)
async def create_order(
    order_in: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Neuen Auftrag erstellen."""
    return await OrderService.create_order(db, order_in, user_id=current_user.id)


@router.get("/{order_id}", response_model=OrderRead)
@require_permission(Permission.ORDER_VIEW)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Einzelnen Auftrag abrufen.

    VIEWER-role callers receive the order WITHOUT financial fields. See C5.
    """
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    # Finding 2.2: audit the financial-field-bearing read (see list_orders for
    # the full rationale). Only ADMIN/GOLDSMITH receive the seven financial
    # fields; VIEWER reads are stripped (C5) and need no financial_read row.
    if can_view_financial(current_user):
        await write_financial_audit_row(
            db,
            action="financial_read",
            entity="order",
            entity_id=order_id,
            order_id=order_id,
            user_id=current_user.id,
            endpoint=f"/api/v1/orders/{order_id}",
        )
    return _project_order_for_user(order, current_user)


@router.put("/{order_id}", response_model=OrderRead)
@require_permission(Permission.ORDER_EDIT)
async def update_order(
    order_id: int,
    order_in: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auftrag aktualisieren."""
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        return await OrderService.update_order(
            db,
            order_id,
            order_in,
            verified_by_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/{order_id}", response_model=OrderRead)
@require_permission(Permission.ORDER_EDIT)
async def patch_order(
    order_id: int,
    order_in: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auftrag (teil-)aktualisieren.

    Slice 5 addition — PunzierungsCheckModal hits this endpoint to write
    ``punzierung_verified_at`` + ``punzierung_verified_marks`` without
    the separate /punzierung-verify endpoint that Maria descoped from
    V1.1. Functionally equivalent to PUT today; the PATCH verb matches
    REST conventions for partial updates and keeps the door open for
    future divergence.
    """
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        return await OrderService.update_order(
            db,
            order_id,
            order_in,
            verified_by_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/{order_id}/status", response_model=OrderRead)
@require_permission(Permission.ORDER_EDIT)
async def change_order_status(
    order_id: int,
    change: OrderStatusChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Status wechseln (W2-07).

    Validated by the transition table in ``services/order_workflow.py``:
    409 ``INVALID_STATUS_TRANSITION`` with a German message and the allowed
    next statuses, 422 when ``on_hold`` / ``cancelled`` have no ``reason``.

    Advancing an alloyed order to COMPLETED is soft-gated (D-10,
    ``order_workflow.PunzierungRequiredError``): 409 with top-level
    ``code == "order.hallmark_required"`` (``legacy_detail.code`` keeps the
    older ``PUNZIERUNG_REQUIRED`` string for callers written against the
    hard-gate era) unless the order already has, or this request records, a
    real Feingehalt mark for its alloy OR a documented
    ``"nicht punziert: <Grund>"`` reason (see
    ``services/hallmark_vocabulary.satisfies_hallmark_requirement`` —
    hallmarking is voluntary under German law, but the decision not to must
    be on record). The status change and its ``order_events`` row are
    committed together.
    """
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        updated = await OrderService.update_order(
            db,
            order_id,
            OrderUpdate.model_validate(
                {
                    "status": change.status,
                    "status_reason": change.reason,
                    "resume_date": change.resume_date,
                }
            ),
            verified_by_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _project_order_for_user(updated, current_user)


@router.get("/{order_id}/timeline", response_model=OrderTimelineRead)
@require_permission(Permission.ORDER_VIEW)
async def get_order_timeline(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderTimelineRead:
    """Verlauf eines Auftrags (W2-07, ARCH-01).

    Status events, Kundeninfos, photos and time entries merged ascending by
    time. No prices or customer free text for anyone; photos only with
    DESIGN_VIEW; the amount-bearing subject of a cost-change update only
    with FINANCIAL_VIEW (that read is audit-logged).
    """
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    financial = can_view_financial(current_user)
    timeline = await build_order_timeline(
        db, order_id, financial=financial, design=can_view_design(current_user)
    )
    if financial and any(
        item.data.get("kind") == "cost_change" for item in timeline.items
    ):
        await write_financial_audit_row(
            db,
            action="timeline_accessed_financial",
            entity="order",
            entity_id=order_id,
            order_id=order_id,
            user_id=current_user.id,
            endpoint=f"/api/v1/orders/{order_id}/timeline",
        )
    return timeline


@router.get("/{order_id}/status-report.pdf", response_class=Response)
@require_permission(Permission.CUSTOMER_UPDATE_SEND)
async def get_order_status_report(
    order_id: int,
    next_steps: Optional[str] = Query(None, max_length=2000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Statusbericht (Kundenbericht) als PDF (W6, DOM section D Option 2).

    Werkstatt-Kopf, Schmuckstueck (Titel, Material, Steine), Verlauf aus
    Status-Ereignissen und tatsaechlich verschickten Kundeninfos, die
    zuletzt mit der Kundin/dem Kunden geteilten Fotos, ein "Wie geht es
    weiter"-Text und die Kontaktzeile. Nie Preise, Kosten, interne Notizen
    oder Mitarbeiternamen (CLAUDE.md). GOLDSMITH/ADMIN only (VIEWER: 403);
    jeder Abruf wird protokolliert.
    """
    try:
        pdf_bytes = await render_order_status_report_pdf(
            db, order_id, next_steps=next_steps
        )
    except StatusReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    logger.info(
        "Status report PDF served",
        extra={
            "audit": True,
            "action": "order_status_report_pdf",
            "order_id": order_id,
            "user_id": current_user.id,
        },
    )
    filename = f"Statusbericht_Auftrag_{order_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/{order_id}/location", response_model=OrderRead)
@require_permission(Permission.ORDER_EDIT)
async def change_order_location(
    order_id: int,
    location_in: LocationChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lagerort eines Auftrags ändern und Verlaufseintrag anlegen."""
    order = await OrderService.change_location(
        db,
        order_id,
        location_in.location,
        current_user.id,
        location_id=location_in.location_id,
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/{order_id}/location-history", response_model=List[LocationHistoryRead])
@require_permission(Permission.ORDER_VIEW)
async def get_order_location_history(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lagerort-Verlauf eines Auftrags abrufen."""
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return await OrderService.get_location_history(db, order_id)


@router.post("/{order_id}/calculate-cost")
@require_permission(Permission.ORDER_EDIT)
async def calculate_order_cost(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Vorkalkulation: Kosten fuer einen Auftrag berechnen und gespeicherte Felder aktualisieren."""
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        breakdown = await CostCalculationService.calculate_order_cost(db, order_id)
        await CostCalculationService.update_order_calculated_price(
            db, order_id, breakdown
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    result = breakdown.to_dict()
    result["order_id"] = order_id
    return result


@router.get("/{order_id}/label", response_class=HTMLResponse)
@require_permission(Permission.ORDER_VIEW)
async def get_order_label(
    order_id: int,
    width_mm: int = Query(89, ge=50, le=210, description="Label width in mm"),
    height_mm: int = Query(36, ge=20, le=297, description="Label height in mm"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Druckbares HTML-Etikett mit QR-Code fuer einen Auftrag.

    Returns a self-contained HTML document sized for label paper
    (default 89x36mm).  The page auto-triggers the browser print
    dialog on load.

    QR payload: ``ORDER:<id>`` — decoded by ScannerPage.
    """
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    workshop_name = getattr(settings, "APP_NAME", "Goldschmiede")
    html = LabelService.generate_order_label_html(
        order=order,
        customer=order.customer,
        workshop_name=workshop_name,
        label_width_mm=width_mm,
        label_height_mm=height_mm,
    )
    return HTMLResponse(content=html, status_code=200)


@router.get("/{order_id}/handover-pdf", response_class=Response)
@require_permission(Permission.DESIGN_VIEW)
async def get_handover_pdf(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Abholprotokoll als PDF (W2-11, DOM-35).

    Foto, Metall, Steine (ohne Einkaufspreis), Material, Pflegehinweise,
    Gewährleistung und Unterschriftszeilen. Nur für fertiggestellte oder
    ausgelieferte Aufträge; Design-Daten, daher DESIGN_VIEW.
    """
    from goldsmith_erp.services.pdf_service import PDFService  # noqa: PLC0415
    from goldsmith_erp.services.workshop_settings_service import (  # noqa: PLC0415
        WorkshopSettingsService,
    )

    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if not can_hand_over(order):
        raise HTTPException(
            status_code=409,
            detail=(
                "Das Abholprotokoll gibt es erst für fertiggestellte oder "
                "ausgelieferte Aufträge."
            ),
        )
    data = await build_handover_data(db, order)
    workshop = await WorkshopSettingsService.read(db)
    try:
        content = PDFService.render_handover_pdf(
            data, workshop.name, workshop.care_text
        )
    except Exception:
        logger.exception("Handover PDF generation failed", extra={"order_id": order_id})
        raise HTTPException(
            status_code=500,
            detail="PDF-Generierung fehlgeschlagen. Bitte später erneut versuchen.",
        )
    logger.info(
        "Handover PDF generated",
        extra={"order_id": order_id, "user_id": current_user.id},
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="abholprotokoll_{order_id}.pdf"'
        },
    )


@router.delete("/{order_id}")
@require_permission(Permission.ORDER_DELETE)
async def delete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auftrag löschen."""
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return await OrderService.delete_order(db, order_id)
