# src/goldsmith_erp/api/routers/handoffs.py
"""
API endpoints for the order handoff protocol (Stabuebergabe).

Handoffs represent the formal moment a goldsmith finishes their part of an
order and passes it to the next craftsperson.  The recipient must explicitly
accept or decline before the order changes hands in the system.

Route overview:
  POST   /api/v1/orders/{order_id}/handoff         — create handoff
  PUT    /api/v1/handoffs/{handoff_id}/accept       — accept incoming handoff
  PUT    /api/v1/handoffs/{handoff_id}/decline      — decline with reason
  GET    /api/v1/handoffs/pending                   — my pending handoffs
  GET    /api/v1/orders/{order_id}/handoffs         — order's handoff history
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.handoff import (
    HandoffAccept,
    HandoffCreate,
    HandoffDecline,
    HandoffRead,
)
from goldsmith_erp.services.handoff_service import HandoffService

router = APIRouter()


# ---------------------------------------------------------------------------
# Create handoff — attached to the orders router via main.py prefix wiring
# ---------------------------------------------------------------------------

@router.post(
    "/orders/{order_id}/handoff",
    response_model=HandoffRead,
    status_code=status.HTTP_201_CREATED,
    summary="Auftrag uebergeben (Stabuebergabe erstellen)",
)
@require_permission(Permission.HANDOFF_CREATE)
async def create_handoff(
    order_id: int,
    handoff_in: HandoffCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Erstellt eine neue Uebergabe fuer den Auftrag.

    Der Empfaenger erhaelt eine Benachrichtigung und muss die Uebergabe
    bestaetigen oder ablehnen.  Bis dahin hat die Uebergabe den Status PENDING.
    """
    try:
        return await HandoffService.create_handoff(
            db=db,
            order_id=order_id,
            from_user_id=current_user.id,
            to_user_id=handoff_in.to_user_id,
            handoff_type=handoff_in.handoff_type,
            notes=handoff_in.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


# ---------------------------------------------------------------------------
# Handoff history for an order — also uses the orders prefix
# ---------------------------------------------------------------------------

@router.get(
    "/orders/{order_id}/handoffs",
    response_model=List[HandoffRead],
    summary="Uebergabe-Protokoll eines Auftrags abrufen",
)
@require_permission(Permission.HANDOFF_VIEW)
async def get_order_handoffs(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Gibt alle Uebergaben fuer einen Auftrag zurueck (neueste zuerst).

    Zeigt die vollstaendige Produktionskette: wer hat das Stueck wann an wen
    weitergegeben und welche Schritte wurden bestaetigt oder abgelehnt.
    """
    return await HandoffService.get_order_handoff_history(db, order_id)


# ---------------------------------------------------------------------------
# Pending handoffs for the current user
# ---------------------------------------------------------------------------

@router.get(
    "/handoffs/pending",
    response_model=List[HandoffRead],
    summary="Meine offenen Uebergaben abrufen",
)
@require_permission(Permission.HANDOFF_VIEW)
async def get_pending_handoffs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Gibt alle offenen (PENDING) Uebergaben zurueck, bei denen der aktuelle
    Benutzer der Empfaenger ist.

    Typische Verwendung: Badge-Zaehler und Aufgabenliste im Dashboard.
    """
    return await HandoffService.get_pending_handoffs(db, current_user.id)


# ---------------------------------------------------------------------------
# Accept / decline
# ---------------------------------------------------------------------------

@router.put(
    "/handoffs/{handoff_id}/accept",
    response_model=HandoffRead,
    summary="Uebergabe bestaetigen",
)
@require_permission(Permission.HANDOFF_RESPOND)
async def accept_handoff(
    handoff_id: int,
    accept_in: HandoffAccept = HandoffAccept(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bestaetigt die Uebergabe als Empfaenger.

    Setzt den Status auf ACCEPTED, schickt eine Benachrichtigung an den
    Uebergeber und veroeffentlicht ein WebSocket-Event.

    Nur der in der Uebergabe vorgesehene Empfaenger darf diesen Endpunkt
    aufrufen.  Bereits beantwortete Uebergaben koennen nicht erneut bearbeitet
    werden.
    """
    try:
        return await HandoffService.accept_handoff(
            db=db,
            handoff_id=handoff_id,
            user_id=current_user.id,
            response_notes=accept_in.response_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.put(
    "/handoffs/{handoff_id}/decline",
    response_model=HandoffRead,
    summary="Uebergabe ablehnen",
)
@require_permission(Permission.HANDOFF_RESPOND)
async def decline_handoff(
    handoff_id: int,
    decline_in: HandoffDecline,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lehnt die Uebergabe ab und begruendet die Ablehnung.

    Eine Begruendung ist Pflicht — der Uebergeber muss wissen, warum das Stueck
    nicht uebernommen wurde, bevor er die Nacharbeit anordnen oder eine neue
    Uebergabe erstellen kann.

    Setzt den Status auf DECLINED und benachrichtigt den Uebergeber mit der
    Begruendung.
    """
    try:
        return await HandoffService.decline_handoff(
            db=db,
            handoff_id=handoff_id,
            user_id=current_user.id,
            response_notes=decline_in.response_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
