"""Base repository with common database operations."""
from typing import Generic, TypeVar, Type, Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import DeclarativeMeta

ModelType = TypeVar("ModelType", bound=DeclarativeMeta)


class BaseRepository(Generic[ModelType]):
    """Base repository providing common CRUD operations."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class
            session: Async database session
        """
        self.model = model
        self.session = session

    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """
        Get a record by ID.

        Args:
            id: Record ID

        Returns:
            Model instance or None if not found
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
    ) -> List[ModelType]:
        """
        Get all records with optional filtering and pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            filters: Dictionary of field:value pairs for filtering
            order_by: Field name to order by (prefix with - for descending)

        Returns:
            List of model instances
        """
        query = select(self.model)

        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.where(getattr(self.model, field) == value)

        # Apply ordering
        if order_by:
            if order_by.startswith("-"):
                field_name = order_by[1:]
                if hasattr(self.model, field_name):
                    query = query.order_by(getattr(self.model, field_name).desc())
            else:
                if hasattr(self.model, order_by):
                    query = query.order_by(getattr(self.model, order_by))
        else:
            # Default: order by ID descending (newest first)
            query = query.order_by(self.model.id.desc())

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count records matching filters.

        Args:
            filters: Dictionary of field:value pairs for filtering

        Returns:
            Count of matching records
        """
        query = select(func.count(self.model.id))

        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.where(getattr(self.model, field) == value)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def create(self, **data) -> ModelType:
        """
        Create a new record.

        Args:
            **data: Field values for the new record

        Returns:
            Created model instance
        """
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: int, **data) -> Optional[ModelType]:
        """
        Update a record by ID.

        Args:
            id: Record ID
            **data: Fields to update

        Returns:
            Updated model instance or None if not found
        """
        # First check if record exists
        instance = await self.get_by_id(id)
        if not instance:
            return None

        # Update fields
        for field, value in data.items():
            if hasattr(instance, field):
                setattr(instance, field, value)

        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def delete(self, id: int) -> bool:
        """
        Delete a record by ID.

        Args:
            id: Record ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            delete(self.model).where(self.model.id == id)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def exists(self, id: int) -> bool:
        """
        Check if a record exists.

        Args:
            id: Record ID

        Returns:
            True if exists, False otherwise
        """
        result = await self.session.execute(
            select(func.count(self.model.id)).where(self.model.id == id)
        )
        count = result.scalar_one()
        return count > 0
