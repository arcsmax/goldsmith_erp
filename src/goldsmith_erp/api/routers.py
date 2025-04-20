from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.order import OrderCreate, OrderRead, OrderUpdate
from goldsmith_erp.services.order_service import OrderService

router = APIRouter(tags=["orders"])

@router.post(
    "/orders",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    """Create a new order."""
    return await OrderService.create_order(payload, db)  # implement in service

@router.get(
    "/orders/{order_id}",
    response_model=OrderRead,
)
async def read_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    """Get an order by ID."""
    order = await OrderService.get_order(order_id, db)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.put(
    "/orders/{order_id}",
    response_model=OrderRead,
)
async def update_order(
    order_id: int,
    payload: OrderUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrderRead:
    """Update an existing order."""
    updated = await OrderService.update_order(order_id, payload, db)
    if not updated:
        raise HTTPException(status_code=404, detail="Order not found")
    return updated

@router.delete(
    "/orders/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an order."""
    success = await OrderService.delete_order(order_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Order not found")