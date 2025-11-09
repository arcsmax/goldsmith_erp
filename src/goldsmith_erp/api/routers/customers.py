"""Customer/CRM API Endpoints"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_db, require_permission, Permission
from goldsmith_erp.db.models import User
from goldsmith_erp.models.customer import (
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    CustomerListItem,
    CustomerWithOrders,
)
from goldsmith_erp.services.customer_service import CustomerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/", response_model=List[CustomerListItem])
async def list_customers(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search in name, company, email"),
    customer_type: Optional[str] = Query(None, description="Filter by customer type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    List all customers with optional filtering.

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    try:
        customers = await CustomerService.get_customers(
            db,
            skip=skip,
            limit=limit,
            search=search,
            customer_type=customer_type,
            is_active=is_active,
            tag=tag,
        )
        return customers

    except Exception as e:
        logger.error("Error listing customers", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customers"
        )


@router.get("/search", response_model=List[CustomerListItem])
async def search_customers(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Fast customer search for autocomplete.

    Searches by name, company name, and email.

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    try:
        customers = await CustomerService.search_customers(db, q, limit=limit)
        return customers

    except Exception as e:
        logger.error("Error searching customers", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed"
        )


@router.get("/top", response_model=List[dict])
async def get_top_customers(
    limit: int = Query(10, ge=1, le=50, description="Number of top customers"),
    by: str = Query("revenue", description="Sort by: revenue, orders, recent"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Get top customers by different criteria.

    - revenue: Customers who spent the most
    - orders: Customers with most orders
    - recent: Customers with most recent orders

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    if by not in ["revenue", "orders", "recent"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 'by' parameter. Must be: revenue, orders, or recent"
        )

    try:
        top_customers = await CustomerService.get_top_customers(db, limit=limit, by=by)
        return top_customers

    except Exception as e:
        logger.error("Error getting top customers", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get top customers"
        )


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Get customer by ID.

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    customer = await CustomerService.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found"
        )
    return customer


@router.get("/{customer_id}/stats", response_model=dict)
async def get_customer_statistics(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Get customer statistics (order count, total spent, last order).

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    # Verify customer exists
    customer = await CustomerService.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found"
        )

    try:
        stats = await CustomerService.get_customer_stats(db, customer_id)
        return stats

    except Exception as e:
        logger.error(f"Error getting customer stats for {customer_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get customer statistics"
        )


@router.post("/", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_in: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_CREATE)),
):
    """
    Create a new customer.

    Permissions: Requires CUSTOMER_CREATE permission.
    """
    try:
        customer = await CustomerService.create_customer(db, customer_in)
        return customer

    except ValueError as e:
        # Email already exists or validation error
        logger.warning(f"Customer creation validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating customer", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer"
        )


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: int,
    customer_update: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_EDIT)),
):
    """
    Update customer information.

    Only provided fields will be updated.

    Permissions: Requires CUSTOMER_EDIT permission.
    """
    try:
        customer = await CustomerService.update_customer(db, customer_id, customer_update)
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found"
            )
        return customer

    except ValueError as e:
        # Email conflict or validation error
        logger.warning(f"Customer update validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating customer {customer_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update customer"
        )


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_DELETE)),
):
    """
    Soft delete a customer (sets is_active = False).

    Cannot delete customers with existing orders.

    Permissions: Requires CUSTOMER_DELETE permission (Admin only).
    """
    try:
        success = await CustomerService.delete_customer(db, customer_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found"
            )

    except ValueError as e:
        # Customer has orders
        logger.warning(f"Cannot delete customer {customer_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deleting customer {customer_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete customer"
        )
