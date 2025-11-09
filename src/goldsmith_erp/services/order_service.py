from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
import json
import logging

from goldsmith_erp.db.models import Order as OrderModel, Material
from goldsmith_erp.models.order import OrderCreate, OrderUpdate
from goldsmith_erp.core.pubsub import publish_event  # Import the Redis publish function
from goldsmith_erp.db.transaction import transactional

logger = logging.getLogger(__name__)

class OrderService:
    @staticmethod
    async def get_orders(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[OrderModel]:
        """
        Holt alle Aufträge mit Pagination.

        Uses eager loading to prevent N+1 queries when accessing relationships.
        """
        result = await db.execute(
            select(OrderModel)
            .options(
                selectinload(OrderModel.materials),
                selectinload(OrderModel.customer)
            )
            .order_by(OrderModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_order(db: AsyncSession, order_id: int) -> Optional[OrderModel]:
        """
        Holt einen einzelnen Auftrag über seine ID.

        Uses eager loading to prevent N+1 queries when accessing relationships.
        """
        result = await db.execute(
            select(OrderModel)
            .options(
                selectinload(OrderModel.materials),
                selectinload(OrderModel.customer)
            )
            .filter(OrderModel.id == order_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_order(db: AsyncSession, order_in: OrderCreate) -> OrderModel:
        """
        Erstellt einen neuen Auftrag mit transaktionaler Integrität.

        All database operations are wrapped in a transaction to ensure ACID properties.
        Event publishing happens after successful commit.
        """
        async with transactional(db):
            order_data = order_in.dict(exclude={"materials"})
            db_order = OrderModel(**order_data)

            # Materialien verknüpfen, falls angegeben
            if order_in.materials:
                material_results = await db.execute(
                    select(Material)
                    .filter(Material.id.in_(order_in.materials))
                )
                materials = material_results.scalars().all()

                # Validate all materials exist
                if len(materials) != len(order_in.materials):
                    found_ids = {m.id for m in materials}
                    missing_ids = set(order_in.materials) - found_ids
                    raise ValueError(f"Materials not found: {missing_ids}")

                db_order.materials = materials

            db.add(db_order)
            # Flush to get the ID before commit
            await db.flush()
            await db.refresh(db_order)

        # Publish event to Redis AFTER successful transaction commit
        # If this fails, the order is still created (eventual consistency)
        try:
            await publish_event(
                "order_updates",
                json.dumps({
                    "action": "create",
                    "order_id": db_order.id,
                    "status": db_order.status.value if hasattr(db_order.status, "value") else db_order.status,
                    "data": {
                        "id": db_order.id,
                        "customer_id": db_order.customer_id,
                        "title": db_order.title if hasattr(db_order, "title") else None,
                        "created_at": db_order.created_at.isoformat() if hasattr(db_order, "created_at") else None,
                        "status": db_order.status.value if hasattr(db_order.status, "value") else db_order.status,
                        "price": str(db_order.price) if db_order.price else None,
                    }
                })
            )
        except Exception as e:
            # Log but don't fail the request if event publishing fails
            logger.error(f"Failed to publish order creation event: {str(e)}", exc_info=True)

        return db_order
    
    @staticmethod
    async def update_order(
        db: AsyncSession, order_id: int, order_in: OrderUpdate
    ) -> Optional[OrderModel]:
        """
        Aktualisiert einen bestehenden Auftrag mit transaktionaler Integrität.

        All database operations are wrapped in a transaction to ensure ACID properties.
        """
        # Zuerst prüfen, ob der Auftrag existiert
        order = await OrderService.get_order(db, order_id)
        if not order:
            return None

        async with transactional(db):
            # Update durchführen
            update_data = order_in.dict(exclude_unset=True)
            await db.execute(
                update(OrderModel)
                .where(OrderModel.id == order_id)
                .values(**update_data)
            )
            # Flush to ensure update is visible in same transaction
            await db.flush()

        # Aktualisiertes Objekt holen after transaction commits
        updated_order = await OrderService.get_order(db, order_id)

        # Publish event to Redis AFTER successful transaction commit
        try:
            await publish_event(
                "order_updates",
                json.dumps({
                    "action": "update",
                    "order_id": order_id,
                    "status": updated_order.status.value if hasattr(updated_order.status, "value") else updated_order.status,
                    "data": {
                        "id": updated_order.id,
                        "customer_id": updated_order.customer_id,
                        "title": updated_order.title if hasattr(updated_order, "title") else None,
                        "updated_at": updated_order.updated_at.isoformat() if hasattr(updated_order, "updated_at") else None,
                        "status": updated_order.status.value if hasattr(updated_order.status, "value") else updated_order.status,
                        "price": str(updated_order.price) if updated_order.price else None,
                    }
                })
            )
        except Exception as e:
            # Log but don't fail the request if event publishing fails
            logger.error(f"Failed to publish order update event: {str(e)}", exc_info=True)

        return updated_order
    
    @staticmethod
    async def delete_order(db: AsyncSession, order_id: int) -> Dict[str, Any]:
        """
        Löscht einen Auftrag mit transaktionaler Integrität.

        All database operations are wrapped in a transaction to ensure ACID properties.
        """
        # Get order information before deletion for the event
        order = await OrderService.get_order(db, order_id)
        if not order:
            return {"success": False, "message": "Order not found"}

        async with transactional(db):
            # Delete the order
            await db.execute(
                delete(OrderModel)
                .where(OrderModel.id == order_id)
            )

        # Publish event to Redis AFTER successful transaction commit
        try:
            await publish_event(
                "order_updates",
                json.dumps({
                    "action": "delete",
                    "order_id": order_id,
                    "message": f"Order {order_id} has been deleted"
                })
            )
        except Exception as e:
            # Log but don't fail the request if event publishing fails
            logger.error(f"Failed to publish order deletion event: {str(e)}", exc_info=True)

        return {"success": True}