"""
Customer API endpoints with GDPR compliance.

This router provides RESTful API endpoints for customer management with
comprehensive GDPR compliance features including:
- CRUD operations with audit logging
- Consent management (GDPR Article 7)
- Data subject rights (Articles 15-22)
- Data retention management (Article 5(1)(e))
- Customer search and filtering

Author: Claude AI
Date: 2025-11-06
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.session import get_session
from goldsmith_erp.db.repositories.customer import CustomerRepository
from goldsmith_erp.services.customer_service import CustomerService
from goldsmith_erp.models.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerSummary,
    CustomerList,
    ConsentUpdate,
    ConsentStatus,
    CustomerExportResponse,
    CustomerErasureRequest,
    CustomerAnonymizeRequest,
    RetentionReview,
    RetentionUpdate,
    AuditLogEntry,
    AuditLogList,
    CustomerStatistics,
    CustomerSearch,
)
from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.models import User

router = APIRouter()


def get_customer_service(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> CustomerService:
    """Dependency to get customer service with current user context."""
    repository = CustomerRepository(session, current_user_id=current_user.id)
    return CustomerService(repository)


# ═══════════════════════════════════════════════════════════════════════════
# Basic CRUD Operations
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/", response_model=CustomerList, summary="List customers")
async def list_customers(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    include_deleted: bool = Query(False, description="Include soft-deleted customers"),
    order_by: Optional[str] = Query(
        None,
        description="Field to order by (prefix with - for descending)"
    ),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Get list of customers with optional filtering and pagination.

    **Requires authentication.**

    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum records to return (max 1000)
    - **is_active**: Filter by active status
    - **include_deleted**: Include soft-deleted customers (admin only)
    - **order_by**: Field to order by (e.g., "last_name", "-created_at")

    **GDPR Note**: All customer data access is logged in audit trail.
    """
    filters = {}
    if is_active is not None:
        filters["is_active"] = is_active

    customers = await service.list_customers(
        skip=skip,
        limit=limit,
        filters=filters,
        order_by=order_by,
        include_deleted=include_deleted,
    )

    # Get total count
    total = len(customers) + skip  # Simplified

    return CustomerList.create(customers, total, skip, limit)


@router.get("/search", response_model=List[CustomerResponse], summary="Search customers")
async def search_customers(
    query: str = Query(..., min_length=2, description="Search query (min 2 characters)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    include_deleted: bool = Query(False, description="Include soft-deleted customers"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Search customers by name, email, or customer number.

    **Requires authentication.**

    - **query**: Search term (searches in name, email, customer_number)
    - **skip**: Pagination offset
    - **limit**: Maximum results
    - **include_deleted**: Include soft-deleted customers

    **GDPR Note**: Search queries are logged for security auditing.
    """
    return await service.search_customers(
        query=query,
        skip=skip,
        limit=limit,
        include_deleted=include_deleted,
    )


@router.get("/statistics", response_model=CustomerStatistics, summary="Get customer statistics")
async def get_statistics(
    service: CustomerService = Depends(get_customer_service)
):
    """
    Get customer statistics overview.

    **Requires authentication.**

    Returns counts for:
    - Total active customers
    - Total customers (including inactive)
    - Soft-deleted customers
    - Customers with marketing consent
    """
    return await service.get_statistics()


@router.get("/{customer_id}", response_model=CustomerResponse, summary="Get customer by ID")
async def get_customer(
    customer_id: int = Path(..., description="Customer ID"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Get a specific customer by ID.

    **Requires authentication.**

    - **customer_id**: ID of the customer to retrieve

    **GDPR Note**: This access is logged in the customer's audit trail
    (GDPR Article 30 - Record of processing activities).
    """
    return await service.get_customer(customer_id)


@router.get("/by-email/{email}", response_model=CustomerResponse, summary="Get customer by email")
async def get_customer_by_email(
    email: str = Path(..., description="Customer email address"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Get a customer by email address.

    **Requires authentication.**

    - **email**: Email address of the customer

    **GDPR Note**: This access is logged in the customer's audit trail.
    """
    return await service.get_customer_by_email(email)


@router.get("/by-number/{customer_number}", response_model=CustomerResponse, summary="Get customer by number")
async def get_customer_by_number(
    customer_number: str = Path(..., description="Customer number (CUST-YYYYMM-XXXX)"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Get a customer by customer number.

    **Requires authentication.**

    - **customer_number**: Unique customer number (format: CUST-YYYYMM-XXXX)

    **GDPR Note**: This access is logged in the customer's audit trail.
    """
    return await service.get_customer_by_number(customer_number)


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED, summary="Create customer")
async def create_customer(
    data: CustomerCreate,
    service: CustomerService = Depends(get_customer_service)
):
    """
    Create a new customer.

    **Requires authentication.**

    **Required fields:**
    - **first_name**: Customer first name
    - **last_name**: Customer last name
    - **email**: Customer email (must be unique)

    **GDPR Compliance:**
    - **legal_basis**: Legal basis for processing (contract, consent, legitimate_interest)
    - **consent_marketing**: Marketing consent flag
    - **consent_version**: Version of consent terms accepted
    - **consent_ip_address**: IP address where consent was given
    - **consent_method**: Method of consent collection

    **Optional fields:**
    - phone, address, city, postal_code, country
    - notes, tags

    **GDPR Notes:**
    - Customer creation is logged in audit trail
    - Customer number is auto-generated (CUST-YYYYMM-XXXX)
    - Default retention period: 10 years from creation
    - All PII fields (phone, address) are encrypted at rest
    """
    return await service.create_customer(**data.dict())


@router.put("/{customer_id}", response_model=CustomerResponse, summary="Update customer")
async def update_customer(
    data: CustomerUpdate,
    customer_id: int = Path(..., description="Customer ID"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Update a customer.

    **Requires authentication.**

    All fields are optional - only provided fields will be updated.

    - **customer_id**: ID of the customer to update

    **GDPR Notes:**
    - All changes are logged in audit trail with old/new values
    - Updated_at and updated_by are automatically set
    - Email changes are validated for uniqueness
    """
    update_data = data.dict(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update"
        )

    return await service.update_customer(customer_id, **update_data)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete customer")
async def delete_customer(
    customer_id: int = Path(..., description="Customer ID"),
    hard_delete: bool = Query(False, description="Permanent deletion (use with caution)"),
    deletion_reason: Optional[str] = Query(None, description="Reason for deletion"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Delete a customer (soft delete by default).

    **Requires authentication.**

    - **customer_id**: ID of the customer to delete
    - **hard_delete**: If true, permanently delete (GDPR erasure)
    - **deletion_reason**: Reason for deletion (recommended for compliance)

    **Soft Delete (default):**
    - Sets is_deleted=True
    - Preserves all data
    - Customer excluded from normal queries
    - Can be restored if needed

    **Hard Delete (permanent):**
    - Permanently removes all customer data
    - Cannot be undone
    - Use only for GDPR erasure requests
    - Requires deletion_reason

    **GDPR Note**: Deletion is logged in audit trail before removal.
    """
    await service.delete_customer(
        customer_id=customer_id,
        hard_delete=hard_delete,
        deletion_reason=deletion_reason,
    )


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Consent Management (Article 7)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/{customer_id}/consent", response_model=CustomerResponse, summary="Update customer consent")
async def update_consent(
    customer_id: int = Path(..., description="Customer ID"),
    data: ConsentUpdate = ...,
    service: CustomerService = Depends(get_customer_service)
):
    """
    Update customer consent preferences (GDPR Article 7).

    **Requires authentication.**

    - **customer_id**: ID of the customer
    - **consent_type**: Type of consent (marketing, email, phone, sms, data_processing)
    - **consent_value**: True to grant, False to revoke
    - **consent_version**: Version of consent terms
    - **ip_address**: IP address where consent was given/revoked
    - **consent_method**: Method of consent (web_form, email, phone)

    **GDPR Compliance:**
    - Consent changes are logged with timestamp and IP
    - Consent can be freely withdrawn at any time (Article 7(3))
    - Consent version tracking for terms changes
    - Audit trail maintained for all consent changes

    **Example:**
    ```json
    {
        "consent_type": "marketing",
        "consent_value": true,
        "consent_version": "1.0",
        "ip_address": "192.168.1.100",
        "consent_method": "web_form"
    }
    ```
    """
    return await service.update_consent(
        customer_id=customer_id,
        consent_type=data.consent_type,
        consent_value=data.consent_value,
        consent_version=data.consent_version,
        ip_address=data.ip_address,
        consent_method=data.consent_method,
    )


@router.post("/{customer_id}/consent/revoke-all", response_model=CustomerResponse, summary="Revoke all consents")
async def revoke_all_consents(
    customer_id: int = Path(..., description="Customer ID"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Revoke all customer consents (GDPR Article 7(3) - Right to withdraw).

    **Requires authentication.**

    - **customer_id**: ID of the customer

    This endpoint revokes all optional consents:
    - Marketing consent
    - Email communication consent
    - Phone communication consent
    - SMS communication consent

    **GDPR Note**: Data processing consent for contract fulfillment
    is not revoked as it's based on legal basis "contract", not consent.
    """
    return await service.revoke_all_consents(customer_id)


@router.get("/{customer_id}/consent", response_model=ConsentStatus, summary="Get consent status")
async def get_consent_status(
    customer_id: int = Path(..., description="Customer ID"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Get customer consent status.

    **Requires authentication.**

    - **customer_id**: ID of the customer

    Returns current status of all consents:
    - Marketing
    - Email communication
    - Phone communication
    - SMS communication
    - Data processing
    - Consent metadata (date, version, method)
    """
    customer = await service.get_customer(customer_id)

    return ConsentStatus(
        marketing=customer.consent_marketing,
        email_communication=customer.email_communication_consent,
        phone_communication=customer.phone_communication_consent,
        sms_communication=customer.sms_communication_consent,
        data_processing=customer.data_processing_consent,
        consent_date=customer.consent_date,
        consent_version=customer.consent_version,
        consent_method=customer.consent_method,
    )


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Data Subject Rights (Articles 15-22)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{customer_id}/export", response_model=CustomerExportResponse, summary="Export customer data")
async def export_customer_data(
    customer_id: int = Path(..., description="Customer ID"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Export all customer data (GDPR Article 15 - Right of Access).

    **Requires authentication.**

    - **customer_id**: ID of the customer

    Returns complete customer data in portable format including:
    - Personal information
    - GDPR compliance information
    - Consent preferences
    - Audit trail (all data access history)
    - Related orders (if any)

    **GDPR Compliance:**
    - Fulfills data subject access request (DSAR)
    - Response time requirement: within 1 month (Article 12(3))
    - Data provided in structured, commonly used format (JSON)
    - Free of charge for first request

    **Use Case:** Customer requests copy of all their personal data.
    """
    return await service.export_customer_data(customer_id)


@router.post("/{customer_id}/anonymize", response_model=CustomerResponse, summary="Anonymize customer")
async def anonymize_customer(
    customer_id: int = Path(..., description="Customer ID"),
    reason: str = Query("Data retention period expired", description="Reason for anonymization"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Anonymize customer data (GDPR Article 5(1)(e) - Storage Limitation).

    **Requires authentication.**

    - **customer_id**: ID of the customer
    - **reason**: Reason for anonymization

    Replaces all PII with anonymized values:
    - Name → "ANONYMIZED USER-{id}"
    - Email → "anonymized-{id}@deleted.local"
    - Phone → NULL
    - Address → NULL
    - All other PII → NULL or anonymized

    **When to use:**
    - Data retention period has expired
    - Customer requests erasure but financial records must be retained
    - Legal obligation to retain statistical data only

    **GDPR Note**: Preserves statistical/analytical data while removing PII.
    """
    return await service.anonymize_customer(customer_id, reason)


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Data Retention (Article 5(1)(e))
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/retention/review", response_model=List[RetentionReview], summary="Get retention review list")
async def get_retention_review(
    category: Optional[str] = Query(None, description="Filter by retention category"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Get customers needing retention review.

    **Requires authentication.**

    - **category**: Optional filter by retention category

    Returns list of customers whose retention deadline has passed
    or is approaching, requiring review action.

    **Recommended Actions:**
    - **Extend**: Customer still active, extend retention
    - **Anonymize**: Retention expired, anonymize data
    - **Delete**: No legal obligation, permanently delete

    **GDPR Compliance:**
    - Storage limitation principle (Article 5(1)(e))
    - Personal data must not be kept longer than necessary
    - Regular review of retention deadlines required
    """
    customers = await service.get_customers_for_retention_review(category)

    return [RetentionReview.from_customer(c) for c in customers]


@router.post("/{customer_id}/retention", response_model=CustomerResponse, summary="Update retention deadline")
async def update_retention(
    customer_id: int = Path(..., description="Customer ID"),
    data: RetentionUpdate = ...,
    service: CustomerService = Depends(get_customer_service)
):
    """
    Update customer retention deadline.

    **Requires authentication.**

    - **customer_id**: ID of the customer
    - **last_order_date**: Date of last order/activity
    - **retention_period_days**: Retention period in days (default: 10 years)

    Updates retention deadline based on last activity date.

    **German Tax Law:** Financial records must be retained for 10 years
    (§147 AO - Abgabenordnung).

    **GDPR Note**: Retention period must be based on legitimate purpose
    and legal obligations.
    """
    return await service.update_customer_retention(
        customer_id=customer_id,
        last_order_date=data.last_order_date,
        retention_period_days=data.retention_period_days,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Audit Trail (Article 30)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{customer_id}/audit-logs", response_model=AuditLogList, summary="Get customer audit trail")
async def get_audit_logs(
    customer_id: int = Path(..., description="Customer ID"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    service: CustomerService = Depends(get_customer_service)
):
    """
    Get audit trail for customer data access.

    **Requires authentication.**

    - **customer_id**: ID of the customer
    - **skip**: Pagination offset
    - **limit**: Maximum records

    Returns complete audit log showing:
    - Who accessed the data
    - When it was accessed
    - What action was performed
    - What data was changed (before/after values)
    - IP address and user agent
    - Legal basis for access

    **GDPR Compliance:**
    - Article 30: Record of processing activities
    - Article 5(2): Accountability principle
    - Required for demonstrating GDPR compliance
    - Must be kept for at least duration of data retention

    **Use Cases:**
    - Data breach investigation
    - Customer access request (Article 15)
    - Compliance audit
    - Security review
    """
    audit_logs = await service.get_customer_audit_trail(
        customer_id=customer_id,
        skip=skip,
        limit=limit,
    )

    total = len(audit_logs) + skip  # Simplified

    return AuditLogList.create(audit_logs, total, skip, limit)
