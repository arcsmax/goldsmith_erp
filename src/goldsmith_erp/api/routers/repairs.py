# src/goldsmith_erp/api/routers/repairs.py
"""
Repair tracking endpoints (Reparaturverwaltung).

All endpoints require authentication.  Write operations (create, status changes)
require REPAIR_CREATE or REPAIR_EDIT permission.  The list/detail endpoints
require REPAIR_VIEW which is granted to all roles including VIEWER.

SEC-01 / GDPR-03: list/detail strip ``estimated_cost``, ``actual_cost`` and
``estimated_value`` (insurance value) for callers without FINANCIAL_VIEW.
SEC-09 / GDPR-04: repair photos (list, file, thumbnail, and the ``photos``
array on the detail view) require DESIGN_VIEW.
"""

import logging
from typing import List, Optional, Union

from fastapi import APIRouter, Depends
from fastapi import File as FastAPIFile
from fastapi import Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.api.role_projection import (
    ExcludeSpec,
    build_excludes,
    project,
    project_response,
)
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import RepairJobStatus, RepairPhotoPhase, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.customer_update import (
    CustomerUpdateRead,
    CustomerUpdateSendResult,
)
from goldsmith_erp.models.pagination import (
    Page,
    PageParams,
    legacy_list_response,
    make_page_params,
    page_response,
)
from goldsmith_erp.models.repair import (
    IntakeChecklistUpdate,
    RepairCompleteInput,
    RepairDiagnoseInput,
    RepairJobCreate,
    RepairJobListItem,
    RepairJobRead,
    RepairPhotoRead,
    RepairStatusUpdate,
)
from goldsmith_erp.services import list_queries
from goldsmith_erp.services.customer_update_service import (
    CustomerUpdateNotFoundError,
    CustomerUpdateService,
    InvalidUpdateStateError,
)
from goldsmith_erp.services.label_service import LabelService
from goldsmith_erp.services.photo_service import PhotoValidationError
from goldsmith_erp.services.repair_photo_service import RepairPhotoService
from goldsmith_erp.services.repair_service import (
    InvalidChecklistPhotoError,
    NoCustomerUpdateDraftError,
    RepairService,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Fields removed from repair reads for callers without FINANCIAL_VIEW.
_REPAIR_FINANCIAL_FIELDS: frozenset[str] = frozenset(
    {"estimated_cost", "actual_cost", "estimated_value"}
)
# Fields removed for callers without DESIGN_VIEW (photos of the piece).
_REPAIR_DESIGN_FIELDS: frozenset[str] = frozenset({"photos"})


def _repair_excludes(user: User) -> ExcludeSpec:
    return build_excludes(
        user, financial=_REPAIR_FINANCIAL_FIELDS, design=_REPAIR_DESIGN_FIELDS
    )


def _media_type_from_ext(suffix: str) -> str:
    """Map a file extension to a MIME type for FileResponse."""
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    return mapping.get(suffix.lower(), "application/octet-stream")


# ============================================================================
# LIST + DETAIL
# ============================================================================


@router.get(
    "/",
    # W3-08: Page[...] when ``offset`` is sent, the legacy list otherwise.
    response_model=Union[Page[RepairJobListItem], List[RepairJobListItem]],
)
@require_permission(Permission.REPAIR_VIEW)
async def list_repairs(
    page: PageParams = Depends(make_page_params(legacy_default_limit=100)),
    status: Optional[RepairJobStatus] = Query(None, description="Nach Status filtern"),
    customer_id: Optional[int] = Query(None, gt=0, description="Nach Kunde filtern"),
    search: Optional[str] = Query(
        None, max_length=100, description="Suche in Nr, Tüte, Beschreibung"
    ),
    q: Optional[str] = Query(
        None,
        min_length=1,
        max_length=100,
        description="Suche in Nr, Tüte, Beschreibung, Kunde (nur mit offset)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liste aller Reparaturauftraege mit optionalen Filtern.

    Mit ``offset``: ``Page`` mit Gesamtzahl; ``q`` (oder ``search``) sucht
    zusaetzlich im Kundennamen. Ohne ``offset`` (veraltet): Liste mit Header
    ``X-Deprecated-List: true``.

    Gibt kompakte ListItem-Objekte zurueck (ohne Fotos und lange Felder).
    Ohne FINANCIAL_VIEW (VIEWER) entfaellt ``estimated_cost``.
    """
    excludes = _repair_excludes(current_user)
    if page.is_paged:
        stmt = await list_queries.repairs_statement(
            db, status=status, customer_id=customer_id, q=q or search
        )
        result = await list_queries.fetch_page(
            db, stmt, page, list_queries.REPAIR_LIST_OPTIONS
        )
        rows = [project(RepairJobListItem, r, excludes) for r in result.items]
        return page_response(rows, result.total, page)
    repairs = await RepairService.list_repairs(
        db,
        skip=page.offset,
        limit=page.limit,
        status=status,
        customer_id=customer_id,
        search=search,
    )
    return legacy_list_response(
        [project(RepairJobListItem, r, excludes) for r in repairs]
    )


@router.get("/{repair_id}", response_model=RepairJobRead)
@require_permission(Permission.REPAIR_VIEW)
async def get_repair(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reparaturauftrag Detailansicht mit Fotos.

    Ohne FINANCIAL_VIEW entfallen Kosten und Versicherungswert, ohne
    DESIGN_VIEW die Fotos (SEC-01, SEC-09).
    """
    repair = await RepairService.get_repair(db, repair_id)
    if repair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reparaturauftrag #{repair_id} nicht gefunden",
        )
    return project_response(RepairJobRead, repair, _repair_excludes(current_user))


@router.get("/{repair_id}/label", response_class=HTMLResponse)
@require_permission(Permission.REPAIR_VIEW)
async def get_repair_label(
    repair_id: int,
    width_mm: int = Query(89, ge=50, le=210, description="Label width in mm"),
    height_mm: int = Query(36, ge=20, le=297, description="Label height in mm"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Druckbares HTML-Etikett mit QR-Code fuer einen Reparaturauftrag.

    Returns a self-contained HTML document sized for label paper
    (default 89x36mm).  The page auto-triggers the browser print
    dialog on load.

    QR payload: ``REPAIR:<id>`` — reserved for future scanner support.
    """
    repair = await RepairService.get_repair(db, repair_id)
    if repair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reparaturauftrag #{repair_id} nicht gefunden",
        )
    workshop_name = getattr(settings, "APP_NAME", "Goldschmiede")
    html = LabelService.generate_repair_label_html(
        repair=repair,
        customer=repair.customer,
        workshop_name=workshop_name,
        label_width_mm=width_mm,
        label_height_mm=height_mm,
    )
    return HTMLResponse(content=html, status_code=200)


# ============================================================================
# CREATE
# ============================================================================


@router.post("/", response_model=RepairJobRead, status_code=status.HTTP_201_CREATED)
@require_permission(Permission.REPAIR_CREATE)
async def create_repair(
    data: RepairJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Neuen Reparaturauftrag aufnehmen (Eingang).

    Generiert automatisch Reparaturnummer (REP-YYYY-NNNN) und Tütennummer.
    Anfangsstatus ist immer RECEIVED.
    """
    repair = await RepairService.create_repair(db, data, current_user.id)
    # Reload with relationships for full response
    repair = await RepairService.get_repair(db, repair.id)
    return repair


# ============================================================================
# INTAKE CHECKLIST
# ============================================================================


@router.put("/{repair_id}/intake-checklist", response_model=RepairJobRead)
@require_permission(Permission.REPAIR_EDIT)
async def update_intake_checklist(
    repair_id: int,
    data: IntakeChecklistUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Eingangs-Checkliste aktualisieren (Foto-Verknuepfung oder
    "nicht zutreffend"-Begruendung je Punkt).

    Jeder Punkt mit Status "photo" muss auf ein INTAKE-Phase-Foto DIESES
    Auftrags verweisen — sonst 422. Unbekannter Auftrag -> 404.
    """
    # NOTE (reviewed, accepted): FastAPI's automatic 422 for schema-invalid
    # bodies echoes the submitted items (incl. na_reason free-text) back in
    # the validation-error response. That is a same-request echo to the
    # already-authenticated REPAIR_EDIT caller of data they themselves just
    # sent — same sensitivity tier as item_description on POST /repairs/.
    # Nothing is persisted or logged from that path; the deliberate
    # ID-only discipline applies to OUR raised errors (see
    # InvalidChecklistPhotoError), which can cross transactional()'s
    # error logger — not to FastAPI's request validation echo.
    try:
        repair = await RepairService.update_intake_checklist(db, repair_id, data.items)
    except InvalidChecklistPhotoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    repair = await RepairService.get_repair(db, repair.id)
    return repair


# ============================================================================
# STATUS TRANSITIONS
# ============================================================================


@router.post("/{repair_id}/diagnose", response_model=RepairJobRead)
@require_permission(Permission.REPAIR_EDIT)
async def diagnose_repair(
    repair_id: int,
    data: RepairDiagnoseInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Diagnose stellen und Kostenvoranschlag erfassen.

    Setzt Status auf DIAGNOSED dann QUOTED.
    Pflicht: Befundbeschreibung und Kostenvoranschlag in EUR.
    """
    try:
        repair = await RepairService.diagnose(db, repair_id, data, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    repair = await RepairService.get_repair(db, repair.id)
    return repair


@router.post("/{repair_id}/approve", response_model=RepairJobRead)
@require_permission(Permission.REPAIR_EDIT)
async def approve_repair(
    repair_id: int,
    data: RepairStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Kundenangebot genehmigt — Status wechselt zu APPROVED.

    Muss nach QUOTED aufgerufen werden, wenn der Kunde dem Kostenvoranschlag
    schriftlich oder muendlich zugestimmt hat.
    """
    try:
        repair = await RepairService.approve(db, repair_id, data, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    repair = await RepairService.get_repair(db, repair.id)
    return repair


@router.post("/{repair_id}/start", response_model=RepairJobRead)
@require_permission(Permission.REPAIR_EDIT)
async def start_repair(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reparaturarbeit beginnen — Status wechselt zu IN_REPAIR.

    Voraussetzung: Auftrag muss im Status APPROVED sein.
    """
    try:
        repair = await RepairService.start_repair(db, repair_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    repair = await RepairService.get_repair(db, repair.id)
    return repair


@router.post("/{repair_id}/quality-check", response_model=RepairJobRead)
@require_permission(Permission.REPAIR_EDIT)
async def submit_quality_check(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reparatur zur Qualitaetskontrolle einreichen — Status wechselt zu QUALITY_CHECK.

    Der Goldschmied erklaert die Reparaturarbeit als abgeschlossen.
    """
    try:
        repair = await RepairService.submit_for_quality_check(
            db, repair_id, current_user.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    repair = await RepairService.get_repair(db, repair.id)
    return repair


@router.post("/{repair_id}/complete", response_model=RepairJobRead)
@require_permission(Permission.REPAIR_EDIT)
async def complete_repair(
    repair_id: int,
    data: RepairCompleteInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reparatur fertigmelden — Status wechselt zu READY.

    Erfasst den tatsaechlichen Rechnungsbetrag (kann vom Kostenvoranschlag abweichen).
    Erstellt REPAIR_READY Benachrichtigungen fuer alle aktiven Benutzer UND einen
    Kundeninfo-Entwurf (Abholbereit). Der Kunde wird erst benachrichtigt, wenn
    dieser Entwurf per "Kunde benachrichtigen" verschickt wird (DOM-12 / W2-02) —
    siehe POST .../customer-updates/send.
    """
    try:
        repair = await RepairService.complete_repair(
            db, repair_id, data, current_user.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    repair = await RepairService.get_repair(db, repair.id)
    return repair


@router.post("/{repair_id}/pickup", response_model=RepairJobRead)
@require_permission(Permission.REPAIR_EDIT)
async def pickup_repair(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Abholung bestaetigen — Status wechselt zu PICKED_UP.

    Erfasst den Abholzeitpunkt. Kein weiterer Statuswechsel moeglich.
    """
    try:
        repair = await RepairService.pickup(db, repair_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    repair = await RepairService.get_repair(db, repair.id)
    return repair


@router.post("/{repair_id}/cancel", response_model=RepairJobRead)
@require_permission(Permission.REPAIR_EDIT)
async def cancel_repair(
    repair_id: int,
    data: RepairStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reparaturauftrag stornieren — moeglich aus allen aktiven Statusen.

    Nicht moeglich wenn bereits PICKED_UP oder CANCELLED.
    """
    try:
        repair = await RepairService.cancel(db, repair_id, data, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    repair = await RepairService.get_repair(db, repair.id)
    return repair


# ============================================================================
# CUSTOMER UPDATES (Kundeninfo) — DOM-12 / W2-02
#
# A pickup-ready draft is created automatically when the repair reaches
# READY (see POST /{repair_id}/complete -> RepairService.complete_repair).
# These two endpoints let staff view it and send it with one tap — the same
# CustomerUpdateService draft/send/dedupe mechanism the order-scoped
# /orders/{id}/updates family uses (api/routers/customer_updates.py), not a
# second notification path.
# ============================================================================


@router.get(
    "/{repair_id}/customer-updates",
    response_model=List[CustomerUpdateRead],
    summary="Kundeninfo-Update-Verlauf einer Reparatur abrufen",
)
@require_permission(Permission.CUSTOMER_UPDATE_VIEW)
async def get_repair_customer_updates(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Gibt alle Kundeninfo-Updates fuer eine Reparatur zurueck (neueste
    zuerst) — i. d. R. genau ein Abholbereit-Entwurf, automatisch erstellt
    beim Wechsel nach READY (siehe POST /{repair_id}/complete).
    """
    updates = await CustomerUpdateService.list_for_repair(
        db, repair_id, current_user.id
    )
    return [CustomerUpdateRead.model_validate(u) for u in updates]


@router.post(
    "/{repair_id}/customer-updates/send",
    response_model=CustomerUpdateSendResult,
    summary="Kundeninfo-Update der Reparatur verschicken",
)
@require_permission(Permission.CUSTOMER_UPDATE_SEND)
async def send_repair_customer_update(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verschickt den (i. d. R. einzigen) Kundeninfo-Entwurf dieser Reparatur
    per Email — "ein Tastendruck" (DOM-12 / W2-02).

    Setzt ``customer_notified_at`` auf der Reparatur NUR bei erfolgreicher
    Zustellung — niemals beim reinen Entwurf-Erstellen. Liefert IMMER 200
    bei einem gueltigen Entwurf, auch wenn SMTP nicht konfiguriert ist
    (``delivered=false``); die Goldschmiedin kann dann per PDF-Download +
    manueller Zustellbestaetigung ausweichen (siehe
    GET /updates/{update_id}/pdf und POST .../mark-delivered in
    api/routers/customer_updates.py). Kein Entwurf vorhanden -> 404.
    Bereits verschickt -> 409 (kein erneuter Versand).
    """
    try:
        return await RepairService.send_customer_update(db, repair_id, current_user.id)
    except NoCustomerUpdateDraftError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except CustomerUpdateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except InvalidUpdateStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/{repair_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permission(Permission.REPAIR_EDIT)
async def delete_repair(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reparaturauftrag soft-loeschen (DSGVO Art. 17 — 30-Tage-Schonfrist).

    Nur fuer PICKED_UP oder CANCELLED Auftraege erlaubt.
    """
    try:
        deleted = await RepairService.soft_delete(db, repair_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reparaturauftrag #{repair_id} nicht gefunden",
        )


# ============================================================================
# PHOTOS
#
# For these specific route patterns, the two-segment photo routes
# ("/photos/{photo_id}", "/photos/{photo_id}/thumbnail") cannot collide with
# the single-segment "/{repair_id}" route or the "/{repair_id}/photos" route:
# the literal "photos" first segment and differing segment counts keep them
# distinct regardless of declaration order (same shape as
# api/routers/consultations.py; covered by the roundtrip integration test).
# They are declared after the repair CRUD routes to keep the file's reading
# order aligned with the resource hierarchy.
# ============================================================================


@router.post(
    "/{repair_id}/photos",
    response_model=RepairPhotoRead,
    status_code=status.HTTP_201_CREATED,
)
@require_permission(Permission.REPAIR_EDIT)
async def upload_repair_photo(
    repair_id: int,
    file: UploadFile = FastAPIFile(..., description="JPEG, PNG oder WEBP (max 8 MB)"),
    phase: RepairPhotoPhase = Form(RepairPhotoPhase.INTAKE),
    notes: Optional[str] = Form(default=None, max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Foto zu einem Reparaturauftrag hochladen (multipart).

    Phase: INTAKE (Eingang), DURING_REPAIR (Waehrend Reparatur), COMPLETED (Fertig).
    Accepts JPEG, PNG, and WEBP files up to PHOTO_MAX_SIZE_MB.
    File type is validated via magic bytes — not by filename or Content-Type.
    """
    try:
        photo = await RepairPhotoService.upload_photo(
            db,
            repair_id=repair_id,
            file=file,
            user_id=current_user.id,
            phase=phase,
            notes=notes,
        )
    except PhotoValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    await db.commit()
    await db.refresh(photo)
    return photo


@router.get("/{repair_id}/photos", response_model=List[RepairPhotoRead])
@require_permission(Permission.DESIGN_VIEW)
async def list_photos(
    repair_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Alle Fotos eines Reparaturauftrags abrufen, nach Phase gruppiert."""
    repair = await RepairService.get_repair(db, repair_id)
    if repair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reparaturauftrag #{repair_id} nicht gefunden",
        )
    return repair.photos


@router.get("/photos/{photo_id}")
@require_permission(Permission.DESIGN_VIEW)
async def get_repair_photo_file(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Original-Foto herunterladen.

    Requires DESIGN_VIEW permission (GOLDSMITH/ADMIN; SEC-09, GDPR-04).
    """
    try:
        path = await RepairPhotoService.get_photo_path(db, photo_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if not path.exists():
        logger.warning(
            "Repair photo record exists but file is missing on disk",
            extra={"photo_id": photo_id},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Foto-Datei nicht auf dem Server gefunden",
        )

    return FileResponse(
        path=str(path),
        media_type=_media_type_from_ext(path.suffix),
        filename=path.name,
    )


@router.get("/photos/{photo_id}/thumbnail")
@require_permission(Permission.DESIGN_VIEW)
async def get_repair_photo_thumbnail(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Miniaturansicht herunterladen. Faellt auf das Original zurueck, falls keine
    Miniaturansicht existiert (z. B. bei fehlgeschlagener Thumbnail-Erzeugung).

    Requires DESIGN_VIEW permission (GOLDSMITH/ADMIN; SEC-09, GDPR-04).
    """
    try:
        thumb_path = await RepairPhotoService.get_photo_path(
            db, photo_id, thumbnail=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if thumb_path.exists():
        return FileResponse(
            path=str(thumb_path),
            media_type="image/jpeg",
            filename=thumb_path.name,
        )

    # Fallback: serve original if thumbnail is missing (mirrors consultations.py)
    original_path = await RepairPhotoService.get_photo_path(db, photo_id)
    if original_path.exists():
        logger.debug(
            "Repair photo thumbnail missing, serving original",
            extra={"photo_id": photo_id},
        )
        return FileResponse(
            path=str(original_path),
            media_type=_media_type_from_ext(original_path.suffix),
            filename=original_path.name,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Foto-Datei nicht auf dem Server gefunden",
    )


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permission(Permission.REPAIR_EDIT)
async def delete_repair_photo(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Foto loeschen (Datei, Thumbnail und Datenbankeintrag).

    Requires REPAIR_EDIT permission.
    """
    try:
        await RepairPhotoService.delete_photo(db, photo_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    await db.commit()
