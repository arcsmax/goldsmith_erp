"""Service for Scrap Gold (Altgold) management."""

import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import AlloyType
from goldsmith_erp.db.models import MetalPriceSource as MetalPriceSourceModel
from goldsmith_erp.db.models import MetalType
from goldsmith_erp.db.models import ScrapGold as ScrapGoldModel
from goldsmith_erp.db.models import ScrapGoldItem as ScrapGoldItemModel
from goldsmith_erp.db.models import ScrapGoldStatus
from goldsmith_erp.models.scrap_gold import (
    ALLOY_BASE_METAL,
    ALLOY_FINENESS,
    ScrapGoldCreate,
    ScrapGoldItemCreate,
    ScrapGoldUpdate,
)
from goldsmith_erp.services.metal_price_service import MetalPriceService

logger = logging.getLogger(__name__)

# Quantization targets: grams to 3 decimals, EUR to 2 decimals (CLAUDE.md:
# Decimal for money; ROUND_HALF_UP is the workshop's convention for cash
# amounts owed to/from a customer).
_GRAM_QUANT = Decimal("0.001")
_EUR_QUANT = Decimal("0.01")

# BE-11: once the customer has signed the Ankaufsbeleg (or the credit was
# applied to an invoice) the record is the signed document. Items, weights,
# prices and the signature are frozen; only status progression and notes
# may change. Enforced here (service level) rather than with a DB trigger:
# every write path goes through this service, and the invoice service only
# ever moves SIGNED -> CREDITED.
LOCKED_STATUSES = frozenset({ScrapGoldStatus.SIGNED, ScrapGoldStatus.CREDITED})
_LOCKED_MESSAGE = (
    "Altgold-Eintrag ist bereits vom Kunden unterschrieben und kann nicht "
    "mehr geaendert werden (nur Notizen)."
)


class ScrapGoldLockedError(ValueError):
    """Raised when a signed/credited Altgold record would be altered (409)."""

    def __init__(self, scrap_gold_id: int) -> None:
        super().__init__(_LOCKED_MESSAGE)
        self.scrap_gold_id = scrap_gold_id


def is_locked(scrap_gold: ScrapGoldModel) -> bool:
    """True once the record is SIGNED or CREDITED (BE-11)."""
    return scrap_gold.status in LOCKED_STATUSES


def ensure_editable(scrap_gold: ScrapGoldModel) -> None:
    """Raise ``ScrapGoldLockedError`` if the record may no longer change."""
    if is_locked(scrap_gold):
        logger.warning(
            "Rejected change to signed scrap gold record",
            extra={"scrap_gold_id": scrap_gold.id, "status": str(scrap_gold.status)},
        )
        raise ScrapGoldLockedError(scrap_gold.id)


class ScrapGoldService:

    @staticmethod
    def calculate_fine_content(alloy: AlloyType, weight_g: float) -> float:
        """Calculate fine gold/silver/platinum content from alloy and weight.

        ``alloy`` must be a valid ``AlloyType`` member. There is no silent
        0.0-fallback for an unrecognised alloy (DOM-19) — callers that
        accept alloy as free text (e.g. the alloy-calculator endpoint) must
        validate against ``ALLOY_RATIOS``/``AlloyType`` before calling this,
        exactly as the request-body path already does via Pydantic.
        """
        alloy_enum = alloy if isinstance(alloy, AlloyType) else AlloyType(alloy)
        fineness = ALLOY_FINENESS[alloy_enum]
        fine = (Decimal(str(weight_g)) * fineness).quantize(
            _GRAM_QUANT, rounding=ROUND_HALF_UP
        )
        return float(fine)

    @staticmethod
    async def get_for_order(
        db: AsyncSession, order_id: int
    ) -> Optional[ScrapGoldModel]:
        """Get scrap gold record for an order, with items."""
        result = await db.execute(
            select(ScrapGoldModel)
            .where(ScrapGoldModel.order_id == order_id)
            .options(selectinload(ScrapGoldModel.items))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        db: AsyncSession, scrap_gold_id: int
    ) -> Optional[ScrapGoldModel]:
        """Get scrap gold by ID with items."""
        result = await db.execute(
            select(ScrapGoldModel)
            .where(ScrapGoldModel.id == scrap_gold_id)
            .options(selectinload(ScrapGoldModel.items))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession, user_id: int, data: ScrapGoldCreate
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
        db: AsyncSession, scrap_gold_id: int, item_data: ScrapGoldItemCreate
    ) -> ScrapGoldItemModel:
        """Add an item to a scrap gold record and recalculate totals.

        Raises ``ScrapGoldLockedError`` once the record is signed (BE-11).
        """
        if await ScrapGoldService._load_editable(db, scrap_gold_id) is None:
            raise LookupError(f"Scrap gold {scrap_gold_id} not found")
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
    async def remove_item(db: AsyncSession, scrap_gold_id: int, item_id: int) -> bool:
        """Remove an item and recalculate totals.

        Raises ``ScrapGoldLockedError`` once the record is signed (BE-11).
        """
        if await ScrapGoldService._load_editable(db, scrap_gold_id) is None:
            return False
        result = await db.execute(
            select(ScrapGoldItemModel).where(
                ScrapGoldItemModel.id == item_id,
                ScrapGoldItemModel.scrap_gold_id == scrap_gold_id,
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
        db: AsyncSession, scrap_gold_id: int, gold_price_per_g: Optional[float] = None
    ) -> Optional[ScrapGoldModel]:
        """Recalculate totals and optionally update the gold price override.

        On a signed/credited record (BE-11) the signed totals are final: a
        price override raises ``ScrapGoldLockedError``, a plain recalculation
        is a no-op (no re-pricing against today's spot price, no status
        demotion).
        """
        scrap_gold = await ScrapGoldService.get_by_id(db, scrap_gold_id)
        if not scrap_gold:
            return None

        if is_locked(scrap_gold):
            if gold_price_per_g is not None:
                ensure_editable(scrap_gold)
            return scrap_gold

        if gold_price_per_g is not None:
            scrap_gold.gold_price_per_g = gold_price_per_g

        await ScrapGoldService._recalculate_totals(db, scrap_gold_id)

        scrap_gold.status = ScrapGoldStatus.CALCULATED
        await db.commit()
        await db.refresh(scrap_gold)
        return scrap_gold

    @staticmethod
    async def sign(
        db: AsyncSession, scrap_gold_id: int, signature_data: str
    ) -> Optional[ScrapGoldModel]:
        """Record customer's digital signature on scrap gold receipt.

        A record can be signed exactly once (BE-11): re-signing would swap
        the signature under an already-issued receipt.
        """
        scrap_gold = await ScrapGoldService.get_by_id(db, scrap_gold_id)
        if not scrap_gold:
            return None
        ensure_editable(scrap_gold)

        scrap_gold.signature_data = signature_data
        scrap_gold.signed_at = datetime.utcnow()
        scrap_gold.status = ScrapGoldStatus.SIGNED
        await db.commit()
        await db.refresh(scrap_gold)
        logger.info(f"Scrap gold {scrap_gold_id} signed by customer")
        return scrap_gold

    @staticmethod
    async def update(
        db: AsyncSession, scrap_gold_id: int, data: ScrapGoldUpdate
    ) -> Optional[ScrapGoldModel]:
        """Update header fields. After signing only ``notes`` may change."""
        scrap_gold = await ScrapGoldService.get_by_id(db, scrap_gold_id)
        if not scrap_gold:
            return None

        changes = data.model_dump(exclude_unset=True)
        if is_locked(scrap_gold) and set(changes) - {"notes"}:
            ensure_editable(scrap_gold)

        for field, value in changes.items():
            setattr(scrap_gold, field, value)
        await db.commit()
        if "gold_price_per_g" in changes:
            await ScrapGoldService._recalculate_totals(db, scrap_gold_id)
        return await ScrapGoldService.get_by_id(db, scrap_gold_id)

    @staticmethod
    async def ensure_item_editable(
        db: AsyncSession, scrap_gold_id: int
    ) -> Optional[ScrapGoldModel]:
        """Public guard for item-level writes outside this service (photo upload)."""
        return await ScrapGoldService._load_editable(db, scrap_gold_id)

    @staticmethod
    async def _load_editable(
        db: AsyncSession, scrap_gold_id: int
    ) -> Optional[ScrapGoldModel]:
        """Load the record for an item write; None if missing, raise if locked."""
        result = await db.execute(
            select(ScrapGoldModel).where(ScrapGoldModel.id == scrap_gold_id)
        )
        scrap_gold = result.scalar_one_or_none()
        if scrap_gold is not None:
            ensure_editable(scrap_gold)
        return scrap_gold

    @staticmethod
    def _price_for_item(
        alloy: AlloyType,
        scrap_gold: ScrapGoldModel,
        spot_prices: Dict[MetalType, Tuple[float, MetalPriceSourceModel, datetime]],
    ) -> Decimal:
        """EUR/gram price of the PURE metal backing this item's alloy.

        Gold items honour a manually-set ``ScrapGold.gold_price_per_g``
        override (the pre-existing "Kurs am Tag des Ankaufs" workflow).
        Silver and platinum items always use the live MetalPriceService
        spot price — the schema has no equivalent override column for
        them (see docs/review/2026-09-25/05-domain-product-fit.md DOM-20).
        """
        base_metal = ALLOY_BASE_METAL[alloy]
        if base_metal == MetalType.GOLD_24K and scrap_gold.gold_price_per_g:
            return Decimal(str(scrap_gold.gold_price_per_g))
        spot_price, _source, _updated_at = spot_prices[base_metal]
        return Decimal(str(spot_price))

    @staticmethod
    async def _recalculate_totals(db: AsyncSession, scrap_gold_id: int) -> None:
        """Recalculate total fine metal content and EUR value.

        DOM-20 fix: each item is valued against the spot price of ITS OWN
        base metal (gold/silver/platinum) rather than a single blanket
        "gold price" applied to everything. ``total_fine_gold_g`` remains a
        single aggregate across all metals in the record (the ScrapGold
        table has no per-metal gram columns to split it into — flagged as
        a known limitation, not a money bug: the EUR total below is always
        metal-correct per item).
        """
        result = await db.execute(
            select(ScrapGoldItemModel).where(
                ScrapGoldItemModel.scrap_gold_id == scrap_gold_id
            )
        )
        items: List[ScrapGoldItemModel] = list(result.scalars().all())

        scrap_gold_result = await db.execute(
            select(ScrapGoldModel).where(ScrapGoldModel.id == scrap_gold_id)
        )
        scrap_gold = scrap_gold_result.scalar_one_or_none()
        if not scrap_gold:
            return

        total_fine = Decimal("0")
        total_value = Decimal("0")

        if items:
            spot_prices = await MetalPriceService.get_spot_prices(db)
            for item in items:
                fine = Decimal(str(item.fine_content_g))
                total_fine += fine

                alloy = (
                    item.alloy
                    if isinstance(item.alloy, AlloyType)
                    else AlloyType(item.alloy)
                )
                price_per_g = ScrapGoldService._price_for_item(
                    alloy, scrap_gold, spot_prices
                )
                total_value += fine * price_per_g

        scrap_gold.total_fine_gold_g = float(
            total_fine.quantize(_GRAM_QUANT, rounding=ROUND_HALF_UP)
        )
        scrap_gold.total_value_eur = float(
            total_value.quantize(_EUR_QUANT, rounding=ROUND_HALF_UP)
        )
        await db.commit()
