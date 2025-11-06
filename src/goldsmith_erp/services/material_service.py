"""Material service with business logic."""
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status

from goldsmith_erp.db.repositories.material import MaterialRepository
from goldsmith_erp.models.material import (
    MaterialCreate,
    MaterialUpdate,
    MaterialResponse,
    MaterialWithStock,
    MaterialStockAdjust,
)


class MaterialService:
    """Service for material business logic."""

    def __init__(self, repository: MaterialRepository):
        """
        Initialize service.

        Args:
            repository: Material repository instance
        """
        self.repository = repository

    async def get_material(self, material_id: int) -> MaterialResponse:
        """
        Get a material by ID.

        Args:
            material_id: Material ID

        Returns:
            Material data

        Raises:
            HTTPException: If material not found
        """
        material = await self.repository.get_by_id(material_id)
        if not material:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Material with id {material_id} not found"
            )
        return MaterialResponse.from_orm(material)

    async def get_material_with_stock_status(
        self,
        material_id: int
    ) -> MaterialWithStock:
        """
        Get a material with stock status indicators.

        Args:
            material_id: Material ID

        Returns:
            Material data with stock status

        Raises:
            HTTPException: If material not found
        """
        material = await self.repository.get_by_id(material_id)
        if not material:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Material with id {material_id} not found"
            )
        return MaterialWithStock.from_material(material)

    async def list_materials(
        self,
        skip: int = 0,
        limit: int = 100,
        material_type: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[MaterialResponse]:
        """
        List materials with optional filtering.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            material_type: Optional filter by material type
            search: Optional search term for name/description

        Returns:
            List of materials
        """
        if search:
            materials = await self.repository.search(search, skip, limit)
        elif material_type:
            materials = await self.repository.get_by_type(material_type, skip, limit)
        else:
            materials = await self.repository.get_all(skip, limit)

        return [MaterialResponse.from_orm(m) for m in materials]

    async def get_low_stock_materials(
        self,
        threshold_factor: float = 1.0
    ) -> List[MaterialWithStock]:
        """
        Get materials with low stock.

        Args:
            threshold_factor: Multiplier for min_stock threshold

        Returns:
            List of materials with low stock
        """
        materials = await self.repository.get_low_stock(threshold_factor)
        return [MaterialWithStock.from_material(m) for m in materials]

    async def create_material(self, data: MaterialCreate) -> MaterialResponse:
        """
        Create a new material.

        Args:
            data: Material creation data

        Returns:
            Created material

        Raises:
            HTTPException: If creation fails
        """
        try:
            material = await self.repository.create(**data.dict())
            return MaterialResponse.from_orm(material)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create material: {str(e)}"
            )

    async def update_material(
        self,
        material_id: int,
        data: MaterialUpdate
    ) -> MaterialResponse:
        """
        Update a material.

        Args:
            material_id: Material ID
            data: Update data

        Returns:
            Updated material

        Raises:
            HTTPException: If material not found or update fails
        """
        # Only include fields that were actually provided
        update_data = data.dict(exclude_unset=True)

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update"
            )

        material = await self.repository.update(material_id, **update_data)
        if not material:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Material with id {material_id} not found"
            )

        return MaterialResponse.from_orm(material)

    async def delete_material(self, material_id: int) -> bool:
        """
        Delete a material.

        Args:
            material_id: Material ID

        Returns:
            True if deleted

        Raises:
            HTTPException: If material not found
        """
        deleted = await self.repository.delete(material_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Material with id {material_id} not found"
            )
        return True

    async def adjust_stock(
        self,
        material_id: int,
        adjustment: MaterialStockAdjust
    ) -> MaterialResponse:
        """
        Adjust material stock.

        Args:
            material_id: Material ID
            adjustment: Stock adjustment data

        Returns:
            Updated material

        Raises:
            HTTPException: If material not found or insufficient stock
        """
        try:
            material = await self.repository.adjust_stock(
                material_id,
                adjustment.quantity,
                adjustment.operation
            )
            if not material:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Material with id {material_id} not found"
                )
            return MaterialResponse.from_orm(material)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    async def set_stock(
        self,
        material_id: int,
        quantity: float
    ) -> MaterialResponse:
        """
        Set material stock to a specific value.

        Args:
            material_id: Material ID
            quantity: New stock quantity

        Returns:
            Updated material

        Raises:
            HTTPException: If material not found or invalid quantity
        """
        try:
            material = await self.repository.set_stock(material_id, quantity)
            if not material:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Material with id {material_id} not found"
                )
            return MaterialResponse.from_orm(material)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    async def get_total_stock_value(
        self,
        material_type: Optional[str] = None
    ) -> float:
        """
        Calculate total value of materials in stock.

        Args:
            material_type: Optional filter by material type

        Returns:
            Total stock value
        """
        filters = {"material_type": material_type} if material_type else None
        return await self.repository.get_total_value(filters)

    async def search_by_properties(
        self,
        properties_filters: Dict[str, Any],
        skip: int = 0,
        limit: int = 100
    ) -> List[MaterialResponse]:
        """
        Search materials by metadata fields.

        Args:
            properties_filters: Dictionary of metadata filters
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of matching materials
        """
        materials = await self.repository.get_by_properties(
            properties_filters,
            skip,
            limit
        )
        return [MaterialResponse.from_orm(m) for m in materials]
