# src/goldsmith_erp/api/routers/orders.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User
from goldsmith_erp.models.order import OrderCreate, OrderRead, OrderUpdate
from goldsmith_erp.services.order_service import OrderService
from goldsmith_erp.core.permissions import Permission, require_permission

router = APIRouter()

@router.get("/", response_model=List[OrderRead])
@require_permission(Permission.ORDER_VIEW)
async def list_orders(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Liste aller Aufträge."""
    return await OrderService.get_orders(db, skip, limit)


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
    return await OrderService.update_order(db, order_id, order_in)

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