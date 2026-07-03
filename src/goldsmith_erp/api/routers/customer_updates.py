# src/goldsmith_erp/api/routers/customer_updates.py
"""
API endpoints for V1.2 Customer Updates & §649 BGB Cost Approval
(Kundeninfo & Kostenfreigabe).

Route overview (registered under the bare API prefix like handoffs.py —
mixed path roots, see main.py):
  POST   /api/v1/orders/{order_id}/updates            — create draft
  GET    /api/v1/orders/{order_id}/updates             — update history
  POST   /api/v1/updates/{update_id}/send              — send (or retry)
  GET    /api/v1/updates/{update_id}/pdf                — PDF download (no mutation)
  POST   /api/v1/updates/{update_id}/mark-delivered     — confirm manual delivery
  POST   /api/v1/orders/{order_id}/cost-changes         — create cost-change request
  GET    /api/v1/orders/{order_id}/cost-changes         — cost-change history
  POST   /api/v1/cost-changes/{cost_change_id}/send             — create+send linked update
  POST   /api/v1/cost-changes/{cost_change_id}/record-response  — log customer's answer
  GET    /api/v1/orders/{order_id}/projected-cost       — §649 cost projection

Permissions: CUSTOMER_UPDATE_VIEW/SEND for the updates family,
COST_CHANGE_VIEW/MANAGE for the cost-change + projected-cost family
(both ADMIN + GOLDSMITH only — VIEWER excluded, financial/design-IP data).

Exception mapping (typed exceptions from the two services; generic German
details, IDs-only — never user free-text):
  *NotFoundError / bare ValueError -> 404
  Invalid*StateError / NoQuoteAvailableError -> 409
  *ValidationError (photo ownership, missing template content) -> 422
"""
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import UpdateDeliveryMethod, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.customer_update import (
    CostChangeCreate,
    CostChangeRead,
    CostChangeRecordResponse,
    CustomerUpdateCreate,
    CustomerUpdateRead,
    CustomerUpdateSendResult,
    MarkDeliveredRequest,
    ProjectedCost,
)
from goldsmith_erp.services.cost_change_service import (
    CostChangeNotFoundError,
    CostChangeService,
    InvalidCostChangeStateError,
    NoQuoteAvailableError,
)
from goldsmith_erp.services.cost_watch_service import CostWatchService
from goldsmith_erp.services.customer_update_service import (
    CustomerUpdateNotFoundError,
    CustomerUpdateService,
    CustomerUpdateValidationError,
    InvalidUpdateStateError,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# CUSTOMER UPDATES (Kundeninfo)
# ============================================================================


@router.post(
    "/orders/{order_id}/updates",
    response_model=CustomerUpdateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Kundeninfo-Update-Entwurf erstellen",
)
@require_permission(Permission.CUSTOMER_UPDATE_SEND)
async def create_order_update(
    order_id: int,
    data: CustomerUpdateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Erstellt einen Update-Entwurf (DRAFT) fuer einen Auftrag.

    Fehlt subject/body, wird aus dem zu ``kind`` passenden Template
    vorbefuellt (ausser kind='custom' — dort sind beide Felder Pflicht).
    photo_ids muessen OrderPhoto-UUIDs DIESES Auftrags sein.
    """
    try:
        update = await CustomerUpdateService.create_draft(
            db,
            order_id=order_id,
            repair_job_id=None,
            data=data,
            user_id=current_user.id,
        )
    except CustomerUpdateValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CustomerUpdateRead.model_validate(update)


@router.get(
    "/orders/{order_id}/updates",
    response_model=list[CustomerUpdateRead],
    summary="Kundeninfo-Update-Verlauf eines Auftrags abrufen",
)
@require_permission(Permission.CUSTOMER_UPDATE_VIEW)
async def get_order_updates(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gibt alle Kundeninfo-Updates fuer einen Auftrag zurueck (neueste zuerst)."""
    updates = await CustomerUpdateService.list_for_order(db, order_id, current_user.id)
    return [CustomerUpdateRead.model_validate(u) for u in updates]


@router.post(
    "/updates/{update_id}/send",
    response_model=CustomerUpdateSendResult,
    summary="Kundeninfo-Update verschicken",
)
@require_permission(Permission.CUSTOMER_UPDATE_SEND)
async def send_update(
    update_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verschickt das Update per Email.

    Liefert IMMER 200 — auch bei fehlgeschlagenem Versand oder wenn SMTP
    nicht konfiguriert ist (``delivered=false``); der Entwurf bleibt in
    jedem Fall erhalten. Ein bereits verschicktes Update (Status "sent")
    kann nicht erneut verschickt werden (409).
    """
    try:
        return await CustomerUpdateService.send(db, update_id, current_user.id)
    except InvalidUpdateStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except CustomerUpdateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/updates/{update_id}/pdf",
    summary="Kundeninfo-Update als PDF herunterladen",
)
@require_permission(Permission.CUSTOMER_UPDATE_VIEW)
async def download_update_pdf(
    update_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liefert das Update als PDF (Fallback-Zustellung, ``delivery_method=
    pdf_manual``). Reiner Lesezugriff — markiert das Update NICHT als
    zugestellt (siehe POST .../mark-delivered fuer die explizite
    Bestaetigung).
    """
    try:
        pdf_bytes = await CustomerUpdateService.render_pdf(db, update_id)
    except CustomerUpdateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception:
        logger.exception(
            "PDF generation failed for customer update",
            extra={"update_id": update_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF-Generierung fehlgeschlagen. Bitte versuchen Sie es spaeter erneut.",
        )

    filename = f"kundeninfo_update_{update_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.post(
    "/updates/{update_id}/mark-delivered",
    response_model=CustomerUpdateRead,
    summary="Manuelle Zustellung bestaetigen (PDF persoenlich uebergeben)",
)
@require_permission(Permission.CUSTOMER_UPDATE_SEND)
async def mark_update_delivered(
    update_id: int,
    data: MarkDeliveredRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bestaetigt, dass das Update auf anderem Weg (PDF ausgedruckt/per
    WhatsApp verschickt) beim Kunden angekommen ist. Nur von DRAFT/
    SEND_FAILED aus moeglich — ein bereits verschicktes Update kann nicht
    erneut markiert werden (409).
    """
    try:
        update = await CustomerUpdateService.mark_delivered(
            db, update_id, current_user.id, method=UpdateDeliveryMethod(data.method)
        )
    except InvalidUpdateStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except CustomerUpdateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CustomerUpdateRead.model_validate(update)


# ============================================================================
# COST CHANGE REQUESTS (§649 BGB Kostenfreigabe)
# ============================================================================


@router.post(
    "/orders/{order_id}/cost-changes",
    response_model=CostChangeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Kostenaenderungsanfrage erstellen",
)
@require_permission(Permission.COST_CHANGE_MANAGE)
async def create_cost_change(
    order_id: int,
    data: CostChangeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Erstellt eine Kostenaenderungsanfrage (DRAFT). ``original_amount``
    stammt aus dem referenzierbaren Kostenvoranschlag des Auftrags (nicht
    aus dem Request-Body). Eine noch offene (SENT) Anfrage fuer denselben
    Auftrag wird automatisch superseded.
    """
    try:
        cost_change = await CostChangeService.create(
            db, order_id, data, current_user.id
        )
    except NoQuoteAvailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CostChangeRead.model_validate(cost_change)


@router.get(
    "/orders/{order_id}/cost-changes",
    response_model=list[CostChangeRead],
    summary="Kostenaenderungs-Verlauf eines Auftrags abrufen",
)
@require_permission(Permission.COST_CHANGE_VIEW)
async def get_order_cost_changes(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gibt alle Kostenaenderungsanfragen fuer einen Auftrag zurueck (neueste zuerst)."""
    requests = await CostChangeService.list_for_order(db, order_id, current_user.id)
    return [CostChangeRead.model_validate(r) for r in requests]


@router.post(
    "/cost-changes/{cost_change_id}/send",
    response_model=CustomerUpdateSendResult,
    summary="Kostenaenderungsanzeige verschicken",
)
@require_permission(Permission.COST_CHANGE_MANAGE)
async def send_cost_change(
    cost_change_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Erstellt und verschickt das verknuepfte Kundeninfo-Update (kind=
    cost_change) fuer diese Anfrage. Nur von DRAFT aus moeglich.
    """
    try:
        return await CostChangeService.send(db, cost_change_id, current_user.id)
    except InvalidCostChangeStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except CostChangeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/cost-changes/{cost_change_id}/record-response",
    response_model=CostChangeRead,
    summary="Kundenantwort auf Kostenaenderung erfassen",
)
@require_permission(Permission.COST_CHANGE_MANAGE)
async def record_cost_change_response(
    cost_change_id: int,
    data: CostChangeRecordResponse,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Erfasst die Antwort der Kundin (Zustimmung/Ablehnung) als Nachweis —
    kein Klick-Tracking, sondern manuelle Protokollierung durch die
    Goldschmiedin. Nur von Status "sent" aus moeglich.
    """
    try:
        cost_change = await CostChangeService.record_response(
            db, cost_change_id, data, current_user.id
        )
    except InvalidCostChangeStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except CostChangeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CostChangeRead.model_validate(cost_change)


# ============================================================================
# PROJECTED COST (§649 watcher — read-only, side-effect-free)
# ============================================================================


@router.get(
    "/orders/{order_id}/projected-cost",
    response_model=ProjectedCost,
    summary="Projizierte Kosten eines Auftrags abrufen",
)
@require_permission(Permission.COST_CHANGE_VIEW)
async def get_order_projected_cost(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liefert die aktuelle Kostenprojektion (Material + Edelsteine + Arbeit)
    und den Abgleich mit dem Kostenvoranschlag. Reiner Lesezugriff — nutzt
    ``CostWatchService.get_projected_cost`` (side-effect-free), NIEMALS
    ``check_order`` (wuerde eine Benachrichtigung ausloesen).
    """
    logger.info(
        "Financial data access",
        extra={
            "audit": True,
            "action": "financial_read",
            "entity": "projected_cost",
            "entity_id": None,
            "order_id": order_id,
            "user_id": current_user.id,
        },
    )
    return await CostWatchService.get_projected_cost(db, order_id)
