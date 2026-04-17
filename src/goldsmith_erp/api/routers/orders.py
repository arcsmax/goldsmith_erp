# src/goldsmith_erp/api/routers/orders.py
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional
from datetime import datetime

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User
from goldsmith_erp.models.order import OrderCreate, OrderRead, OrderUpdate, LocationChangeRequest, LocationHistoryRead
from goldsmith_erp.services.order_service import OrderService
from goldsmith_erp.services.cost_calculation_service import CostCalculationService
from goldsmith_erp.services.label_service import LabelService
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, require_permission

router = APIRouter()

@router.get("/", response_model=List[OrderRead])
@require_permission(Permission.ORDER_VIEW)
async def list_orders(
    skip: int = 0,
    limit: int = 100,
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Liste aller Aufträge."""
    return await OrderService.get_orders(db, skip, limit, customer_id=customer_id)


@router.get("/calendar/deadlines")
@require_permission(Permission.ORDER_VIEW)
async def get_calendar_deadlines(
    start: Optional[str] = Query(None, description="Start date (ISO format)"),
    end: Optional[str] = Query(None, description="End date (ISO format)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Auftraege mit Deadlines fuer Kalender-Ansicht mit Ampel-Status."""
    try:
        orders = await OrderService.get_orders_with_deadlines(db, start, end)
    except ValueError:
        raise HTTPException(status_code=422, detail="Ungültiges Datumsformat. ISO-Format erwartet.")
    now = datetime.utcnow()
    result = []
    for order in orders:
        if not order.deadline:
            continue
        days_until = (order.deadline - now).days
        if order.status in ("completed", "delivered"):
            traffic_light = "grey"
        elif days_until < 2:
            traffic_light = "red"
        elif days_until <= 5:
            traffic_light = "yellow"
        else:
            traffic_light = "green"

        result.append({
            "id": order.id,
            "title": order.title,
            "status": order.status.value if hasattr(order.status, 'value') else order.status,
            "deadline": order.deadline.isoformat(),
            "customer_name": f"{order.customer.first_name} {order.customer.last_name}" if order.customer else None,
            "traffic_light": traffic_light,
            "days_until_deadline": days_until,
        })
    return result


@router.post("/", response_model=OrderRead)
@require_permission(Permission.ORDER_CREATE)
async def create_order(
    order_in: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Neuen Auftrag erstellen."""
    return await OrderService.create_order(db, order_in)

@router.get("/{order_id}", response_model=OrderRead)
@require_permission(Permission.ORDER_VIEW)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Einzelnen Auftrag abrufen."""
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.put("/{order_id}", response_model=OrderRead)
@require_permission(Permission.ORDER_EDIT)
async def update_order(
    order_id: int,
    order_in: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
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

@router.post("/{order_id}/location", response_model=OrderRead)
@require_permission(Permission.ORDER_EDIT)
async def change_order_location(
    order_id: int,
    location_in: LocationChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lagerort eines Auftrags ändern und Verlaufseintrag anlegen."""
    order = await OrderService.change_location(
        db, order_id, location_in.location, current_user.id
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/{order_id}/location-history", response_model=List[LocationHistoryRead])
@require_permission(Permission.ORDER_VIEW)
async def get_order_location_history(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Vorkalkulation: Kosten fuer einen Auftrag berechnen und gespeicherte Felder aktualisieren."""
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        breakdown = await CostCalculationService.calculate_order_cost(db, order_id)
        await CostCalculationService.update_order_calculated_price(db, order_id, breakdown)
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


@router.delete("/{order_id}")
@require_permission(Permission.ORDER_DELETE)
async def delete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Auftrag löschen."""
    order = await OrderService.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return await OrderService.delete_order(db, order_id)