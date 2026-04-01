"""Customer Service - Business logic for customer/CRM operations"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import Customer as CustomerModel, Order as OrderModel
from goldsmith_erp.models.customer import CustomerCreate, CustomerUpdate
from goldsmith_erp.db.transaction import transactional

logger = logging.getLogger(__name__)

# ── PII encryption helpers ────────────────────────────────────────────────────
# These fields contain GDPR-sensitive personal data and must be encrypted at
# rest when ENCRYPTION_KEY is configured in settings.
PII_FIELDS = ["phone", "mobile", "street", "city", "postal_code"]


def _get_encryption():
    """Return the singleton EncryptionService, or None if not configured."""
    try:
        from goldsmith_erp.core.encryption import get_encryption_service
        return get_encryption_service()
    except Exception:
        return None


def _encrypt_pii(data: dict) -> dict:
    """Encrypt PII fields before writing to DB.

    No-op when ENCRYPTION_KEY is not configured so the app starts without
    encryption in development / migration scenarios.
    """
    enc = _get_encryption()
    if not enc:
        return data
    result = dict(data)
    for field in PII_FIELDS:
        if field in result and result[field]:
            try:
                result[field] = enc.encrypt(result[field])
            except Exception:
                # Keep plaintext if encryption fails rather than losing data
                pass
    return result


def _decrypt_pii(customer: CustomerModel) -> None:
    """Decrypt PII fields in place after reading from DB.

    Silently skips fields that cannot be decrypted — this covers both
    legacy plaintext rows and rows encrypted under a rotated key.
    """
    enc = _get_encryption()
    if not enc:
        return
    for field in PII_FIELDS:
        value = getattr(customer, field, None)
        if value:
            try:
                setattr(customer, field, enc.decrypt(value))
            except Exception:
                # Already plaintext, wrong key, or NULL — leave as-is
                pass


class CustomerService:
    """Service layer for customer management"""

    @staticmethod
    async def get_customers(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        customer_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        tag: Optional[str] = None,
    ) -> List[CustomerModel]:
        """
        Get customers with optional filtering and pagination.

        Uses eager loading to prevent N+1 queries.
        """
        query = select(CustomerModel).options(
            selectinload(CustomerModel.orders)
        )

        # Apply filters
        filters = []

        if search:
            # Search in name, company, email
            search_term = f"%{search}%"
            filters.append(
                or_(
                    CustomerModel.first_name.ilike(search_term),
                    CustomerModel.last_name.ilike(search_term),
                    CustomerModel.company_name.ilike(search_term),
                    CustomerModel.email.ilike(search_term),
                )
            )

        if customer_type:
            filters.append(CustomerModel.customer_type == customer_type)

        if is_active is not None:
            filters.append(CustomerModel.is_active == is_active)

        if tag:
            # JSON array contains tag
            filters.append(CustomerModel.tags.contains([tag]))

        if filters:
            query = query.filter(and_(*filters))

        # Order by created_at desc (newest first)
        query = query.order_by(desc(CustomerModel.created_at))

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        customers = list(result.scalars().all())
        for customer in customers:
            _decrypt_pii(customer)
        return customers

    @staticmethod
    async def get_customer(db: AsyncSession, customer_id: int) -> Optional[CustomerModel]:
        """Get customer by ID with eager loading of relationships"""
        result = await db.execute(
            select(CustomerModel)
            .options(selectinload(CustomerModel.orders))
            .filter(CustomerModel.id == customer_id)
        )
        customer = result.scalar_one_or_none()
        if customer:
            _decrypt_pii(customer)
        return customer

    @staticmethod
    async def get_customer_by_email(db: AsyncSession, email: str) -> Optional[CustomerModel]:
        """Get customer by email address"""
        result = await db.execute(
            select(CustomerModel).filter(CustomerModel.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_customer(db: AsyncSession, customer_in: CustomerCreate) -> CustomerModel:
        """
        Create a new customer with transactional guarantees.

        Validates that email is unique.
        """
        async with transactional(db):
            # Check if email already exists
            existing = await CustomerService.get_customer_by_email(db, customer_in.email)
            if existing:
                raise ValueError("Ein Kunde mit dieser E-Mail-Adresse existiert bereits")

            # Encrypt PII before persisting to DB
            customer_data = _encrypt_pii(customer_in.model_dump())
            db_customer = CustomerModel(**customer_data)

            db.add(db_customer)
            await db.flush()
            await db.refresh(db_customer)

        # Decrypt for the response payload — never log PII in plaintext
        _decrypt_pii(db_customer)
        logger.info(
            "Customer created",
            extra={
                "customer_id": db_customer.id,
                # email intentionally omitted — PII must not appear in logs
                "customer_type": db_customer.customer_type,
            }
        )

        return db_customer

    @staticmethod
    async def update_customer(
        db: AsyncSession,
        customer_id: int,
        customer_update: CustomerUpdate
    ) -> Optional[CustomerModel]:
        """
        Update customer with transactional guarantees.

        Only updates fields that are provided (not None).
        """
        async with transactional(db):
            # Get existing customer
            db_customer = await CustomerService.get_customer(db, customer_id)
            if not db_customer:
                return None

            # Update only provided fields
            update_data = customer_update.model_dump(exclude_unset=True)

            # Check email uniqueness if email is being updated
            if 'email' in update_data and update_data['email'] != db_customer.email:
                existing = await CustomerService.get_customer_by_email(db, update_data['email'])
                if existing:
                    raise ValueError("Ein Kunde mit dieser E-Mail-Adresse existiert bereits")

            # Encrypt PII fields before writing to DB
            update_data = _encrypt_pii(update_data)

            # Apply updates
            for field, value in update_data.items():
                setattr(db_customer, field, value)

            db_customer.updated_at = datetime.utcnow()
            await db.flush()
            await db.refresh(db_customer)

        # Decrypt for the response payload
        _decrypt_pii(db_customer)
        logger.info(
            "Customer updated",
            extra={
                "customer_id": customer_id,
                "updated_fields": list(update_data.keys()),
            }
        )

        return db_customer

    @staticmethod
    async def delete_customer(db: AsyncSession, customer_id: int) -> bool:
        """
        Soft delete a customer (sets is_active = False).

        Does not delete customers with active orders.
        """
        async with transactional(db):
            db_customer = await CustomerService.get_customer(db, customer_id)
            if not db_customer:
                return False

            # Check if customer has orders
            order_count = await CustomerService.get_customer_order_count(db, customer_id)
            if order_count > 0:
                raise ValueError(
                    f"Cannot delete customer with {order_count} orders. "
                    "Please use soft delete (set is_active=False) instead."
                )

            # Soft delete
            db_customer.is_active = False
            db_customer.updated_at = datetime.utcnow()
            await db.flush()

        logger.info("Customer soft deleted", extra={"customer_id": customer_id})
        return True

    @staticmethod
    async def get_customer_order_count(db: AsyncSession, customer_id: int) -> int:
        """Get total number of orders for a customer"""
        result = await db.execute(
            select(func.count(OrderModel.id))
            .filter(OrderModel.customer_id == customer_id)
        )
        return result.scalar() or 0

    @staticmethod
    async def get_customer_stats(db: AsyncSession, customer_id: int) -> Dict[str, Any]:
        """
        Get customer statistics including order count, total spent, last order.
        """
        # Get order statistics
        result = await db.execute(
            select(
                func.count(OrderModel.id).label('order_count'),
                func.sum(OrderModel.price).label('total_spent'),
                func.max(OrderModel.created_at).label('last_order_date'),
            )
            .filter(OrderModel.customer_id == customer_id)
        )
        stats = result.one()

        return {
            "customer_id": customer_id,
            "order_count": stats.order_count or 0,
            "total_spent": float(stats.total_spent or 0),
            "last_order_date": stats.last_order_date,
        }

    @staticmethod
    async def search_customers(
        db: AsyncSession,
        query: str,
        limit: int = 10
    ) -> List[CustomerModel]:
        """
        Fast customer search for autocomplete.

        Searches by name, company, email.

        NOTE — encrypted field limitation: phone, mobile, street, city and
        postal_code are stored as Fernet ciphertext when ENCRYPTION_KEY is set.
        ILIKE cannot match encrypted values, so those fields are intentionally
        excluded from the WHERE clause here.  If full-address search becomes a
        requirement, implement a separate deterministic-hash index column for
        each encrypted field (HMAC-SHA256 of the normalised plaintext) and
        filter on the hash instead.
        """
        search_term = f"%{query}%"
        result = await db.execute(
            select(CustomerModel)
            .filter(
                and_(
                    CustomerModel.is_active == True,
                    or_(
                        CustomerModel.first_name.ilike(search_term),
                        CustomerModel.last_name.ilike(search_term),
                        CustomerModel.company_name.ilike(search_term),
                        CustomerModel.email.ilike(search_term),
                    )
                )
            )
            .order_by(CustomerModel.last_name, CustomerModel.first_name)
            .limit(limit)
        )
        customers = list(result.scalars().all())
        for customer in customers:
            _decrypt_pii(customer)
        return customers

    @staticmethod
    async def get_top_customers(
        db: AsyncSession,
        limit: int = 10,
        by: str = "revenue"  # revenue, orders, recent
    ) -> List[Dict[str, Any]]:
        """
        Get top customers by different criteria.

        Args:
            by: 'revenue' (total spent), 'orders' (order count), 'recent' (last order)
        """
        if by == "revenue":
            # Top customers by total revenue
            result = await db.execute(
                select(
                    CustomerModel,
                    func.sum(OrderModel.price).label('total_spent')
                )
                .join(OrderModel, CustomerModel.id == OrderModel.customer_id)
                .filter(CustomerModel.is_active == True)
                .group_by(CustomerModel.id)
                .order_by(desc('total_spent'))
                .limit(limit)
            )
        elif by == "orders":
            # Top customers by order count
            result = await db.execute(
                select(
                    CustomerModel,
                    func.count(OrderModel.id).label('order_count')
                )
                .join(OrderModel, CustomerModel.id == OrderModel.customer_id)
                .filter(CustomerModel.is_active == True)
                .group_by(CustomerModel.id)
                .order_by(desc('order_count'))
                .limit(limit)
            )
        else:  # recent
            # Customers with most recent orders
            result = await db.execute(
                select(
                    CustomerModel,
                    func.max(OrderModel.created_at).label('last_order')
                )
                .join(OrderModel, CustomerModel.id == OrderModel.customer_id)
                .filter(CustomerModel.is_active == True)
                .group_by(CustomerModel.id)
                .order_by(desc('last_order'))
                .limit(limit)
            )

        rows = result.all()
        customers = []
        for row in rows:
            customer = row[0]
            stat_value = row[1]
            customers.append({
                "customer": customer,
                "stat_value": stat_value,
                "stat_type": by
            })

        return customers
