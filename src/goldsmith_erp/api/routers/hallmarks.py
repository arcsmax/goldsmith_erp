# src/goldsmith_erp/api/routers/hallmarks.py
"""
Hallmarking endpoints (Punzierung).

All endpoints are scoped under /orders/{order_id}/hallmarks.
Read access requires HALLMARK_VIEW (granted to all authenticated roles except
external — see permissions.py).  Write access requires HALLMARK_CREATE or
HALLMARK_EDIT (GOLDSMITH and ADMIN only).

German law (Edelmetallgesetz) obliges goldsmiths to stamp pieces above
threshold weights with a Feingehaltsstempel.  These endpoints let the workshop
track submission to the Pruefstelle, approval, and physical stamping.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import HallmarkStatus, HallmarkType, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.services.hallmark_service import HallmarkService

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic schemas
# ============================================================================


class HallmarkCreate(BaseModel):
    """Request body for creating a new hallmark record."""

    hallmark_type: HallmarkType = Field(
        ...,
        description=(
            "Typ der Punze: FINENESS_MARK (Feingehaltsstempel), "
            "MAKERS_MARK (Herstellermarke), ASSAY_OFFICE (Beschauzeichen), "
            "COMMON_CONTROL (CCM), DATE_LETTER"
        ),
    )
    assay_office: Optional[str] = Field(
        None,
        max_length=100,
        description="Pruefstelle, z.B. 'Pforzheim' oder 'Schwaebisch Gmuend'",
    )
    notes: Optional[str] = Field(None, description="Freitext-Anmerkungen")


class HallmarkStatusUpdate(BaseModel):
    """Request body for a status transition."""

    new_status: HallmarkStatus = Field(..., description="Neuer Status")
    certificate_number: Optional[str] = Field(
        None,
        max_length=100,
        description="Zertifikatsnummer der Pruefstelle (beim APPROVED-Uebergang)",
    )
    notes: Optional[str] = Field(None, description="Begründung oder Anmerkungen")


class HallmarkUpdate(BaseModel):
    """Request body for updating mutable fields (no status change)."""

    assay_office: Optional[str] = Field(None, max_length=100)
    certificate_number: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class HallmarkRead(BaseModel):
    """Response schema for a hallmark record."""

    id: int
    order_id: int
    hallmark_type: HallmarkType
    status: HallmarkStatus
    assay_office: Optional[str]
    certificate_number: Optional[str]
    submitted_at: Optional[str]
    approved_at: Optional[str]
    stamped_at: Optional[str]
    notes: Optional[str]
    created_at: str
    created_by: Optional[int]

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_model(cls, obj) -> "HallmarkRead":
        def _dt(val) -> Optional[str]:
            return val.isoformat() if val else None

        return cls(
            id=obj.id,
            order_id=obj.order_id,
            hallmark_type=obj.hallmark_type,
            status=obj.status,
            assay_office=obj.assay_office,
            certificate_number=obj.certificate_number,
            submitted_at=_dt(obj.submitted_at),
            approved_at=_dt(obj.approved_at),
            stamped_at=_dt(obj.stamped_at),
            notes=obj.notes,
            created_at=_dt(obj.created_at) or "",
            created_by=obj.created_by,
        )


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/orders/{order_id}/hallmarks",
    response_model=List[HallmarkRead],
    summary="Alle Punzierungen eines Auftrags",
)
@require_permission(Permission.HALLMARK_VIEW)
async def list_hallmarks(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[HallmarkRead]:
    """
    Liste aller Punzierungsdatensaetze fuer einen Auftrag.

    Gibt die Records in absteigender Erstellungsreihenfolge zurueck.
    """
    hallmarks = await HallmarkService.get_hallmarks_for_order(db, order_id)
    return [HallmarkRead.from_orm_model(h) for h in hallmarks]


@router.get(
    "/orders/{order_id}/hallmarks/{hallmark_id}",
    response_model=HallmarkRead,
    summary="Punzierung Detailansicht",
)
@require_permission(Permission.HALLMARK_VIEW)
async def get_hallmark(
    order_id: int,
    hallmark_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HallmarkRead:
    hallmark = await HallmarkService.get_hallmark(db, hallmark_id)
    if hallmark is None or hallmark.order_id != order_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Punzierung {hallmark_id} nicht gefunden",
        )
    return HallmarkRead.from_orm_model(hallmark)


@router.post(
    "/orders/{order_id}/hallmarks",
    response_model=HallmarkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Neue Punzierung anlegen",
)
@require_permission(Permission.HALLMARK_CREATE)
async def create_hallmark(
    order_id: int,
    body: HallmarkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HallmarkRead:
    """
    Legt einen neuen Punzierungsdatensatz fuer einen Auftrag an.

    Startet immer mit Status PENDING.  Der Goldschmied kann danach den
    Einreichungsprozess (SUBMITTED) und das Genehmigungsverfahren
    (APPROVED -> STAMPED) ueber den Status-Endpunkt steuern.
    """
    try:
        hallmark = await HallmarkService.create_hallmark(
            db=db,
            order_id=order_id,
            hallmark_type=body.hallmark_type,
            created_by_id=current_user.id,
            assay_office=body.assay_office,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    logger.info(
        "Hallmark created via API",
        extra={
            "hallmark_id": hallmark.id,
            "order_id": order_id,
            "user_id": current_user.id,
        },
    )
    return HallmarkRead.from_orm_model(hallmark)


@router.patch(
    "/orders/{order_id}/hallmarks/{hallmark_id}",
    response_model=HallmarkRead,
    summary="Punzierungs-Felder aktualisieren (ohne Statusaenderung)",
)
@require_permission(Permission.HALLMARK_EDIT)
async def update_hallmark(
    order_id: int,
    hallmark_id: int,
    body: HallmarkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HallmarkRead:
    """Aktualisiert Pruefstelle, Zertifikatsnummer oder Notizen."""
    # Verify ownership to the correct order
    hallmark = await HallmarkService.get_hallmark(db, hallmark_id)
    if hallmark is None or hallmark.order_id != order_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Punzierung {hallmark_id} nicht gefunden",
        )

    try:
        updated = await HallmarkService.update_hallmark(
            db=db,
            hallmark_id=hallmark_id,
            assay_office=body.assay_office,
            certificate_number=body.certificate_number,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return HallmarkRead.from_orm_model(updated)


@router.post(
    "/orders/{order_id}/hallmarks/{hallmark_id}/status",
    response_model=HallmarkRead,
    summary="Punzierungs-Status aendern",
)
@require_permission(Permission.HALLMARK_EDIT)
async def update_hallmark_status(
    order_id: int,
    hallmark_id: int,
    body: HallmarkStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HallmarkRead:
    """
    Fuehrt eine Statusaenderung durch.

    Erlaubte Uebergaenge:
      PENDING -> SUBMITTED
      SUBMITTED -> APPROVED | REJECTED
      APPROVED -> STAMPED
      REJECTED -> SUBMITTED  (Wiedereinreichung nach Nacharbeit)
    """
    hallmark = await HallmarkService.get_hallmark(db, hallmark_id)
    if hallmark is None or hallmark.order_id != order_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Punzierung {hallmark_id} nicht gefunden",
        )

    try:
        updated = await HallmarkService.transition_status(
            db=db,
            hallmark_id=hallmark_id,
            new_status=body.new_status,
            certificate_number=body.certificate_number,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    logger.info(
        "Hallmark status changed via API",
        extra={
            "hallmark_id": hallmark_id,
            "new_status": body.new_status.value,
            "user_id": current_user.id,
        },
    )
    return HallmarkRead.from_orm_model(updated)


@router.delete(
    "/orders/{order_id}/hallmarks/{hallmark_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Punzierung loeschen (nur PENDING)",
)
@require_permission(Permission.HALLMARK_EDIT)
async def delete_hallmark(
    order_id: int,
    hallmark_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Loescht einen Punzierungsdatensatz.

    Nur erlaubt wenn Status == PENDING.  Eingereichte oder genehmigte
    Records sind rechtliche Dokumentation und koennen nicht geloescht werden.
    """
    hallmark = await HallmarkService.get_hallmark(db, hallmark_id)
    if hallmark is None or hallmark.order_id != order_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Punzierung {hallmark_id} nicht gefunden",
        )

    try:
        await HallmarkService.delete_hallmark(db, hallmark_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
