"""Material repository for database operations."""
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from goldsmith_erp.db.models import Material
from goldsmith_erp.db.repositories.base import BaseRepository


class MaterialRepository(BaseRepository[Material]):
    """Repository for Material model with specific operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Material, session)

    async def get_by_type(
        self,
        material_type: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Material]:
        """
        Get materials by type.

        Args:
            material_type: Type of material (gold, silver, stone, etc.)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of materials
        """
        result = await self.session.execute(
            select(Material)
            .where(Material.material_type == material_type)
            .order_by(Material.name)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_low_stock(
        self,
        threshold_factor: float = 1.0
    ) -> List[Material]:
        """
        Get materials with low stock (below min_stock threshold).

        Args:
            threshold_factor: Multiplier for min_stock (1.0 = at threshold, 1.5 = 50% above)

        Returns:
            List of materials with low stock
        """
        result = await self.session.execute(
            select(Material)
            .where(Material.stock <= Material.min_stock * threshold_factor)
            .order_by(Material.stock.asc())
        )
        return list(result.scalars().all())

    async def search(
        self,
        query: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Material]:
        """
        Search materials by name or description.

        Args:
            query: Search query string
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of matching materials
        """
        search_term = f"%{query}%"
        result = await self.session.execute(
            select(Material)
            .where(
                or_(
                    Material.name.ilike(search_term),
                    Material.description.ilike(search_term)
                )
            )
            .order_by(Material.name)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def adjust_stock(
        self,
        id: int,
        quantity: float,
        operation: str = "add"
    ) -> Optional[Material]:
        """
        Adjust material stock.

        Args:
            id: Material ID
            quantity: Quantity to add or subtract
            operation: "add" to increase stock, "subtract" to decrease

        Returns:
            Updated material or None if not found or invalid operation

        Raises:
            ValueError: If operation would result in negative stock
        """
        material = await self.get_by_id(id)
        if not material:
            return None

        if operation == "add":
            new_stock = material.stock + quantity
        elif operation == "subtract":
            new_stock = material.stock - quantity
            if new_stock < 0:
                raise ValueError(
                    f"Insufficient stock. Available: {material.stock}, "
                    f"Requested: {quantity}"
                )
        else:
            raise ValueError(f"Invalid operation: {operation}. Use 'add' or 'subtract'")

        material.stock = new_stock
        await self.session.commit()
        await self.session.refresh(material)
        return material

    async def set_stock(
        self,
        id: int,
        quantity: float
    ) -> Optional[Material]:
        """
        Set material stock to a specific value.

        Args:
            id: Material ID
            quantity: New stock quantity

        Returns:
            Updated material or None if not found

        Raises:
            ValueError: If quantity is negative
        """
        if quantity < 0:
            raise ValueError(f"Stock quantity cannot be negative: {quantity}")

        material = await self.get_by_id(id)
        if not material:
            return None

        material.stock = quantity
        await self.session.commit()
        await self.session.refresh(material)
        return material

    async def get_total_value(
        self,
        filters: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Calculate total value of materials in stock.

        Args:
            filters: Optional filters (e.g., {"material_type": "gold"})

        Returns:
            Total value (sum of stock * unit_price)
        """
        query = select(Material)

        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(Material, field):
                    query = query.where(getattr(Material, field) == value)

        result = await self.session.execute(query)
        materials = result.scalars().all()

        total_value = sum(m.stock * m.unit_price for m in materials)
        return total_value

    async def get_by_properties(
        self,
        properties_filters: Dict[str, Any],
        skip: int = 0,
        limit: int = 100
    ) -> List[Material]:
        """
        Search materials by metadata fields (JSONB).

        Args:
            properties_filters: Dictionary of metadata field:value pairs
                             Example: {"purity": 750, "color": "yellow"}
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of matching materials
        """
        query = select(Material)

        # Apply JSONB filters
        for key, value in properties_filters.items():
            query = query.where(
                Material.properties[key].astext == str(value)
            )

        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
