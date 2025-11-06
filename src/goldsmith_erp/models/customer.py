"""
Pydantic schemas for Customer with GDPR compliance.

These schemas define the API contract for customer data with comprehensive
GDPR compliance features including validation, consent management, and
data subject rights.

Author: Claude AI
Date: 2025-11-06
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, validator


# ═══════════════════════════════════════════════════════════════════════════
# Base Schemas
# ═══════════════════════════════════════════════════════════════════════════

class CustomerBase(BaseModel):
    """Base customer schema with common fields."""

    first_name: str = Field(..., description="Customer first name", min_length=1, max_length=100)
    last_name: str = Field(..., description="Customer last name", min_length=1, max_length=100)
    email: EmailStr = Field(..., description="Customer email address")
    phone: Optional[str] = Field(None, description="Customer phone number (encrypted in DB)")

    # Address
    address_line1: Optional[str] = Field(None, description="Address line 1 (encrypted in DB)")
    address_line2: Optional[str] = Field(None, description="Address line 2 (encrypted in DB)")
    postal_code: Optional[str] = Field(None, description="Postal code", max_length=20)
    city: Optional[str] = Field(None, description="City", max_length=100)
    country: str = Field("DE", description="Country code (ISO 3166-1 alpha-2)", max_length=2)

    # Status
    is_active: bool = Field(True, description="Whether customer is active")

    # GDPR Legal Basis (GDPR Article 6)
    legal_basis: str = Field(
        "contract",
        description="GDPR legal basis for processing",
        regex="^(contract|consent|legitimate_interest|legal_obligation)$"
    )

    # Additional fields
    notes: Optional[str] = Field(None, description="Internal notes about customer")
    tags: List[str] = Field(default_factory=list, description="Customer tags for categorization")

    @validator("country")
    def validate_country(cls, v):
        """Validate country code format."""
        if v and len(v) != 2:
            raise ValueError("Country code must be 2 characters (ISO 3166-1 alpha-2)")
        return v.upper() if v else v


class CustomerCreate(CustomerBase):
    """Schema for creating a new customer."""

    # GDPR Consent (Article 7)
    consent_marketing: bool = Field(False, description="Marketing consent")
    consent_version: Optional[str] = Field("1.0", description="Version of consent terms")
    consent_ip_address: Optional[str] = Field(None, description="IP address where consent was given")
    consent_method: Optional[str] = Field(None, description="Method of consent collection")

    # Privacy Preferences (Article 21)
    data_processing_consent: bool = Field(True, description="Consent for data processing")
    email_communication_consent: bool = Field(False, description="Consent for email communication")
    phone_communication_consent: bool = Field(False, description="Consent for phone communication")
    sms_communication_consent: bool = Field(False, description="Consent for SMS communication")


class CustomerUpdate(BaseModel):
    """Schema for updating a customer (all fields optional)."""

    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

    # Address
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    postal_code: Optional[str] = Field(None, max_length=20)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=2)

    # Status
    is_active: Optional[bool] = None

    # GDPR
    legal_basis: Optional[str] = Field(
        None,
        regex="^(contract|consent|legitimate_interest|legal_obligation)$"
    )

    # Additional fields
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class CustomerResponse(CustomerBase):
    """Schema for customer response (includes DB fields)."""

    id: int
    customer_number: str = Field(..., description="Unique customer number (CUST-YYYYMM-XXXX)")

    # GDPR Consent fields
    consent_marketing: bool
    consent_date: Optional[datetime] = Field(None, description="Date consent was given/updated")
    consent_version: Optional[str] = None
    consent_ip_address: Optional[str] = None
    consent_method: Optional[str] = None

    # Privacy Preferences
    data_processing_consent: bool
    email_communication_consent: bool
    phone_communication_consent: bool
    sms_communication_consent: bool

    # Data Retention (Article 5(1)(e))
    data_retention_category: str = Field(..., description="Data retention category")
    last_order_date: Optional[datetime] = Field(None, description="Date of last order")
    retention_deadline: Optional[datetime] = Field(None, description="Data retention deadline")

    # Soft Delete (Article 17)
    is_deleted: bool
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[int] = None
    deletion_reason: Optional[str] = None

    # Audit fields
    created_at: datetime
    created_by: int
    updated_at: Optional[datetime] = None
    updated_by: Optional[int] = None

    class Config:
        from_attributes = True


class CustomerSummary(BaseModel):
    """Minimal customer information for lists and references."""

    id: int
    customer_number: str
    first_name: str
    last_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerList(BaseModel):
    """Schema for paginated customer list."""

    items: List[CustomerResponse]
    total: int
    skip: int
    limit: int
    has_more: bool

    @classmethod
    def create(
        cls,
        items: List,
        total: int,
        skip: int,
        limit: int
    ) -> "CustomerList":
        """Create paginated response."""
        return cls(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
            has_more=(skip + len(items)) < total,
        )


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Consent Management Schemas
# ═══════════════════════════════════════════════════════════════════════════

class ConsentUpdate(BaseModel):
    """Schema for updating customer consent."""

    consent_type: str = Field(
        ...,
        description="Type of consent to update",
        regex="^(marketing|email|phone|sms|data_processing)$"
    )
    consent_value: bool = Field(..., description="True to grant, False to revoke")
    consent_version: str = Field("1.0", description="Version of consent terms")
    ip_address: Optional[str] = Field(None, description="IP address of consent action")
    consent_method: Optional[str] = Field(None, description="Method of consent (web_form, email, phone)")


class ConsentStatus(BaseModel):
    """Schema for customer consent status."""

    marketing: bool
    email_communication: bool
    phone_communication: bool
    sms_communication: bool
    data_processing: bool
    consent_date: Optional[datetime]
    consent_version: Optional[str]
    consent_method: Optional[str]


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Data Subject Rights Schemas
# ═══════════════════════════════════════════════════════════════════════════

class CustomerExportRequest(BaseModel):
    """Schema for GDPR data export request (Article 15 - Right of Access)."""

    customer_id: int = Field(..., description="Customer ID to export")
    include_audit_logs: bool = Field(True, description="Include audit trail in export")
    include_orders: bool = Field(True, description="Include order history in export")
    format: str = Field("json", description="Export format", regex="^(json|csv|xml)$")


class CustomerExportResponse(BaseModel):
    """Schema for GDPR data export response."""

    customer_information: Dict[str, Any]
    gdpr_information: Dict[str, Any]
    consent_preferences: Dict[str, Any]
    audit_trail: List[Dict[str, Any]]
    orders: Optional[List[Dict[str, Any]]] = None
    export_metadata: Dict[str, Any]


class CustomerErasureRequest(BaseModel):
    """Schema for GDPR erasure request (Article 17 - Right to Erasure)."""

    customer_id: int = Field(..., description="Customer ID to erase")
    hard_delete: bool = Field(
        False,
        description="True for permanent deletion, False for soft delete"
    )
    deletion_reason: str = Field(
        ...,
        description="Reason for deletion (required for compliance)",
        min_length=10
    )
    confirm_erasure: bool = Field(
        ...,
        description="Must be True to confirm permanent deletion"
    )

    @validator("confirm_erasure")
    def validate_confirmation(cls, v, values):
        """Require confirmation for hard delete."""
        if values.get("hard_delete") and not v:
            raise ValueError("confirm_erasure must be True for permanent deletion")
        return v


class CustomerAnonymizeRequest(BaseModel):
    """Schema for customer anonymization request."""

    customer_id: int = Field(..., description="Customer ID to anonymize")
    reason: str = Field(
        "Data retention period expired",
        description="Reason for anonymization"
    )


class CustomerRectificationRequest(BaseModel):
    """Schema for GDPR rectification request (Article 16 - Right to Rectification)."""

    customer_id: int = Field(..., description="Customer ID")
    corrections: CustomerUpdate = Field(..., description="Fields to correct")
    reason: str = Field(
        ...,
        description="Reason for rectification",
        min_length=10
    )


# ═══════════════════════════════════════════════════════════════════════════
# Data Retention Schemas
# ═══════════════════════════════════════════════════════════════════════════

class RetentionReview(BaseModel):
    """Schema for customer retention review."""

    customer_id: int
    customer_number: str
    full_name: str
    email: EmailStr
    last_order_date: Optional[datetime]
    retention_deadline: Optional[datetime]
    days_until_deletion: Optional[int]
    data_retention_category: str
    recommended_action: str  # "extend", "anonymize", "delete"

    @classmethod
    def from_customer(cls, customer) -> "RetentionReview":
        """Create from Customer model instance."""
        days_until = None
        recommended_action = "extend"

        if customer.retention_deadline:
            days_until = (customer.retention_deadline - datetime.utcnow()).days

            if days_until < 0:
                recommended_action = "anonymize"
            elif days_until < 30:
                recommended_action = "extend"

        return cls(
            customer_id=customer.id,
            customer_number=customer.customer_number,
            full_name=f"{customer.first_name} {customer.last_name}",
            email=customer.email,
            last_order_date=customer.last_order_date,
            retention_deadline=customer.retention_deadline,
            days_until_deletion=days_until,
            data_retention_category=customer.data_retention_category,
            recommended_action=recommended_action,
        )


class RetentionUpdate(BaseModel):
    """Schema for updating customer retention deadline."""

    customer_id: int = Field(..., description="Customer ID")
    last_order_date: datetime = Field(..., description="Date of last order/activity")
    retention_period_days: int = Field(
        3650,
        description="Retention period in days (default: 10 years)",
        ge=1,
        le=36500  # Max 100 years
    )


# ═══════════════════════════════════════════════════════════════════════════
# Audit Trail Schemas
# ═══════════════════════════════════════════════════════════════════════════

class AuditLogEntry(BaseModel):
    """Schema for customer audit log entry."""

    id: int
    customer_id: int
    action: str
    entity: str
    entity_id: Optional[int]
    field_name: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    user_id: int
    user_email: Optional[str]
    user_role: Optional[str]
    timestamp: datetime
    ip_address: Optional[str]
    user_agent: Optional[str]
    legal_basis: Optional[str]
    purpose: Optional[str]

    class Config:
        from_attributes = True


class AuditLogList(BaseModel):
    """Schema for paginated audit log list."""

    items: List[AuditLogEntry]
    total: int
    skip: int
    limit: int
    has_more: bool

    @classmethod
    def create(
        cls,
        items: List,
        total: int,
        skip: int,
        limit: int
    ) -> "AuditLogList":
        """Create paginated response."""
        return cls(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
            has_more=(skip + len(items)) < total,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Statistics Schemas
# ═══════════════════════════════════════════════════════════════════════════

class CustomerStatistics(BaseModel):
    """Schema for customer statistics."""

    total_active_customers: int = Field(..., description="Total active customers")
    total_customers: int = Field(..., description="Total customers (including inactive)")
    total_deleted_customers: int = Field(..., description="Total soft-deleted customers")
    marketing_consent_customers: int = Field(..., description="Customers with marketing consent")
    customers_needing_retention_review: int = Field(
        0,
        description="Customers past retention deadline"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Search Schemas
# ═══════════════════════════════════════════════════════════════════════════

class CustomerSearch(BaseModel):
    """Schema for customer search parameters."""

    query: str = Field(..., description="Search query", min_length=2)
    skip: int = Field(0, description="Number of records to skip", ge=0)
    limit: int = Field(100, description="Maximum records to return", ge=1, le=1000)
    include_deleted: bool = Field(False, description="Include soft-deleted customers")


# ═══════════════════════════════════════════════════════════════════════════
# Error Schemas
# ═══════════════════════════════════════════════════════════════════════════

class GDPRError(BaseModel):
    """Schema for GDPR-related errors."""

    error_code: str = Field(..., description="Error code")
    error_message: str = Field(..., description="Human-readable error message")
    gdpr_article: Optional[str] = Field(None, description="Related GDPR article")
    remediation: Optional[str] = Field(None, description="How to fix the error")


# ═══════════════════════════════════════════════════════════════════════════
# Bulk Operations Schemas
# ═══════════════════════════════════════════════════════════════════════════

class BulkConsentUpdate(BaseModel):
    """Schema for bulk consent updates."""

    customer_ids: List[int] = Field(..., description="List of customer IDs", max_items=1000)
    consent_type: str = Field(
        ...,
        description="Type of consent to update",
        regex="^(marketing|email|phone|sms|data_processing)$"
    )
    consent_value: bool = Field(..., description="True to grant, False to revoke")
    consent_version: str = Field("1.0", description="Version of consent terms")
    reason: str = Field(..., description="Reason for bulk update")


class BulkOperationResult(BaseModel):
    """Schema for bulk operation results."""

    total_requested: int = Field(..., description="Total operations requested")
    successful: int = Field(..., description="Successful operations")
    failed: int = Field(..., description="Failed operations")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Error details")
