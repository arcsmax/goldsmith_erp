"""
Order repository with comprehensive order management (Phase 1.8).

This repository provides data access methods for Order, OrderItem, and
OrderStatusHistory models with features including:
- Complete order lifecycle management
- Order item (material) tracking with allocation
- Status history tracking with audit trail
- Soft delete support
- Cost calculations
- Statistics and reporting

Author: Claude AI
Date: 2025-11-06
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, update
from sqlalchemy.orm import selectinload, joinedload

from goldsmith_erp.db.models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    Customer,
    Material,
    User,
)
from goldsmith_erp.db.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    """
    Repository for Order model with comprehensive order management.

    Provides complete order lifecycle management with built-in:
    - Order item (material) tracking
    - Status history with audit trail
    - Soft delete support
    - Cost calculations
    - Statistics and reporting

    Usage:
        >>> repo = OrderRepository(session, current_user_id=1)
        >>> order = await repo.get_by_id_with_items(1)
        >>> orders = await repo.list_orders(status="in_progress")
    """

    def __init__(self, session: AsyncSession, current_user_id: Optional[int] = None):
        """
        Initialize order repository.

        Args:
            session: Async database session
            current_user_id: ID of current user for audit logging
        """
        super().__init__(Order, session)
        self.current_user_id = current_user_id

    # ═══════════════════════════════════════════════════════════════════════
    # Enhanced CRUD Operations (with soft delete)
    # ═══════════════════════════════════════════════════════════════════════

    async def get_by_id(
        self,
        id: int,
        include_deleted: bool = False,
    ) -> Optional[Order]:
        """
        Get order by ID.

        Args:
            id: Order ID
            include_deleted: If True, include soft-deleted orders

        Returns:
            Order instance or None if not found
        """
        query = select(Order).where(Order.id == id)

        # Exclude soft-deleted by default
        if not include_deleted:
            query = query.where(Order.is_deleted == False)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_with_items(
        self,
        id: int,
        include_deleted: bool = False,
    ) -> Optional[Order]:
        """
        Get order by ID with order items and status history loaded.

        Args:
            id: Order ID
            include_deleted: If True, include soft-deleted orders

        Returns:
            Order instance with relationships loaded, or None if not found
        """
        query = (
            select(Order)
            .where(Order.id == id)
            .options(
                selectinload(Order.order_items).selectinload(OrderItem.material),
                selectinload(Order.status_history).selectinload(OrderStatusHistory.user),
                selectinload(Order.customer),
                selectinload(Order.assigned_user),
            )
        )

        if not include_deleted:
            query = query.where(Order.is_deleted == False)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_order_number(
        self,
        order_number: str,
        include_deleted: bool = False,
    ) -> Optional[Order]:
        """
        Get order by order number.

        Args:
            order_number: Order number (e.g., ORD-202501-0001)
            include_deleted: If True, include soft-deleted orders

        Returns:
            Order instance or None if not found
        """
        query = select(Order).where(Order.order_number == order_number)

        if not include_deleted:
            query = query.where(Order.is_deleted == False)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_orders(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        order_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        assigned_to: Optional[int] = None,
        include_deleted: bool = False,
        order_by: Optional[str] = None,
    ) -> List[Order]:
        """
        List orders with optional filtering and pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            status: Filter by status
            priority: Filter by priority
            order_type: Filter by order type
            customer_id: Filter by customer ID
            assigned_to: Filter by assigned user ID
            include_deleted: If True, include soft-deleted orders
            order_by: Field to order by (prefix with - for descending)

        Returns:
            List of orders
        """
        query = select(Order).options(
            selectinload(Order.customer),
            selectinload(Order.assigned_user),
        )

        # Apply filters
        if not include_deleted:
            query = query.where(Order.is_deleted == False)
        if status:
            query = query.where(Order.status == status)
        if priority:
            query = query.where(Order.priority == priority)
        if order_type:
            query = query.where(Order.order_type == order_type)
        if customer_id:
            query = query.where(Order.customer_id == customer_id)
        if assigned_to:
            query = query.where(Order.assigned_to == assigned_to)

        # Apply ordering
        if order_by:
            if order_by.startswith("-"):
                field_name = order_by[1:]
                if hasattr(Order, field_name):
                    query = query.order_by(getattr(Order, field_name).desc())
            else:
                if hasattr(Order, order_by):
                    query = query.order_by(getattr(Order, order_by))
        else:
            # Default: order by created_at descending (newest first)
            query = query.order_by(Order.created_at.desc())

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_orders(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        order_type: Optional[str] = None,
        customer_id: Optional[int] = None,
        assigned_to: Optional[int] = None,
        include_deleted: bool = False,
    ) -> int:
        """
        Count orders matching filters.

        Args:
            status: Filter by status
            priority: Filter by priority
            order_type: Filter by order type
            customer_id: Filter by customer ID
            assigned_to: Filter by assigned user ID
            include_deleted: If True, include soft-deleted orders

        Returns:
            Count of matching orders
        """
        query = select(func.count(Order.id))

        # Apply filters
        if not include_deleted:
            query = query.where(Order.is_deleted == False)
        if status:
            query = query.where(Order.status == status)
        if priority:
            query = query.where(Order.priority == priority)
        if order_type:
            query = query.where(Order.order_type == order_type)
        if customer_id:
            query = query.where(Order.customer_id == customer_id)
        if assigned_to:
            query = query.where(Order.assigned_to == assigned_to)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def create_order(
        self,
        customer_id: int,
        title: str,
        description: Optional[str] = None,
        order_type: str = "custom_jewelry",
        priority: str = "normal",
        estimated_completion_date: Optional[datetime] = None,
        delivery_date: Optional[datetime] = None,
        estimated_hours: Optional[float] = None,
        hourly_rate: Optional[float] = None,
        customer_price: Optional[float] = None,
        tax_rate: float = 19.0,
        currency: str = "EUR",
        assigned_to: Optional[int] = None,
        notes: Optional[str] = None,
        customer_notes: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Order:
        """
        Create a new order with generated order number.

        Args:
            customer_id: Customer ID
            title: Order title
            description: Detailed description
            order_type: Type of order (custom_jewelry, repair, etc.)
            priority: Priority (low, normal, high, urgent)
            estimated_completion_date: Estimated completion date
            delivery_date: Promised delivery date
            estimated_hours: Estimated labor hours
            hourly_rate: Hourly rate for labor
            customer_price: Price quoted to customer
            tax_rate: Tax rate percentage (default 19%)
            currency: Currency code (default EUR)
            assigned_to: Assigned user ID
            notes: Internal notes
            customer_notes: Customer-facing notes
            attachments: File attachments

        Returns:
            Created order instance
        """
        # Generate order number
        order_number = await self._generate_order_number()

        # Calculate labor cost if both hours and rate provided
        labor_cost = 0.0
        if estimated_hours and hourly_rate:
            labor_cost = estimated_hours * hourly_rate

        # Create order
        order = Order(
            order_number=order_number,
            customer_id=customer_id,
            title=title,
            description=description,
            order_type=order_type,
            priority=priority,
            status="draft",
            estimated_completion_date=estimated_completion_date,
            delivery_date=delivery_date,
            estimated_hours=estimated_hours,
            actual_hours=0.0,
            hourly_rate=hourly_rate,
            labor_cost=labor_cost,
            customer_price=customer_price or 0.0,
            tax_rate=tax_rate,
            currency=currency,
            assigned_to=assigned_to,
            notes=notes,
            customer_notes=customer_notes,
            attachments=attachments or [],
            created_by=self.current_user_id,
            updated_by=self.current_user_id,
        )

        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)

        # Create initial status history entry
        await self.add_status_history(
            order_id=order.id,
            old_status=None,
            new_status="draft",
            reason="Order created",
        )

        return order

    async def update_order(
        self,
        order_id: int,
        **updates
    ) -> Optional[Order]:
        """
        Update an order.

        Args:
            order_id: Order ID
            **updates: Fields to update

        Returns:
            Updated order or None if not found
        """
        order = await self.get_by_id(order_id)
        if not order:
            return None

        # Add updated_by and updated_at
        updates["updated_by"] = self.current_user_id
        updates["updated_at"] = datetime.utcnow()

        # Update fields
        for field, value in updates.items():
            if hasattr(order, field):
                setattr(order, field, value)

        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def soft_delete_order(
        self,
        order_id: int,
    ) -> Optional[Order]:
        """
        Soft delete an order.

        Args:
            order_id: Order ID

        Returns:
            Updated order or None if not found
        """
        order = await self.get_by_id(order_id)
        if not order:
            return None

        order.is_deleted = True
        order.deleted_at = datetime.utcnow()
        order.deleted_by = self.current_user_id
        order.updated_by = self.current_user_id
        order.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(order)
        return order

    # ═══════════════════════════════════════════════════════════════════════
    # OrderItem Operations
    # ═══════════════════════════════════════════════════════════════════════

    async def add_order_item(
        self,
        order_id: int,
        material_id: int,
        quantity_planned: float,
        unit: str,
        unit_price: float,
        notes: Optional[str] = None,
    ) -> OrderItem:
        """
        Add a material to an order.

        Args:
            order_id: Order ID
            material_id: Material ID
            quantity_planned: Planned quantity to use
            unit: Unit of measurement
            unit_price: Unit price at time of order
            notes: Notes about material usage

        Returns:
            Created order item
        """
        order_item = OrderItem(
            order_id=order_id,
            material_id=material_id,
            quantity_planned=quantity_planned,
            quantity_used=0.0,
            unit=unit,
            unit_price=unit_price,
            total_cost=0.0,
            notes=notes,
        )

        self.session.add(order_item)
        await self.session.commit()
        await self.session.refresh(order_item)

        # Recalculate order costs
        await self._recalculate_order_costs(order_id)

        return order_item

    async def update_order_item(
        self,
        order_item_id: int,
        **updates
    ) -> Optional[OrderItem]:
        """
        Update an order item.

        Args:
            order_item_id: Order item ID
            **updates: Fields to update

        Returns:
            Updated order item or None if not found
        """
        result = await self.session.execute(
            select(OrderItem).where(OrderItem.id == order_item_id)
        )
        order_item = result.scalar_one_or_none()

        if not order_item:
            return None

        # Update fields
        for field, value in updates.items():
            if hasattr(order_item, field):
                setattr(order_item, field, value)

        # Recalculate total cost if quantity_used changed
        if "quantity_used" in updates:
            order_item.total_cost = order_item.quantity_used * order_item.unit_price

        await self.session.commit()
        await self.session.refresh(order_item)

        # Recalculate order costs
        await self._recalculate_order_costs(order_item.order_id)

        return order_item

    async def allocate_material(
        self,
        order_item_id: int,
    ) -> Optional[OrderItem]:
        """
        Mark materials as allocated for an order item.

        Args:
            order_item_id: Order item ID

        Returns:
            Updated order item or None if not found
        """
        return await self.update_order_item(
            order_item_id,
            is_allocated=True,
            allocated_at=datetime.utcnow(),
        )

    async def mark_material_used(
        self,
        order_item_id: int,
        quantity_used: float,
        notes: Optional[str] = None,
    ) -> Optional[OrderItem]:
        """
        Mark materials as used in production.

        Args:
            order_item_id: Order item ID
            quantity_used: Actual quantity used
            notes: Notes about usage

        Returns:
            Updated order item or None if not found
        """
        updates = {
            "quantity_used": quantity_used,
            "is_used": True,
            "used_at": datetime.utcnow(),
        }
        if notes:
            updates["notes"] = notes

        return await self.update_order_item(order_item_id, **updates)

    async def remove_order_item(
        self,
        order_item_id: int,
    ) -> bool:
        """
        Remove an order item.

        Args:
            order_item_id: Order item ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            select(OrderItem).where(OrderItem.id == order_item_id)
        )
        order_item = result.scalar_one_or_none()

        if not order_item:
            return False

        order_id = order_item.order_id
        await self.session.delete(order_item)
        await self.session.commit()

        # Recalculate order costs
        await self._recalculate_order_costs(order_id)

        return True

    # ═══════════════════════════════════════════════════════════════════════
    # Status History Operations
    # ═══════════════════════════════════════════════════════════════════════

    async def add_status_history(
        self,
        order_id: int,
        old_status: Optional[str],
        new_status: str,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> OrderStatusHistory:
        """
        Add a status history entry.

        Args:
            order_id: Order ID
            old_status: Previous status
            new_status: New status
            reason: Reason for status change
            notes: Additional notes
            ip_address: IP address of user making change
            user_agent: User agent of request

        Returns:
            Created status history entry
        """
        status_history = OrderStatusHistory(
            order_id=order_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=self.current_user_id or 0,
            reason=reason,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.session.add(status_history)
        await self.session.commit()
        await self.session.refresh(status_history)

        return status_history

    async def change_order_status(
        self,
        order_id: int,
        new_status: str,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[Order]:
        """
        Change order status with history tracking.

        Args:
            order_id: Order ID
            new_status: New status
            reason: Reason for status change
            notes: Additional notes
            ip_address: IP address
            user_agent: User agent

        Returns:
            Updated order or None if not found
        """
        order = await self.get_by_id(order_id)
        if not order:
            return None

        old_status = order.status

        # Add status history
        await self.add_status_history(
            order_id=order_id,
            old_status=old_status,
            new_status=new_status,
            reason=reason,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Update order status and date fields
        updates = {"status": new_status}

        if new_status == "in_progress" and not order.started_at:
            updates["started_at"] = datetime.utcnow()
        elif new_status == "completed":
            updates["completed_at"] = datetime.utcnow()
            updates["actual_completion_date"] = datetime.utcnow()
        elif new_status == "delivered":
            updates["delivered_at"] = datetime.utcnow()
        elif new_status == "cancelled":
            updates["cancelled_at"] = datetime.utcnow()

        return await self.update_order(order_id, **updates)

    # ═══════════════════════════════════════════════════════════════════════
    # Cost Calculations
    # ═══════════════════════════════════════════════════════════════════════

    async def _recalculate_order_costs(
        self,
        order_id: int,
    ) -> None:
        """
        Recalculate order costs based on order items and labor.

        Args:
            order_id: Order ID
        """
        order = await self.get_by_id_with_items(order_id)
        if not order:
            return

        # Calculate material cost from order items
        material_cost = sum(item.total_cost for item in order.order_items)

        # Calculate labor cost
        labor_cost = 0.0
        if order.actual_hours and order.hourly_rate:
            labor_cost = order.actual_hours * order.hourly_rate
        elif order.estimated_hours and order.hourly_rate:
            labor_cost = order.estimated_hours * order.hourly_rate

        # Calculate totals
        total_cost = material_cost + labor_cost + (order.additional_cost or 0.0)
        margin = (order.customer_price or 0.0) - total_cost

        # Calculate tax
        subtotal = order.customer_price or 0.0
        tax_amount = subtotal * (order.tax_rate / 100)
        total_amount = subtotal + tax_amount

        # Update order
        order.material_cost = material_cost
        order.labor_cost = labor_cost
        order.total_cost = total_cost
        order.margin = margin
        order.subtotal = subtotal
        order.tax_amount = tax_amount
        order.total_amount = total_amount
        order.updated_by = self.current_user_id
        order.updated_at = datetime.utcnow()

        await self.session.commit()

    # ═══════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════

    async def _generate_order_number(self) -> str:
        """
        Generate a unique order number in format: ORD-YYYYMM-XXXX

        Returns:
            Unique order number
        """
        now = datetime.utcnow()
        prefix = f"ORD-{now.strftime('%Y%m')}"

        # Get count of orders this month
        result = await self.session.execute(
            select(func.count(Order.id))
            .where(Order.order_number.like(f"{prefix}%"))
        )
        count = result.scalar_one()

        # Generate order number
        order_number = f"{prefix}-{(count + 1):04d}"

        return order_number

    # ═══════════════════════════════════════════════════════════════════════
    # Statistics & Reporting
    # ═══════════════════════════════════════════════════════════════════════

    async def get_order_statistics(self) -> Dict[str, Any]:
        """
        Get order statistics for dashboard and reporting.

        Returns:
            Dictionary with order statistics
        """
        # Count orders by status
        total_orders = await self.count_orders()
        draft_orders = await self.count_orders(status="draft")
        in_progress_orders = await self.count_orders(status="in_progress")
        completed_orders = await self.count_orders(status="completed")
        delivered_orders = await self.count_orders(status="delivered")
        cancelled_orders = await self.count_orders(status="cancelled")

        # Calculate revenue and profit (delivered orders only)
        revenue_result = await self.session.execute(
            select(
                func.sum(Order.customer_price).label("total_revenue"),
                func.sum(Order.total_cost).label("total_costs"),
            )
            .where(Order.status == "delivered")
            .where(Order.is_deleted == False)
        )
        revenue_row = revenue_result.first()
        total_revenue = revenue_row.total_revenue or 0.0
        total_costs = revenue_row.total_costs or 0.0
        total_profit = total_revenue - total_costs

        # Calculate average margin
        if delivered_orders > 0:
            average_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0.0
        else:
            average_margin = 0.0

        # Count overdue orders (past estimated_completion_date)
        overdue_result = await self.session.execute(
            select(func.count(Order.id))
            .where(Order.estimated_completion_date < datetime.utcnow())
            .where(Order.status.in_(["draft", "approved", "in_progress"]))
            .where(Order.is_deleted == False)
        )
        overdue_orders = overdue_result.scalar_one()

        # Count urgent orders
        urgent_orders = await self.count_orders(priority="urgent")

        return {
            "total_orders": total_orders,
            "draft_orders": draft_orders,
            "in_progress_orders": in_progress_orders,
            "completed_orders": completed_orders,
            "delivered_orders": delivered_orders,
            "cancelled_orders": cancelled_orders,
            "total_revenue": total_revenue,
            "total_costs": total_costs,
            "total_profit": total_profit,
            "average_margin": average_margin,
            "overdue_orders": overdue_orders,
            "urgent_orders": urgent_orders,
        }
