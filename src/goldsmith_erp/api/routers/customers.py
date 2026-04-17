"""Customer/CRM API Endpoints"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.api.deps import Permission, get_db, require_permission
from goldsmith_erp.core.idempotency import IdempotencyContext, get_idempotency_context
from goldsmith_erp.db.models import Customer as CustomerModel
from goldsmith_erp.db.models import User
from goldsmith_erp.models.customer import (
    CustomerCreate,
    CustomerListItem,
    CustomerRead,
    CustomerUpdate,
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
            detail="Failed to retrieve customers",
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Search failed"
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
            detail="Invalid 'by' parameter. Must be: revenue, orders, or recent",
        )

    try:
        top_customers = await CustomerService.get_top_customers(db, limit=limit, by=by)
        return top_customers

    except Exception as e:
        logger.error("Error getting top customers", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get top customers",
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
            detail=f"Customer {customer_id} not found",
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
            detail=f"Customer {customer_id} not found",
        )

    try:
        stats = await CustomerService.get_customer_stats(db, customer_id)
        return stats

    except Exception as e:
        logger.error(f"Error getting customer stats for {customer_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get customer statistics",
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error creating customer", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer",
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
        customer = await CustomerService.update_customer(
            db, customer_id, customer_update
        )
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found",
            )
        return customer

    except ValueError as e:
        # Email conflict or validation error
        logger.warning(f"Customer update validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating customer {customer_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update customer",
        )


@router.get("/{customer_id}/export", response_model=Dict[str, Any])
async def gdpr_export_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_DELETE)),
):
    """
    GDPR Art. 15 — Export all personal data held for a customer.

    Returns the customer record along with all related data (orders,
    measurements) as a JSON object.  Access is restricted to ADMIN role
    (CUSTOMER_DELETE permission) because the export contains raw PII.

    Permissions: Requires CUSTOMER_DELETE permission (Admin only).
    """
    # Load customer with all relationships using selectinload to avoid N+1
    result = await db.execute(
        select(CustomerModel)
        .options(
            selectinload(CustomerModel.orders),
            selectinload(CustomerModel.measurements),
        )
        .filter(CustomerModel.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    # Audit log — financial/PII data export must be traceable
    logger.info(
        "GDPR data export",
        extra={
            "audit": True,
            "action": "gdpr_export",
            "customer_id": customer_id,
            "user_id": current_user.id,
            "user_role": current_user.role.value,
        },
    )

    # Serialize all data — omit relationship proxy objects and SQLAlchemy state
    orders_data = []
    for order in customer.orders:
        orders_data.append(
            {
                "id": order.id,
                "status": order.status,
                "description": order.description,
                "price": float(order.price) if order.price is not None else None,
                "created_at": (
                    order.created_at.isoformat() if order.created_at else None
                ),
                "deadline": order.deadline.isoformat() if order.deadline else None,
            }
        )

    measurements_data = []
    for m in customer.measurements:
        measurements_data.append(
            {
                "id": m.id,
                "measurement_type": (
                    m.measurement_type.value if m.measurement_type else None
                ),
                "value": m.value,
                "unit": m.unit,
                "hand": m.hand.value if m.hand else None,
                "finger": m.finger.value if m.finger else None,
                "notes": m.notes,
                "measured_at": m.measured_at.isoformat() if m.measured_at else None,
            }
        )

    return {
        "export_date": datetime.utcnow().isoformat(),
        "customer": {
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "company_name": customer.company_name,
            "email": customer.email,
            "phone": customer.phone,
            "mobile": customer.mobile,
            "street": customer.street,
            "city": customer.city,
            "postal_code": customer.postal_code,
            "country": customer.country,
            "customer_type": customer.customer_type,
            "source": customer.source,
            "notes": customer.notes,
            "tags": customer.tags,
            "ring_size": customer.ring_size,
            "chain_length_cm": customer.chain_length_cm,
            "bracelet_length_cm": customer.bracelet_length_cm,
            "allergies": customer.allergies,
            "preferences": customer.preferences,
            "birthday": customer.birthday.isoformat() if customer.birthday else None,
            "is_active": customer.is_active,
            "created_at": (
                customer.created_at.isoformat() if customer.created_at else None
            ),
        },
        "orders": orders_data,
        "measurements": measurements_data,
    }


@router.delete("/{customer_id}/gdpr-erase", status_code=status.HTTP_200_OK)
async def gdpr_erase_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_DELETE)),
    # Slice 2 (M1) — accept the two idempotency headers. V1.1 does not yet
    # dedupe server-side (check_and_store_idempotency is a stub); the
    # context object is captured here so a retry in V1.1 still surfaces a
    # valid-UUID / within-window check before the expensive scrub runs.
    idem: IdempotencyContext = Depends(get_idempotency_context),
):
    """
    GDPR Art. 17 — Request erasure of all personal data for a customer.

    Three things happen atomically in a single DB transaction:
      1. Customer is deactivated (is_active=False) and scheduled for
         hard-delete after a 30-day grace period.
      2. Customer PII (names, phone, email) is scrubbed from related
         free-text fields — order descriptions, special instructions,
         order comments, and time-entry notes. See
         `CustomerService.scrub_customer_pii` for the full scope.
      3. Audit rows are written to `customer_audit_logs` and a tracking
         row to `gdpr_requests` (Art. 30 record of processing).

    The gdpr-cleanup.sh cron job performs the actual hard-delete once the
    30-day grace period has passed.

    Permissions: Requires CUSTOMER_DELETE permission (Admin only).
    """
    result = await db.execute(
        select(CustomerModel).filter(CustomerModel.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    if customer.deletion_scheduled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Löschung bereits angefordert. "
                f"Geplantes Löschdatum: {customer.deletion_scheduled_at.date().isoformat()}"
            ),
        )

    deletion_date = datetime.utcnow() + timedelta(days=30)

    # All mutations go through a single transaction — if PII scrub fails,
    # the customer row is NOT left half-deactivated.
    try:
        customer.is_active = False
        customer.deletion_scheduled_at = deletion_date
        customer.updated_at = datetime.utcnow()

        # Scrub PII from related free-text records. This also writes
        # CustomerAuditLog + GDPRRequest entries.
        scrub_counts = await CustomerService.scrub_customer_pii(
            db,
            customer_id=customer_id,
            performed_by=current_user.id,
        )

        await db.commit()
    except Exception:
        await db.rollback()
        logger.error(
            "GDPR erasure failed — transaction rolled back",
            extra={
                "audit": True,
                "action": "gdpr_erase_request_failed",
                "customer_id": customer_id,
                "user_id": current_user.id,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GDPR erasure failed — no changes persisted.",
        )

    # Audit log — GDPR erasure requests are legally significant.
    # Include the idempotency key (if any) so operator-side log analysis
    # can correlate client retries. client_created_at captured for Lena
    # §4 timing even though V1.1 does not yet act on it server-side.
    logger.info(
        "GDPR erasure requested",
        extra={
            "audit": True,
            "action": "gdpr_erase_request",
            "customer_id": customer_id,
            "user_id": current_user.id,
            "deletion_scheduled": deletion_date.isoformat(),
            "pii_redaction_count": scrub_counts.get("total", 0),
            "idempotency_key": str(idem.key) if idem.key else None,
            "client_created_at": (
                idem.client_created_at.isoformat() if idem.client_created_at else None
            ),
        },
    )

    return {
        "message": "Löschung geplant",
        "customer_id": customer_id,
        "deletion_date": deletion_date.date().isoformat(),
        "pii_redactions": scrub_counts,
    }


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
                detail=f"Customer {customer_id} not found",
            )

    except ValueError as e:
        # Customer has orders
        logger.warning(f"Cannot delete customer {customer_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting customer {customer_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete customer",
        )
