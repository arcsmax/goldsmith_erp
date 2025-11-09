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
        return result.scalars().all()

    @staticmethod
    async def get_customer(db: AsyncSession, customer_id: int) -> Optional[CustomerModel]:
        """Get customer by ID with eager loading of relationships"""
        result = await db.execute(
            select(CustomerModel)
            .options(selectinload(CustomerModel.orders))
            .filter(CustomerModel.id == customer_id)
        )
        return result.scalar_one_or_none()

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
                raise ValueError(f"Customer with email {customer_in.email} already exists")

            # Create customer
            customer_data = customer_in.model_dump()
            db_customer = CustomerModel(**customer_data)

            db.add(db_customer)
            await db.flush()
            await db.refresh(db_customer)

        logger.info(
            "Customer created",
            extra={
                "customer_id": db_customer.id,
                "email": db_customer.email,
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
                    raise ValueError(f"Customer with email {update_data['email']} already exists")

            # Apply updates
            for field, value in update_data.items():
                setattr(db_customer, field, value)

            db_customer.updated_at = datetime.utcnow()
            await db.flush()
            await db.refresh(db_customer)

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
        return result.scalars().all()

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
