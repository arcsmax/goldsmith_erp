from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from typing import List, Optional, Dict, Any

from goldsmith_erp.db.models import Order as OrderModel, Material
from goldsmith_erp.models.order import OrderCreate, OrderUpdate

class OrderService:
    @staticmethod
    async def get_orders(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[OrderModel]:
        """Holt alle Aufträge mit Pagination."""
        result = await db.execute(
            select(OrderModel)
            .order_by(OrderModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_order(db: AsyncSession, order_id: int) -> Optional[OrderModel]:
        """Holt einen einzelnen Auftrag über seine ID."""
        result = await db.execute(
            select(OrderModel)
            .filter(OrderModel.id == order_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_order(db: AsyncSession, order_in: OrderCreate) -> OrderModel:
        """Erstellt einen neuen Auftrag."""
        order_data = order_in.dict(exclude={"materials"})
        db_order = OrderModel(**order_data)
        
        # Materialien verknüpfen, falls angegeben
        if order_in.materials:
            material_results = await db.execute(
                select(Material)
                .filter(Material.id.in_(order_in.materials))
            )
            materials = material_results.scalars().all()
            db_order.materials = materials
        
        db.add(db_order)
        await db.commit()
        await db.refresh(db_order)
        return db_order

    @staticmethod
    async def update_order(
        db: AsyncSession, order_id: int, order_in: OrderUpdate
    ) -> Optional[OrderModel]:
        """Aktualisiert einen bestehenden Auftrag."""
        # Zuerst prüfen, ob der Auftrag existiert
        order = await OrderService.get_order(db, order_id)
        if not order:
            return None
        
        # Update durchführen
        update_data = order_in.dict(exclude_unset=True)
        await db.execute(
            update(OrderModel)
            .where(OrderModel.id == order_id)
            .values(**update_data)
        )
        await db.commit()
        
        # Aktualisiertes Objekt zurückgeben
        return await OrderService.get_order(db, order_id)

    @staticmethod
    async def delete_order(db: AsyncSession, order_id: int) -> Dict[str, Any]:
        """Löscht einen Auftrag."""
        await db.execute(
            delete(OrderModel)
            .where(OrderModel.id == order_id)
        )
        await db.commit()
        return {"success": True}