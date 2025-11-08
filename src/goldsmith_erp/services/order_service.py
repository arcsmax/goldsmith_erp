"""
Order service with comprehensive business logic (Phase 1.8).

This service provides business logic for order management including:
- Order lifecycle management (draft → delivered)
- Order item (material) management
- Status workflow validation
- Material allocation and usage tracking
- Cost calculations and validation
- Statistics and reporting

Author: Claude AI
Date: 2025-11-06
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status

from goldsmith_erp.db.repositories.order import OrderRepository
from goldsmith_erp.db.models import Order, OrderItem, OrderStatusHistory


class OrderService:
    """
    Service for order business logic.

    Provides comprehensive order management with:
    - Order lifecycle management
    - Status workflow validation
    - Material allocation and tracking
    - Cost calculations
    - Statistics and reporting

    Usage:
        >>> service = OrderService(repository)
        >>> order = await service.get_order(1)
        >>> order = await service.create_order(customer_id=1, title="Custom Ring", ...)
    """

    # Valid status transitions
    VALID_STATUS_TRANSITIONS = {
        "draft": ["approved", "cancelled"],
        "approved": ["in_progress", "cancelled"],
        "in_progress": ["completed", "cancelled"],
        "completed": ["delivered"],
        "delivered": [],  # Final state
        "cancelled": [],  # Final state
    }

    # Valid order types
    VALID_ORDER_TYPES = [
        "custom_jewelry",
        "repair",
        "modification",
        "resizing",
        "cleaning",
    ]

    # Valid priorities
    VALID_PRIORITIES = ["low", "normal", "high", "urgent"]

    def __init__(self, repository: OrderRepository):
        """
        Initialize service.

        Args:
            repository: Order repository instance
        """
        self.repository = repository

    # ═══════════════════════════════════════════════════════════════════════
    # Basic CRUD Operations
    # ═══════════════════════════════════════════════════════════════════════

    async def get_order(
        self,
        order_id: int,
        include_deleted: bool = False,
        include_items: bool = True,
    ) -> Order:
        """
        Get an order by ID.

        Args:
            order_id: Order ID
            include_deleted: If True, include soft-deleted orders
            include_items: If True, load order items and status history

        Returns:
            Order instance

        Raises:
            HTTPException: If order not found
        """
        if include_items:
            order = await self.repository.get_by_id_with_items(
                order_id,
                include_deleted=include_deleted,
            )
        else:
            order = await self.repository.get_by_id(
                order_id,
                include_deleted=include_deleted,
            )

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with ID {order_id} not found"
            )

        return order

    async def get_order_by_number(
        self,
        order_number: str,
        include_deleted: bool = False,
    ) -> Order:
        """
        Get order by order number.

        Args:
            order_number: Order number (e.g., ORD-202501-0001)
            include_deleted: If True, include soft-deleted orders

        Returns:
            Order instance

        Raises:
            HTTPException: If order not found
        """
        order = await self.repository.get_by_order_number(
            order_number,
            include_deleted=include_deleted,
        )

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with number {order_number} not found"
            )

        return order

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
            limit: Maximum number of records to return (max 1000)
            status: Filter by status
            priority: Filter by priority
            order_type: Filter by order type
            customer_id: Filter by customer ID
            assigned_to: Filter by assigned user ID
            include_deleted: If True, include soft-deleted orders
            order_by: Field to order by (prefix with - for descending)

        Returns:
            List of orders

        Raises:
            HTTPException: If validation fails
        """
        # Validate limit
        if limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit cannot exceed 1000"
            )

        # Validate filters
        if status and status not in ["draft", "approved", "in_progress", "completed", "delivered", "cancelled"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}"
            )

        if priority and priority not in self.VALID_PRIORITIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority: {priority}. Must be one of: {', '.join(self.VALID_PRIORITIES)}"
            )

        if order_type and order_type not in self.VALID_ORDER_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid order type: {order_type}. Must be one of: {', '.join(self.VALID_ORDER_TYPES)}"
            )

        return await self.repository.list_orders(
            skip=skip,
            limit=limit,
            status=status,
            priority=priority,
            order_type=order_type,
            customer_id=customer_id,
            assigned_to=assigned_to,
            include_deleted=include_deleted,
            order_by=order_by,
        )

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
        return await self.repository.count_orders(
            status=status,
            priority=priority,
            order_type=order_type,
            customer_id=customer_id,
            assigned_to=assigned_to,
            include_deleted=include_deleted,
        )

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
        Create a new order with validation.

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
            Created order

        Raises:
            HTTPException: If validation fails
        """
        # Validate order type
        if order_type not in self.VALID_ORDER_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid order type: {order_type}. Must be one of: {', '.join(self.VALID_ORDER_TYPES)}"
            )

        # Validate priority
        if priority not in self.VALID_PRIORITIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority: {priority}. Must be one of: {', '.join(self.VALID_PRIORITIES)}"
            )

        # Validate numeric values
        if estimated_hours is not None and estimated_hours <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Estimated hours must be greater than 0"
            )

        if hourly_rate is not None and hourly_rate < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Hourly rate cannot be negative"
            )

        if customer_price is not None and customer_price < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer price cannot be negative"
            )

        if tax_rate < 0 or tax_rate > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tax rate must be between 0 and 100"
            )

        # Validate dates
        if estimated_completion_date and estimated_completion_date < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Estimated completion date cannot be in the past"
            )

        if delivery_date and delivery_date < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Delivery date cannot be in the past"
            )

        # Create order
        return await self.repository.create_order(
            customer_id=customer_id,
            title=title,
            description=description,
            order_type=order_type,
            priority=priority,
            estimated_completion_date=estimated_completion_date,
            delivery_date=delivery_date,
            estimated_hours=estimated_hours,
            hourly_rate=hourly_rate,
            customer_price=customer_price,
            tax_rate=tax_rate,
            currency=currency,
            assigned_to=assigned_to,
            notes=notes,
            customer_notes=customer_notes,
            attachments=attachments,
        )

    async def update_order(
        self,
        order_id: int,
        **updates
    ) -> Order:
        """
        Update an order with validation.

        Args:
            order_id: Order ID
            **updates: Fields to update

        Returns:
            Updated order

        Raises:
            HTTPException: If order not found or validation fails
        """
        # Check order exists
        order = await self.get_order(order_id, include_items=False)

        # Validate order type if provided
        if "order_type" in updates and updates["order_type"] not in self.VALID_ORDER_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid order type: {updates['order_type']}"
            )

        # Validate priority if provided
        if "priority" in updates and updates["priority"] not in self.VALID_PRIORITIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority: {updates['priority']}"
            )

        # Validate numeric values
        if "estimated_hours" in updates and updates["estimated_hours"] is not None and updates["estimated_hours"] <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Estimated hours must be greater than 0"
            )

        if "customer_price" in updates and updates["customer_price"] is not None and updates["customer_price"] < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer price cannot be negative"
            )

        # Update order
        updated_order = await self.repository.update_order(order_id, **updates)

        if not updated_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with ID {order_id} not found"
            )

        return updated_order

    async def delete_order(
        self,
        order_id: int,
    ) -> Order:
        """
        Soft delete an order.

        Args:
            order_id: Order ID

        Returns:
            Deleted order

        Raises:
            HTTPException: If order not found or cannot be deleted
        """
        # Check order exists
        order = await self.get_order(order_id, include_items=False)

        # Check if order can be deleted (not delivered)
        if order.status == "delivered":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete delivered orders. Please contact administrator."
            )

        # Soft delete
        deleted_order = await self.repository.soft_delete_order(order_id)

        if not deleted_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with ID {order_id} not found"
            )

        return deleted_order

    # ═══════════════════════════════════════════════════════════════════════
    # Status Management
    # ═══════════════════════════════════════════════════════════════════════

    async def change_order_status(
        self,
        order_id: int,
        new_status: str,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Order:
        """
        Change order status with workflow validation.

        Args:
            order_id: Order ID
            new_status: New status
            reason: Reason for status change
            notes: Additional notes
            ip_address: IP address
            user_agent: User agent

        Returns:
            Updated order

        Raises:
            HTTPException: If order not found or transition is invalid
        """
        # Get current order
        order = await self.get_order(order_id, include_items=False)

        # Validate status transition
        if new_status not in self.VALID_STATUS_TRANSITIONS.get(order.status, []):
            valid_transitions = ", ".join(self.VALID_STATUS_TRANSITIONS.get(order.status, []))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition from '{order.status}' to '{new_status}'. "
                       f"Valid transitions: {valid_transitions or 'none (final state)'}"
            )

        # Additional validation for specific transitions
        if new_status == "in_progress":
            # Check if materials are allocated
            order_with_items = await self.get_order(order_id, include_items=True)
            if order_with_items.order_items:
                unallocated_items = [item for item in order_with_items.order_items if not item.is_allocated]
                if unallocated_items:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot start order: not all materials are allocated"
                    )

        if new_status == "completed":
            # Check if materials are marked as used
            order_with_items = await self.get_order(order_id, include_items=True)
            if order_with_items.order_items:
                unused_items = [item for item in order_with_items.order_items if not item.is_used]
                if unused_items:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot complete order: not all materials are marked as used"
                    )

        # Change status
        updated_order = await self.repository.change_order_status(
            order_id=order_id,
            new_status=new_status,
            reason=reason,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if not updated_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with ID {order_id} not found"
            )

        return updated_order

    # ═══════════════════════════════════════════════════════════════════════
    # Order Item Management
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

        Raises:
            HTTPException: If validation fails
        """
        # Check order exists and is editable
        order = await self.get_order(order_id, include_items=False)

        if order.status not in ["draft", "approved"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add materials to order in '{order.status}' status"
            )

        # Validate quantities
        if quantity_planned <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity planned must be greater than 0"
            )

        if unit_price < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unit price cannot be negative"
            )

        # Add order item
        return await self.repository.add_order_item(
            order_id=order_id,
            material_id=material_id,
            quantity_planned=quantity_planned,
            unit=unit,
            unit_price=unit_price,
            notes=notes,
        )

    async def update_order_item(
        self,
        order_item_id: int,
        **updates
    ) -> OrderItem:
        """
        Update an order item.

        Args:
            order_item_id: Order item ID
            **updates: Fields to update

        Returns:
            Updated order item

        Raises:
            HTTPException: If not found or validation fails
        """
        # Validate quantities if provided
        if "quantity_planned" in updates and updates["quantity_planned"] <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity planned must be greater than 0"
            )

        if "quantity_used" in updates and updates["quantity_used"] < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity used cannot be negative"
            )

        if "unit_price" in updates and updates["unit_price"] < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unit price cannot be negative"
            )

        # Update
        updated_item = await self.repository.update_order_item(order_item_id, **updates)

        if not updated_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order item with ID {order_item_id} not found"
            )

        return updated_item

    async def allocate_material(
        self,
        order_item_id: int,
    ) -> OrderItem:
        """
        Allocate materials for an order item.

        Args:
            order_item_id: Order item ID

        Returns:
            Updated order item

        Raises:
            HTTPException: If not found or already allocated
        """
        # Note: In a real system, this would check material stock availability
        # and reserve the materials

        allocated_item = await self.repository.allocate_material(order_item_id)

        if not allocated_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order item with ID {order_item_id} not found"
            )

        return allocated_item

    async def mark_material_used(
        self,
        order_item_id: int,
        quantity_used: float,
        notes: Optional[str] = None,
    ) -> OrderItem:
        """
        Mark materials as used in production.

        Args:
            order_item_id: Order item ID
            quantity_used: Actual quantity used
            notes: Notes about usage

        Returns:
            Updated order item

        Raises:
            HTTPException: If not found or validation fails
        """
        # Validate quantity
        if quantity_used <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity used must be greater than 0"
            )

        # Note: In a real system, this would deduct the quantity from material stock

        used_item = await self.repository.mark_material_used(
            order_item_id=order_item_id,
            quantity_used=quantity_used,
            notes=notes,
        )

        if not used_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order item with ID {order_item_id} not found"
            )

        return used_item

    async def remove_order_item(
        self,
        order_item_id: int,
    ) -> bool:
        """
        Remove an order item.

        Args:
            order_item_id: Order item ID

        Returns:
            True if removed

        Raises:
            HTTPException: If not found
        """
        removed = await self.repository.remove_order_item(order_item_id)

        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order item with ID {order_item_id} not found"
            )

        return True

    # ═══════════════════════════════════════════════════════════════════════
    # Statistics & Reporting
    # ═══════════════════════════════════════════════════════════════════════

    async def get_order_statistics(self) -> Dict[str, Any]:
        """
        Get order statistics for dashboard and reporting.

        Returns:
            Dictionary with order statistics
        """
        return await self.repository.get_order_statistics()

    async def get_orders_by_customer(
        self,
        customer_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Order]:
        """
        Get all orders for a specific customer.

        Args:
            customer_id: Customer ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of orders
        """
        return await self.list_orders(
            customer_id=customer_id,
            skip=skip,
            limit=limit,
            order_by="-created_at",
        )

    async def get_overdue_orders(self) -> List[Order]:
        """
        Get all overdue orders (past estimated completion date).

        Returns:
            List of overdue orders
        """
        all_orders = await self.list_orders(
            limit=1000,
            order_by="estimated_completion_date",
        )

        # Filter overdue orders
        now = datetime.utcnow()
        overdue = [
            order for order in all_orders
            if order.estimated_completion_date
            and order.estimated_completion_date < now
            and order.status in ["draft", "approved", "in_progress"]
        ]

        return overdue

    async def get_urgent_orders(self) -> List[Order]:
        """
        Get all urgent priority orders.

        Returns:
            List of urgent orders
        """
        return await self.list_orders(
            priority="urgent",
            limit=1000,
            order_by="-created_at",
        )
