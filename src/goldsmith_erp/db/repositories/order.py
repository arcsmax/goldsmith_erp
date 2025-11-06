"""Order repository for database operations."""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import Order
from goldsmith_erp.db.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    """Repository for Order model with specific operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Order, session)

    async def get_by_id_with_relations(self, id: int) -> Optional[Order]:
        """
        Get order by ID with customer and materials loaded.

        Args:
            id: Order ID

        Returns:
            Order instance with relationships loaded, or None if not found
        """
        result = await self.session.execute(
            select(Order)
            .where(Order.id == id)
            .options(
                selectinload(Order.customer),
                selectinload(Order.materials)
            )
        )
        return result.scalar_one_or_none()

    async def get_all_with_relations(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None
    ) -> List[Order]:
        """
        Get all orders with customer and materials loaded.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            status: Optional status filter

        Returns:
            List of orders with relationships loaded
        """
        query = select(Order).options(
            selectinload(Order.customer),
            selectinload(Order.materials)
        )

        if status:
            query = query.where(Order.status == status)

        query = query.order_by(Order.created_at.desc()).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_customer(
        self,
        customer_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> List[Order]:
        """
        Get orders for a specific customer.

        Args:
            customer_id: Customer ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of orders
        """
        result = await self.session.execute(
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Order]:
        """
        Get orders by status.

        Args:
            status: Order status (new, in_progress, completed, delivered)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of orders
        """
        result = await self.session.execute(
            select(Order)
            .where(Order.status == status)
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        id: int,
        new_status: str
    ) -> Optional[Order]:
        """
        Update order status.

        Args:
            id: Order ID
            new_status: New status value

        Returns:
            Updated order or None if not found
        """
        return await self.update(id, status=new_status)

    async def add_material(
        self,
        order_id: int,
        material_id: int
    ) -> Optional[Order]:
        """
        Add a material to an order.

        Args:
            order_id: Order ID
            material_id: Material ID

        Returns:
            Updated order or None if not found
        """
        order = await self.get_by_id_with_relations(order_id)
        if not order:
            return None

        # Check if material is already added
        if any(m.id == material_id for m in order.materials):
            return order

        # Import here to avoid circular import
        from goldsmith_erp.db.models import Material
        material_result = await self.session.execute(
            select(Material).where(Material.id == material_id)
        )
        material = material_result.scalar_one_or_none()

        if material:
            order.materials.append(material)
            await self.session.commit()
            await self.session.refresh(order)

        return order

    async def remove_material(
        self,
        order_id: int,
        material_id: int
    ) -> Optional[Order]:
        """
        Remove a material from an order.

        Args:
            order_id: Order ID
            material_id: Material ID

        Returns:
            Updated order or None if not found
        """
        order = await self.get_by_id_with_relations(order_id)
        if not order:
            return None

        # Remove material if exists
        order.materials = [m for m in order.materials if m.id != material_id]
        await self.session.commit()
        await self.session.refresh(order)

        return order
