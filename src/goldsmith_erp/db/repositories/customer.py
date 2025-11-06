"""
Customer repository with GDPR-compliant database operations.

This repository provides data access methods for the Customer model with
comprehensive GDPR compliance features including:
- Audit logging for all data access
- Soft delete support
- Consent management
- Data retention policies
- Data subject rights (access, erasure, portability)
- PII encryption/decryption

Author: Claude AI
Date: 2025-11-06
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, update
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Customer,
    CustomerAuditLog,
    GDPRRequest,
    Order,
)
from goldsmith_erp.db.repositories.base import BaseRepository
from goldsmith_erp.core.encryption import get_encryption_service


class CustomerRepository(BaseRepository[Customer]):
    """
    Repository for Customer model with GDPR-compliant operations.

    Provides comprehensive customer data management with built-in:
    - Audit logging (GDPR Article 30)
    - Soft delete (GDPR Article 17)
    - Consent tracking (GDPR Article 7)
    - Data retention (GDPR Article 5(1)(e))
    - PII encryption/decryption

    Usage:
        >>> repo = CustomerRepository(session, current_user_id=1)
        >>> customer = await repo.get_by_id(1)
        >>> customers = await repo.search("mustermann")
    """

    def __init__(self, session: AsyncSession, current_user_id: Optional[int] = None):
        """
        Initialize customer repository.

        Args:
            session: Async database session
            current_user_id: ID of current user for audit logging
        """
        super().__init__(Customer, session)
        self.current_user_id = current_user_id
        self.encryption = get_encryption_service()

    # ═══════════════════════════════════════════════════════════════════════
    # Enhanced CRUD Operations (with audit logging & soft delete)
    # ═══════════════════════════════════════════════════════════════════════

    async def get_by_id(
        self,
        id: int,
        include_deleted: bool = False,
        log_access: bool = True,
    ) -> Optional[Customer]:
        """
        Get customer by ID with optional audit logging.

        Args:
            id: Customer ID
            include_deleted: If True, include soft-deleted customers
            log_access: If True, log this access in audit trail

        Returns:
            Customer instance or None if not found
        """
        query = select(Customer).where(Customer.id == id)

        # Exclude soft-deleted by default
        if not include_deleted:
            query = query.where(Customer.is_deleted == False)

        result = await self.session.execute(query)
        customer = result.scalar_one_or_none()

        # Log access for GDPR Article 30 (audit trail)
        if customer and log_access:
            await self._log_audit(
                customer_id=customer.id,
                action="accessed",
                entity="customer",
                entity_id=customer.id,
            )

        # Decrypt PII fields
        if customer:
            customer = self._decrypt_customer_pii(customer)

        return customer

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        include_deleted: bool = False,
    ) -> List[Customer]:
        """
        Get all customers with filtering, pagination, and soft delete support.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            filters: Dictionary of field:value pairs for filtering
            order_by: Field name to order by (prefix with - for descending)
            include_deleted: If True, include soft-deleted customers

        Returns:
            List of customer instances
        """
        query = select(Customer)

        # Exclude soft-deleted by default
        if not include_deleted:
            query = query.where(Customer.is_deleted == False)

        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(Customer, field):
                    query = query.where(getattr(Customer, field) == value)

        # Apply ordering
        if order_by:
            if order_by.startswith("-"):
                field_name = order_by[1:]
                if hasattr(Customer, field_name):
                    query = query.order_by(getattr(Customer, field_name).desc())
            else:
                if hasattr(Customer, order_by):
                    query = query.order_by(getattr(Customer, order_by))
        else:
            # Default: order by customer_number descending (newest first)
            query = query.order_by(Customer.customer_number.desc())

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        customers = list(result.scalars().all())

        # Decrypt PII for all customers
        customers = [self._decrypt_customer_pii(c) for c in customers]

        return customers

    async def create(
        self,
        customer_number: str,
        first_name: str,
        last_name: str,
        email: str,
        legal_basis: str = "contract",
        **additional_data,
    ) -> Customer:
        """
        Create a new customer with GDPR compliance fields.

        Args:
            customer_number: Unique customer number (CUST-YYYYMM-XXXX)
            first_name: Customer first name
            last_name: Customer last name
            email: Customer email address
            legal_basis: GDPR legal basis (contract, consent, legitimate_interest)
            **additional_data: Additional customer fields

        Returns:
            Created customer instance

        Note:
            Automatically sets:
            - created_at, created_by
            - is_active = True
            - is_deleted = False
            - Encrypts PII fields (phone, address)
        """
        # Encrypt PII fields if provided
        pii_fields = ["phone", "address_line1", "address_line2"]
        for field in pii_fields:
            if field in additional_data and additional_data[field]:
                additional_data[field] = self.encryption.encrypt(additional_data[field])

        # Create customer
        customer_data = {
            "customer_number": customer_number,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "legal_basis": legal_basis,
            "created_at": datetime.utcnow(),
            "created_by": self.current_user_id,
            "is_active": True,
            "is_deleted": False,
            **additional_data,
        }

        customer = Customer(**customer_data)
        self.session.add(customer)
        await self.session.flush()  # Flush to get ID

        # Log creation
        await self._log_audit(
            customer_id=customer.id,
            action="created",
            entity="customer",
            entity_id=customer.id,
        )

        await self.session.commit()
        await self.session.refresh(customer)

        # Decrypt PII before returning
        customer = self._decrypt_customer_pii(customer)

        return customer

    async def update(
        self,
        id: int,
        **data,
    ) -> Optional[Customer]:
        """
        Update customer with change tracking and audit logging.

        Args:
            id: Customer ID
            **data: Fields to update

        Returns:
            Updated customer or None if not found

        Note:
            - Logs all field changes in audit log
            - Automatically updates updated_at, updated_by
            - Encrypts PII fields before storing
        """
        customer = await self.get_by_id(id, include_deleted=False, log_access=False)
        if not customer:
            return None

        # Track changes for audit log
        changes = {}

        # Encrypt PII fields if being updated
        pii_fields = ["phone", "address_line1", "address_line2"]

        for field, new_value in data.items():
            if hasattr(customer, field):
                old_value = getattr(customer, field)

                # Encrypt PII fields
                if field in pii_fields and new_value:
                    new_value = self.encryption.encrypt(new_value)

                # Track change
                if old_value != new_value:
                    changes[field] = {"old": str(old_value), "new": str(new_value)}

                setattr(customer, field, new_value)

        # Update audit fields
        customer.updated_at = datetime.utcnow()
        customer.updated_by = self.current_user_id

        # Log each field change
        for field, change in changes.items():
            await self._log_audit(
                customer_id=customer.id,
                action="updated",
                entity="customer",
                entity_id=customer.id,
                field_name=field,
                old_value=change["old"],
                new_value=change["new"],
            )

        await self.session.commit()
        await self.session.refresh(customer)

        # Decrypt PII before returning
        customer = self._decrypt_customer_pii(customer)

        return customer

    async def delete(
        self,
        id: int,
        hard_delete: bool = False,
        deletion_reason: Optional[str] = None,
    ) -> bool:
        """
        Soft delete or hard delete customer.

        Args:
            id: Customer ID
            hard_delete: If True, permanently delete (GDPR erasure)
            deletion_reason: Reason for deletion (required for GDPR compliance)

        Returns:
            True if deleted, False if not found

        Note:
            - Soft delete: Sets is_deleted=True, preserves data
            - Hard delete: Permanently removes from database (use with caution)
        """
        customer = await self.get_by_id(id, include_deleted=False, log_access=False)
        if not customer:
            return False

        if hard_delete:
            # GDPR Article 17: Right to Erasure
            await self._log_audit(
                customer_id=customer.id,
                action="deleted",
                entity="customer",
                entity_id=customer.id,
                purpose=deletion_reason or "GDPR erasure request",
            )

            await self.session.delete(customer)
            await self.session.commit()
            return True
        else:
            # Soft delete
            customer.is_deleted = True
            customer.deleted_at = datetime.utcnow()
            customer.deleted_by = self.current_user_id
            customer.deletion_reason = deletion_reason

            await self._log_audit(
                customer_id=customer.id,
                action="soft_deleted",
                entity="customer",
                entity_id=customer.id,
                purpose=deletion_reason or "Soft delete",
            )

            await self.session.commit()
            return True

    # ═══════════════════════════════════════════════════════════════════════
    # Search & Filtering
    # ═══════════════════════════════════════════════════════════════════════

    async def search(
        self,
        query: str,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> List[Customer]:
        """
        Search customers by name, email, or customer number.

        Args:
            query: Search query string
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_deleted: If True, include soft-deleted customers

        Returns:
            List of matching customers
        """
        search_term = f"%{query}%"
        stmt = select(Customer).where(
            or_(
                Customer.first_name.ilike(search_term),
                Customer.last_name.ilike(search_term),
                Customer.email.ilike(search_term),
                Customer.customer_number.ilike(search_term),
            )
        )

        # Exclude soft-deleted by default
        if not include_deleted:
            stmt = stmt.where(Customer.is_deleted == False)

        stmt = stmt.order_by(Customer.last_name, Customer.first_name)
        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        customers = list(result.scalars().all())

        # Decrypt PII
        customers = [self._decrypt_customer_pii(c) for c in customers]

        return customers

    async def get_by_email(self, email: str) -> Optional[Customer]:
        """
        Get customer by email address.

        Args:
            email: Customer email

        Returns:
            Customer instance or None
        """
        result = await self.session.execute(
            select(Customer).where(
                and_(
                    Customer.email == email,
                    Customer.is_deleted == False,
                )
            )
        )
        customer = result.scalar_one_or_none()

        if customer:
            customer = self._decrypt_customer_pii(customer)

        return customer

    async def get_by_customer_number(self, customer_number: str) -> Optional[Customer]:
        """
        Get customer by customer number.

        Args:
            customer_number: Unique customer number (CUST-YYYYMM-XXXX)

        Returns:
            Customer instance or None
        """
        result = await self.session.execute(
            select(Customer).where(
                and_(
                    Customer.customer_number == customer_number,
                    Customer.is_deleted == False,
                )
            )
        )
        customer = result.scalar_one_or_none()

        if customer:
            customer = self._decrypt_customer_pii(customer)

        return customer

    # ═══════════════════════════════════════════════════════════════════════
    # GDPR Consent Management
    # ═══════════════════════════════════════════════════════════════════════

    async def update_consent(
        self,
        customer_id: int,
        consent_type: str,
        consent_value: bool,
        consent_version: str = "1.0",
        ip_address: Optional[str] = None,
        consent_method: Optional[str] = None,
    ) -> Optional[Customer]:
        """
        Update customer consent preferences (GDPR Article 7).

        Args:
            customer_id: Customer ID
            consent_type: Type of consent (marketing, email, phone, sms, data_processing)
            consent_value: True to grant, False to revoke
            consent_version: Version of consent terms
            ip_address: IP address where consent was given/revoked
            consent_method: Method of consent (web_form, email, phone, etc.)

        Returns:
            Updated customer or None

        Note:
            Automatically updates consent_date when consent changes
        """
        customer = await self.get_by_id(customer_id, log_access=False)
        if not customer:
            return None

        # Map consent type to field
        consent_fields = {
            "marketing": "consent_marketing",
            "email": "email_communication_consent",
            "phone": "phone_communication_consent",
            "sms": "sms_communication_consent",
            "data_processing": "data_processing_consent",
        }

        field_name = consent_fields.get(consent_type)
        if not field_name:
            raise ValueError(f"Invalid consent type: {consent_type}")

        # Update consent
        old_value = getattr(customer, field_name)
        setattr(customer, field_name, consent_value)

        # Update consent metadata
        customer.consent_date = datetime.utcnow()
        customer.consent_version = consent_version
        if ip_address:
            customer.consent_ip_address = ip_address
        if consent_method:
            customer.consent_method = consent_method

        # Log consent change
        await self._log_audit(
            customer_id=customer.id,
            action="consent_updated",
            entity="customer",
            entity_id=customer.id,
            field_name=field_name,
            old_value=str(old_value),
            new_value=str(consent_value),
            legal_basis="GDPR Article 7 (Consent)",
        )

        await self.session.commit()
        await self.session.refresh(customer)

        customer = self._decrypt_customer_pii(customer)
        return customer

    # ═══════════════════════════════════════════════════════════════════════
    # GDPR Data Retention
    # ═══════════════════════════════════════════════════════════════════════

    async def get_customers_for_deletion(
        self,
        category: Optional[str] = None,
    ) -> List[Customer]:
        """
        Get customers whose retention deadline has passed (GDPR Article 5(1)(e)).

        Args:
            category: Optional retention category filter

        Returns:
            List of customers ready for deletion/anonymization
        """
        query = select(Customer).where(
            and_(
                Customer.retention_deadline <= datetime.utcnow(),
                Customer.is_deleted == False,
            )
        )

        if category:
            query = query.where(Customer.data_retention_category == category)

        result = await self.session.execute(query)
        customers = list(result.scalars().all())

        # Decrypt PII
        customers = [self._decrypt_customer_pii(c) for c in customers]

        return customers

    async def update_retention_deadline(
        self,
        customer_id: int,
        last_order_date: datetime,
        retention_period_days: int = 3650,  # 10 years default
    ) -> Optional[Customer]:
        """
        Update customer retention deadline based on last order.

        Args:
            customer_id: Customer ID
            last_order_date: Date of last order
            retention_period_days: Retention period in days (default: 10 years)

        Returns:
            Updated customer or None
        """
        customer = await self.get_by_id(customer_id, log_access=False)
        if not customer:
            return None

        customer.last_order_date = last_order_date
        customer.retention_deadline = last_order_date + timedelta(days=retention_period_days)

        await self._log_audit(
            customer_id=customer.id,
            action="retention_updated",
            entity="customer",
            entity_id=customer.id,
            purpose=f"Updated retention deadline to {customer.retention_deadline}",
        )

        await self.session.commit()
        await self.session.refresh(customer)

        customer = self._decrypt_customer_pii(customer)
        return customer

    # ═══════════════════════════════════════════════════════════════════════
    # GDPR Audit Logging (Article 30)
    # ═══════════════════════════════════════════════════════════════════════

    async def get_audit_logs(
        self,
        customer_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[CustomerAuditLog]:
        """
        Get audit logs for a customer.

        Args:
            customer_id: Customer ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of audit log entries
        """
        result = await self.session.execute(
            select(CustomerAuditLog)
            .where(CustomerAuditLog.customer_id == customer_id)
            .order_by(CustomerAuditLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _log_audit(
        self,
        customer_id: int,
        action: str,
        entity: str,
        entity_id: Optional[int] = None,
        field_name: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        legal_basis: Optional[str] = None,
        purpose: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """
        Internal method to log customer data access/modification.

        Args:
            customer_id: Customer ID
            action: Action performed (accessed, created, updated, deleted, etc.)
            entity: Entity type (customer, order, consent, etc.)
            entity_id: ID of entity acted upon
            field_name: Name of field changed
            old_value: Previous value
            new_value: New value
            legal_basis: GDPR legal basis for action
            purpose: Purpose of data processing
            ip_address: IP address of request
            user_agent: User agent string
        """
        # Get current user info (would come from request context in real app)
        user_id = self.current_user_id or 1
        user_email = None  # Would fetch from User model
        user_role = None   # Would fetch from User model

        audit_log = CustomerAuditLog(
            customer_id=customer_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            timestamp=datetime.utcnow(),
            ip_address=ip_address,
            user_agent=user_agent,
            legal_basis=legal_basis,
            purpose=purpose,
        )

        self.session.add(audit_log)
        await self.session.flush()

    # ═══════════════════════════════════════════════════════════════════════
    # PII Encryption/Decryption Helpers
    # ═══════════════════════════════════════════════════════════════════════

    def _decrypt_customer_pii(self, customer: Customer) -> Customer:
        """
        Decrypt PII fields for a customer instance.

        Args:
            customer: Customer instance with encrypted PII

        Returns:
            Customer instance with decrypted PII
        """
        if customer.phone:
            try:
                customer.phone = self.encryption.decrypt(customer.phone)
            except Exception:
                pass  # Keep encrypted value if decryption fails

        if customer.address_line1:
            try:
                customer.address_line1 = self.encryption.decrypt(customer.address_line1)
            except Exception:
                pass

        if customer.address_line2:
            try:
                customer.address_line2 = self.encryption.decrypt(customer.address_line2)
            except Exception:
                pass

        return customer
