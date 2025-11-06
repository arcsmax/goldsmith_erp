"""
Customer service with GDPR-compliant business logic.

This service provides business logic for customer management with
comprehensive GDPR compliance including:
- Data validation
- Consent management
- Data retention policies
- Data subject rights (access, erasure, portability, rectification)
- Audit logging
- Customer number generation

Author: Claude AI
Date: 2025-11-06
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status

from goldsmith_erp.db.repositories.customer import CustomerRepository
from goldsmith_erp.db.models import Customer


class CustomerService:
    """
    Service for customer business logic with GDPR compliance.

    Provides comprehensive customer management with:
    - CRUD operations with validation
    - Customer number generation
    - Consent management
    - Data retention policies
    - GDPR data subject rights
    - Audit trail access

    Usage:
        >>> service = CustomerService(repository)
        >>> customer = await service.get_customer(1)
        >>> customers = await service.search_customers("mustermann")
    """

    def __init__(self, repository: CustomerRepository):
        """
        Initialize service.

        Args:
            repository: Customer repository instance
        """
        self.repository = repository

    # ═══════════════════════════════════════════════════════════════════════
    # Basic CRUD Operations
    # ═══════════════════════════════════════════════════════════════════════

    async def get_customer(
        self,
        customer_id: int,
        include_deleted: bool = False,
    ) -> Customer:
        """
        Get a customer by ID.

        Args:
            customer_id: Customer ID
            include_deleted: If True, include soft-deleted customers

        Returns:
            Customer instance

        Raises:
            HTTPException: If customer not found
        """
        customer = await self.repository.get_by_id(
            customer_id,
            include_deleted=include_deleted,
        )

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer with ID {customer_id} not found"
            )

        return customer

    async def get_customer_by_email(self, email: str) -> Customer:
        """
        Get customer by email address.

        Args:
            email: Customer email

        Returns:
            Customer instance

        Raises:
            HTTPException: If customer not found
        """
        customer = await self.repository.get_by_email(email)

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer with email {email} not found"
            )

        return customer

    async def get_customer_by_number(self, customer_number: str) -> Customer:
        """
        Get customer by customer number.

        Args:
            customer_number: Unique customer number (CUST-YYYYMM-XXXX)

        Returns:
            Customer instance

        Raises:
            HTTPException: If customer not found
        """
        customer = await self.repository.get_by_customer_number(customer_number)

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer with number {customer_number} not found"
            )

        return customer

    async def list_customers(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        include_deleted: bool = False,
    ) -> List[Customer]:
        """
        List customers with optional filtering and pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return (max 1000)
            filters: Optional filters (e.g., {"is_active": True})
            order_by: Field name to order by (prefix with - for descending)
            include_deleted: If True, include soft-deleted customers

        Returns:
            List of customers

        Raises:
            HTTPException: If limit exceeds maximum
        """
        # Enforce maximum limit for performance
        if limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum limit is 1000 customers per request"
            )

        customers = await self.repository.get_all(
            skip=skip,
            limit=limit,
            filters=filters,
            order_by=order_by,
            include_deleted=include_deleted,
        )

        return customers

    async def search_customers(
        self,
        query: str,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> List[Customer]:
        """
        Search customers by name, email, or customer number.

        Args:
            query: Search query string (min 2 characters)
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_deleted: If True, include soft-deleted customers

        Returns:
            List of matching customers

        Raises:
            HTTPException: If query too short
        """
        if len(query) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Search query must be at least 2 characters"
            )

        customers = await self.repository.search(
            query=query,
            skip=skip,
            limit=limit,
            include_deleted=include_deleted,
        )

        return customers

    async def create_customer(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone: Optional[str] = None,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        postal_code: Optional[str] = None,
        city: Optional[str] = None,
        country: str = "DE",
        legal_basis: str = "contract",
        consent_marketing: bool = False,
        consent_version: Optional[str] = "1.0",
        consent_ip_address: Optional[str] = None,
        consent_method: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
        **additional_data,
    ) -> Customer:
        """
        Create a new customer with GDPR compliance validation.

        Args:
            first_name: Customer first name (required)
            last_name: Customer last name (required)
            email: Customer email address (required, unique)
            phone: Customer phone number (will be encrypted)
            address_line1: Address line 1 (will be encrypted)
            address_line2: Address line 2 (will be encrypted)
            postal_code: Postal code
            city: City
            country: Country code (default: DE for Germany)
            legal_basis: GDPR legal basis (contract, consent, legitimate_interest)
            consent_marketing: Marketing consent flag
            consent_version: Version of consent terms
            consent_ip_address: IP address where consent was given
            consent_method: Method of consent collection
            notes: Internal notes about customer
            tags: List of tags for customer categorization
            **additional_data: Additional customer fields

        Returns:
            Created customer

        Raises:
            HTTPException: If validation fails or email already exists
        """
        # Validate required fields
        if not first_name or not first_name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="First name is required"
            )

        if not last_name or not last_name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Last name is required"
            )

        if not email or not email.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is required"
            )

        # Validate email format (basic check)
        if "@" not in email or "." not in email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )

        # Check if email already exists
        existing_customer = await self.repository.get_by_email(email)
        if existing_customer:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Customer with email {email} already exists"
            )

        # Validate legal basis
        valid_legal_bases = ["contract", "consent", "legitimate_interest", "legal_obligation"]
        if legal_basis not in valid_legal_bases:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid legal basis. Must be one of: {', '.join(valid_legal_bases)}"
            )

        # Generate customer number
        customer_number = await self._generate_customer_number()

        # Set consent metadata if marketing consent given
        consent_data = {}
        if consent_marketing:
            consent_data = {
                "consent_marketing": True,
                "consent_date": datetime.utcnow(),
                "consent_version": consent_version,
                "consent_ip_address": consent_ip_address,
                "consent_method": consent_method,
            }

        # Set default retention (10 years for contract-based customers)
        retention_deadline = datetime.utcnow() + timedelta(days=3650)

        try:
            customer = await self.repository.create(
                customer_number=customer_number,
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                email=email.strip().lower(),
                phone=phone,
                address_line1=address_line1,
                address_line2=address_line2,
                postal_code=postal_code,
                city=city,
                country=country,
                legal_basis=legal_basis,
                data_retention_category="active",
                retention_deadline=retention_deadline,
                notes=notes,
                tags=tags or [],
                **consent_data,
                **additional_data,
            )

            return customer

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create customer: {str(e)}"
            )

    async def update_customer(
        self,
        customer_id: int,
        **update_data,
    ) -> Customer:
        """
        Update customer information with validation.

        Args:
            customer_id: Customer ID
            **update_data: Fields to update

        Returns:
            Updated customer

        Raises:
            HTTPException: If customer not found or validation fails
        """
        # Check customer exists
        existing_customer = await self.repository.get_by_id(
            customer_id,
            include_deleted=False,
            log_access=False,
        )

        if not existing_customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer with ID {customer_id} not found"
            )

        # If email is being updated, check it doesn't already exist
        if "email" in update_data:
            new_email = update_data["email"].strip().lower()
            if new_email != existing_customer.email:
                email_exists = await self.repository.get_by_email(new_email)
                if email_exists:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Email {new_email} is already in use"
                    )
                update_data["email"] = new_email

        # Validate legal basis if being updated
        if "legal_basis" in update_data:
            valid_legal_bases = ["contract", "consent", "legitimate_interest", "legal_obligation"]
            if update_data["legal_basis"] not in valid_legal_bases:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid legal basis. Must be one of: {', '.join(valid_legal_bases)}"
                )

        try:
            customer = await self.repository.update(customer_id, **update_data)
            return customer

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update customer: {str(e)}"
            )

    async def delete_customer(
        self,
        customer_id: int,
        hard_delete: bool = False,
        deletion_reason: Optional[str] = None,
    ) -> bool:
        """
        Delete customer (soft or hard delete).

        Args:
            customer_id: Customer ID
            hard_delete: If True, permanently delete (GDPR erasure)
            deletion_reason: Reason for deletion (recommended for compliance)

        Returns:
            True if deleted

        Raises:
            HTTPException: If customer not found

        Warning:
            Hard delete permanently removes all customer data.
            Use only for GDPR erasure requests or data retention expiry.
        """
        deleted = await self.repository.delete(
            customer_id,
            hard_delete=hard_delete,
            deletion_reason=deletion_reason,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer with ID {customer_id} not found"
            )

        return True

    # ═══════════════════════════════════════════════════════════════════════
    # GDPR Consent Management (Article 7)
    # ═══════════════════════════════════════════════════════════════════════

    async def update_consent(
        self,
        customer_id: int,
        consent_type: str,
        consent_value: bool,
        consent_version: str = "1.0",
        ip_address: Optional[str] = None,
        consent_method: Optional[str] = None,
    ) -> Customer:
        """
        Update customer consent preferences.

        Args:
            customer_id: Customer ID
            consent_type: Type of consent (marketing, email, phone, sms, data_processing)
            consent_value: True to grant, False to revoke
            consent_version: Version of consent terms
            ip_address: IP address where consent was given/revoked
            consent_method: Method of consent (web_form, email, phone, etc.)

        Returns:
            Updated customer

        Raises:
            HTTPException: If customer not found or invalid consent type
        """
        valid_consent_types = ["marketing", "email", "phone", "sms", "data_processing"]

        if consent_type not in valid_consent_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid consent type. Must be one of: {', '.join(valid_consent_types)}"
            )

        try:
            customer = await self.repository.update_consent(
                customer_id=customer_id,
                consent_type=consent_type,
                consent_value=consent_value,
                consent_version=consent_version,
                ip_address=ip_address,
                consent_method=consent_method,
            )

            if not customer:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Customer with ID {customer_id} not found"
                )

            return customer

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    async def revoke_all_consents(self, customer_id: int) -> Customer:
        """
        Revoke all customer consents (GDPR Article 7(3) - right to withdraw).

        Args:
            customer_id: Customer ID

        Returns:
            Updated customer

        Raises:
            HTTPException: If customer not found
        """
        customer = await self.repository.update(
            customer_id,
            consent_marketing=False,
            email_communication_consent=False,
            phone_communication_consent=False,
            sms_communication_consent=False,
        )

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer with ID {customer_id} not found"
            )

        return customer

    # ═══════════════════════════════════════════════════════════════════════
    # GDPR Data Subject Rights
    # ═══════════════════════════════════════════════════════════════════════

    async def export_customer_data(self, customer_id: int) -> Dict[str, Any]:
        """
        Export all customer data (GDPR Article 15 - Right of Access).

        Args:
            customer_id: Customer ID

        Returns:
            Dictionary with all customer data and related records

        Raises:
            HTTPException: If customer not found

        Note:
            Returns all personal data in a portable format for data subject
            access requests.
        """
        customer = await self.get_customer(customer_id)

        # Get audit logs
        audit_logs = await self.repository.get_audit_logs(customer_id, limit=1000)

        # Build export data
        export_data = {
            "customer_information": {
                "customer_number": customer.customer_number,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "phone": customer.phone,
                "address": {
                    "line1": customer.address_line1,
                    "line2": customer.address_line2,
                    "postal_code": customer.postal_code,
                    "city": customer.city,
                    "country": customer.country,
                },
                "created_at": customer.created_at.isoformat() if customer.created_at else None,
                "updated_at": customer.updated_at.isoformat() if customer.updated_at else None,
            },
            "gdpr_information": {
                "legal_basis": customer.legal_basis,
                "data_retention_category": customer.data_retention_category,
                "retention_deadline": customer.retention_deadline.isoformat() if customer.retention_deadline else None,
            },
            "consent_preferences": {
                "marketing": customer.consent_marketing,
                "email_communication": customer.email_communication_consent,
                "phone_communication": customer.phone_communication_consent,
                "sms_communication": customer.sms_communication_consent,
                "data_processing": customer.data_processing_consent,
                "consent_date": customer.consent_date.isoformat() if customer.consent_date else None,
                "consent_version": customer.consent_version,
                "consent_method": customer.consent_method,
            },
            "audit_trail": [
                {
                    "timestamp": log.timestamp.isoformat(),
                    "action": log.action,
                    "entity": log.entity,
                    "field_name": log.field_name,
                    "user_email": log.user_email,
                }
                for log in audit_logs
            ],
            "export_metadata": {
                "exported_at": datetime.utcnow().isoformat(),
                "export_format": "JSON",
                "gdpr_article": "Article 15 - Right of Access",
            }
        }

        return export_data

    async def anonymize_customer(
        self,
        customer_id: int,
        reason: str = "Data retention period expired",
    ) -> Customer:
        """
        Anonymize customer data (GDPR Article 5(1)(e) - Storage Limitation).

        Args:
            customer_id: Customer ID
            reason: Reason for anonymization

        Returns:
            Anonymized customer

        Raises:
            HTTPException: If customer not found

        Note:
            Replaces all PII with anonymized values while preserving
            statistical data for business analytics.
        """
        customer = await self.get_customer(customer_id)

        # Anonymize personal data
        anonymized_data = {
            "first_name": "ANONYMIZED",
            "last_name": f"USER-{customer_id}",
            "email": f"anonymized-{customer_id}@deleted.local",
            "phone": None,
            "address_line1": None,
            "address_line2": None,
            "postal_code": None,
            "city": None,
            "notes": f"[ANONYMIZED: {reason}]",
            "is_deleted": True,
            "deleted_at": datetime.utcnow(),
            "deletion_reason": reason,
        }

        updated_customer = await self.repository.update(customer_id, **anonymized_data)

        return updated_customer

    # ═══════════════════════════════════════════════════════════════════════
    # GDPR Data Retention (Article 5(1)(e))
    # ═══════════════════════════════════════════════════════════════════════

    async def get_customers_for_retention_review(
        self,
        category: Optional[str] = None,
    ) -> List[Customer]:
        """
        Get customers whose retention deadline has passed.

        Args:
            category: Optional retention category filter

        Returns:
            List of customers ready for deletion/anonymization

        Note:
            These customers should be reviewed and either:
            - Anonymized (if no legal obligation to retain)
            - Retention extended (if ongoing business relationship)
            - Hard deleted (if no longer needed)
        """
        customers = await self.repository.get_customers_for_deletion(category)
        return customers

    async def update_customer_retention(
        self,
        customer_id: int,
        last_order_date: datetime,
        retention_period_days: int = 3650,  # 10 years
    ) -> Customer:
        """
        Update customer retention deadline based on last activity.

        Args:
            customer_id: Customer ID
            last_order_date: Date of last order or activity
            retention_period_days: Retention period in days (default: 10 years)

        Returns:
            Updated customer

        Raises:
            HTTPException: If customer not found
        """
        customer = await self.repository.update_retention_deadline(
            customer_id=customer_id,
            last_order_date=last_order_date,
            retention_period_days=retention_period_days,
        )

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer with ID {customer_id} not found"
            )

        return customer

    # ═══════════════════════════════════════════════════════════════════════
    # Audit Trail (Article 30)
    # ═══════════════════════════════════════════════════════════════════════

    async def get_customer_audit_trail(
        self,
        customer_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List:
        """
        Get audit trail for customer data access.

        Args:
            customer_id: Customer ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of audit log entries

        Raises:
            HTTPException: If customer not found
        """
        # Verify customer exists
        await self.get_customer(customer_id)

        audit_logs = await self.repository.get_audit_logs(
            customer_id=customer_id,
            skip=skip,
            limit=limit,
        )

        return audit_logs

    # ═══════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════

    async def _generate_customer_number(self) -> str:
        """
        Generate unique customer number: CUST-YYYYMM-XXXX

        Returns:
            Unique customer number

        Example:
            CUST-202511-0001
        """
        prefix = f"CUST-{datetime.utcnow().strftime('%Y%m')}"

        # Find last customer number for this month
        # Query all customers with this prefix and get the highest number
        filters = {"customer_number__startswith": prefix}
        customers = await self.repository.get_all(
            skip=0,
            limit=1,
            order_by="-customer_number",
        )

        if customers and customers[0].customer_number.startswith(prefix):
            last_num = int(customers[0].customer_number.split('-')[2])
            new_num = last_num + 1
        else:
            new_num = 1

        return f"{prefix}-{new_num:04d}"

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get customer statistics.

        Returns:
            Dictionary with customer statistics
        """
        # Count total active customers
        total_active = await self.repository.count({"is_deleted": False, "is_active": True})

        # Count total customers (including inactive)
        total_customers = await self.repository.count({"is_deleted": False})

        # Count soft-deleted customers
        total_deleted = await self.repository.count({"is_deleted": True})

        # Count customers by consent status
        marketing_consent = await self.repository.count({
            "is_deleted": False,
            "consent_marketing": True,
        })

        return {
            "total_active_customers": total_active,
            "total_customers": total_customers,
            "total_deleted_customers": total_deleted,
            "marketing_consent_customers": marketing_consent,
        }
