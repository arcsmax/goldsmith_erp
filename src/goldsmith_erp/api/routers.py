from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.order import OrderCreate, OrderRead, OrderUpdate
from goldsmith_erp.services.order_service import OrderService
from goldsmith_erp.api.deps import get_current_user  # Import dependency
from goldsmith_erp.db.models import User  # Import User model for type hint

router = APIRouter(tags=["orders"])

@router.post(
    "/orders",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)  # Added authentication
) -> OrderRead:
    """Create a new order."""
    # Now you can potentially associate the order with the current user if needed
    # payload.customer_id = current_user.id  # Example
    return await OrderService.create_order(payload, db)

@router.get(
    "/orders/{order_id}",
    response_model=OrderRead,
)
async def read_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)  # Already added
) -> OrderRead:
    """Get an order by ID."""
    # Now you can potentially use current_user for authorization checks if needed
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
    current_user: User = Depends(get_current_user)  # Already added
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
    current_user: User = Depends(get_current_user)  # Already added
) -> None:
    """Delete an order."""
    success = await OrderService.delete_order(order_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Order not found")