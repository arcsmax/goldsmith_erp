"""Service for Scrap Gold (Altgold) management."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime
import logging

from goldsmith_erp.db.models import (
    ScrapGold as ScrapGoldModel,
    ScrapGoldItem as ScrapGoldItemModel,
    ScrapGoldStatus,
)
from goldsmith_erp.models.scrap_gold import (
    ScrapGoldCreate, ScrapGoldUpdate, ScrapGoldItemCreate, ALLOY_RATIOS
)

logger = logging.getLogger(__name__)


class ScrapGoldService:

    @staticmethod
    def calculate_fine_content(alloy: str, weight_g: float) -> float:
        """Calculate fine gold/silver content from alloy type and weight."""
        ratio = ALLOY_RATIOS.get(alloy, 0.0)
        return round(weight_g * ratio, 3)

    @staticmethod
    async def get_for_order(db: AsyncSession, order_id: int) -> Optional[ScrapGoldModel]:
        """Get scrap gold record for an order, with items."""
        result = await db.execute(
            select(ScrapGoldModel)
            .where(ScrapGoldModel.order_id == order_id)
            .options(selectinload(ScrapGoldModel.items))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, scrap_gold_id: int) -> Optional[ScrapGoldModel]:
        """Get scrap gold by ID with items."""
        result = await db.execute(
            select(ScrapGoldModel)
            .where(ScrapGoldModel.id == scrap_gold_id)
            .options(selectinload(ScrapGoldModel.items))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: int,
        data: ScrapGoldCreate
    ) -> ScrapGoldModel:
        """Create a new scrap gold record for an order."""
        scrap_gold = ScrapGoldModel(
            order_id=data.order_id,
            customer_id=data.customer_id,
            created_by=user_id,
            gold_price_per_g=data.gold_price_per_g,
            price_source=data.price_source,
            notes=data.notes,
        )
        db.add(scrap_gold)
        await db.commit()
        await db.refresh(scrap_gold)
        return scrap_gold

    @staticmethod
    async def add_item(
        db: AsyncSession,
        scrap_gold_id: int,
        item_data: ScrapGoldItemCreate
    ) -> ScrapGoldItemModel:
        """Add an item to a scrap gold record and recalculate totals."""
        fine_content = ScrapGoldService.calculate_fine_content(
            item_data.alloy, item_data.weight_g
        )
        item = ScrapGoldItemModel(
            scrap_gold_id=scrap_gold_id,
            description=item_data.description,
            alloy=item_data.alloy,
            weight_g=item_data.weight_g,
            fine_content_g=fine_content,
            photo_path=item_data.photo_path,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)

        # Recalculate totals
        await ScrapGoldService._recalculate_totals(db, scrap_gold_id)
        return item

    @staticmethod
    async def remove_item(
        db: AsyncSession,
        scrap_gold_id: int,
        item_id: int
    ) -> bool:
        """Remove an item and recalculate totals."""
        result = await db.execute(
            select(ScrapGoldItemModel).where(
                ScrapGoldItemModel.id == item_id,
                ScrapGoldItemModel.scrap_gold_id == scrap_gold_id
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return False
        await db.delete(item)
        await db.commit()
        await ScrapGoldService._recalculate_totals(db, scrap_gold_id)
        return True

    @staticmethod
    async def calculate_and_update(
        db: AsyncSession,
        scrap_gold_id: int,
        gold_price_per_g: Optional[float] = None
    ) -> Optional[ScrapGoldModel]:
        """Recalculate totals and optionally update gold price."""
        scrap_gold = await ScrapGoldService.get_by_id(db, scrap_gold_id)
        if not scrap_gold:
            return None

        if gold_price_per_g is not None:
            scrap_gold.gold_price_per_g = gold_price_per_g

        await ScrapGoldService._recalculate_totals(db, scrap_gold_id)

        scrap_gold.status = ScrapGoldStatus.CALCULATED
        await db.commit()
        await db.refresh(scrap_gold)
        return scrap_gold

    @staticmethod
    async def sign(
        db: AsyncSession,
        scrap_gold_id: int,
        signature_data: str
    ) -> Optional[ScrapGoldModel]:
        """Record customer's digital signature on scrap gold receipt."""
        scrap_gold = await ScrapGoldService.get_by_id(db, scrap_gold_id)
        if not scrap_gold:
            return None

        scrap_gold.signature_data = signature_data
        scrap_gold.signed_at = datetime.utcnow()
        scrap_gold.status = ScrapGoldStatus.SIGNED
        await db.commit()
        await db.refresh(scrap_gold)
        logger.info(f"Scrap gold {scrap_gold_id} signed by customer")
        return scrap_gold

    @staticmethod
    async def _recalculate_totals(db: AsyncSession, scrap_gold_id: int):
        """Recalculate total fine gold and value for a scrap gold record."""
        result = await db.execute(
            select(ScrapGoldItemModel)
            .where(ScrapGoldItemModel.scrap_gold_id == scrap_gold_id)
        )
        items = result.scalars().all()

        total_fine = sum(item.fine_content_g for item in items)

        scrap_gold_result = await db.execute(
            select(ScrapGoldModel).where(ScrapGoldModel.id == scrap_gold_id)
        )
        scrap_gold = scrap_gold_result.scalar_one_or_none()
        if scrap_gold:
            scrap_gold.total_fine_gold_g = round(total_fine, 3)
            if scrap_gold.gold_price_per_g:
                scrap_gold.total_value_eur = round(
                    total_fine * scrap_gold.gold_price_per_g, 2
                )
            await db.commit()
