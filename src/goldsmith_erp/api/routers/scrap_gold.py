"""API Router for Scrap Gold (Altgold) management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User
from goldsmith_erp.models.scrap_gold import (
    ScrapGoldCreate, ScrapGoldRead, ScrapGoldItemCreate,
    ScrapGoldItemRead, ScrapGoldSignRequest, AlloyCalculation, ALLOY_RATIOS
)
from goldsmith_erp.services.scrap_gold_service import ScrapGoldService
from goldsmith_erp.core.permissions import Permission, require_permission

router = APIRouter()


@router.get("/orders/{order_id}/scrap-gold", response_model=Optional[ScrapGoldRead])
@require_permission(Permission.ORDER_VIEW)
async def get_scrap_gold(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Altgold-Eintrag fuer einen Auftrag abrufen."""
    return await ScrapGoldService.get_for_order(db, order_id)


@router.post("/orders/{order_id}/scrap-gold", response_model=ScrapGoldRead, status_code=201)
@require_permission(Permission.ORDER_EDIT)
async def create_scrap_gold(
    order_id: int,
    data: ScrapGoldCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Neuen Altgold-Eintrag fuer einen Auftrag anlegen."""
    existing = await ScrapGoldService.get_for_order(db, order_id)
    if existing:
        raise HTTPException(status_code=409, detail="Altgold-Eintrag existiert bereits fuer diesen Auftrag")
    data.order_id = order_id
    scrap_gold = await ScrapGoldService.create(db, current_user.id, data)
    return await ScrapGoldService.get_by_id(db, scrap_gold.id)


@router.post("/scrap-gold/{scrap_gold_id}/items", response_model=ScrapGoldItemRead, status_code=201)
@require_permission(Permission.ORDER_EDIT)
async def add_item(
    scrap_gold_id: int,
    item_data: ScrapGoldItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Position zum Altgold-Eintrag hinzufuegen."""
    scrap_gold = await ScrapGoldService.get_by_id(db, scrap_gold_id)
    if not scrap_gold:
        raise HTTPException(status_code=404, detail="Altgold-Eintrag nicht gefunden")
    return await ScrapGoldService.add_item(db, scrap_gold_id, item_data)


@router.delete("/scrap-gold/{scrap_gold_id}/items/{item_id}", status_code=204)
@require_permission(Permission.ORDER_EDIT)
async def remove_item(
    scrap_gold_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Position aus Altgold-Eintrag entfernen."""
    deleted = await ScrapGoldService.remove_item(db, scrap_gold_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Position nicht gefunden")


@router.post("/scrap-gold/{scrap_gold_id}/calculate", response_model=ScrapGoldRead)
@require_permission(Permission.ORDER_EDIT)
async def calculate_totals(
    scrap_gold_id: int,
    gold_price_per_g: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Feingold-Gehalt und Wert berechnen."""
    result = await ScrapGoldService.calculate_and_update(db, scrap_gold_id, gold_price_per_g)
    if not result:
        raise HTTPException(status_code=404, detail="Altgold-Eintrag nicht gefunden")
    return await ScrapGoldService.get_by_id(db, scrap_gold_id)


@router.post("/scrap-gold/{scrap_gold_id}/sign", response_model=ScrapGoldRead)
@require_permission(Permission.ORDER_EDIT)
async def sign_receipt(
    scrap_gold_id: int,
    sign_data: ScrapGoldSignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Digitale Unterschrift des Kunden erfassen."""
    result = await ScrapGoldService.sign(db, scrap_gold_id, sign_data.signature_data)
    if not result:
        raise HTTPException(status_code=404, detail="Altgold-Eintrag nicht gefunden")
    return await ScrapGoldService.get_by_id(db, scrap_gold_id)


@router.get("/scrap-gold/alloy-calculator", response_model=AlloyCalculation)
@require_permission(Permission.ORDER_VIEW)
async def calculate_alloy(
    alloy: str,
    weight_g: float,
    current_user: User = Depends(get_current_user)
):
    """Feingold-Gehalt einer Legierung berechnen (Hilfstool)."""
    if alloy not in ALLOY_RATIOS:
        raise HTTPException(status_code=400, detail=f"Unbekannte Legierung: {alloy}")
    if weight_g <= 0:
        raise HTTPException(status_code=400, detail="Gewicht muss positiv sein")
    fine_content = ScrapGoldService.calculate_fine_content(alloy, weight_g)
    return AlloyCalculation(
        alloy=alloy,
        weight_g=weight_g,
        fine_content_g=fine_content,
        fine_content_percent=ALLOY_RATIOS[alloy] * 100
    )
