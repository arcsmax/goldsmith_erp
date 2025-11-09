# src/goldsmith_erp/api/routers/orders.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

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