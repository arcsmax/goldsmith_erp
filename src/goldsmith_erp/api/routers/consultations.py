# src/goldsmith_erp/api/routers/consultations.py
"""Beratungs-API (V1.1). Design-IP: nur ADMIN/GOLDSMITH.

Endpoints:
  POST   /api/v1/consultations/                          - create consultation
  GET    /api/v1/consultations/                           - list consultations
  GET    /api/v1/consultations/{id}                       - get single consultation
  PATCH  /api/v1/consultations/{id}                        - autosave update
  POST   /api/v1/consultations/{id}/convert                - convert to quote/order
  POST   /api/v1/consultations/{id}/photos                 - upload photo (multipart)
  GET    /api/v1/consultations/{id}/photos                 - list photos
  GET    /api/v1/consultations/photos/{photo_id}            - serve original
  GET    /api/v1/consultations/photos/{photo_id}/thumbnail  - serve thumbnail
  DELETE /api/v1/consultations/photos/{photo_id}            - delete photo

Consultations contain business-confidential design intent (custom jewelry
wishes, budgets) — every route requires CONSULTATION_VIEW/CREATE/EDIT, which
is granted only to GOLDSMITH and ADMIN (see core/permissions.py). VIEWER has
none of these permissions and is rejected with 403 on every route.

The two-segment photo routes ("/photos/{photo_id}", "/photos/{photo_id}/thumbnail")
cannot be shadowed by the single-segment "/{consultation_id}" route or the
"/{consultation_id}/photos" route — Starlette matches by segment count and
literal-segment position, not just declaration order — but they are declared
after the consultation CRUD routes to keep the file's reading order aligned
with the resource hierarchy.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi import File as FastAPIFile
from fastapi import Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import ConsultationPhotoKind, ConsultationStatus, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.consultation import (
    ConsultationConvertRequest,
    ConsultationCreate,
    ConsultationListItem,
    ConsultationPhotoRead,
    ConsultationRead,
    ConsultationUpdate,
)
from goldsmith_erp.services.consultation_photo_service import ConsultationPhotoService
from goldsmith_erp.services.consultation_service import (
    AlreadyConvertedError,
    ConsultationNotFoundError,
    ConsultationService,
)
from goldsmith_erp.services.photo_service import PhotoValidationError

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _media_type_from_ext(suffix: str) -> str:
    """Map a file extension to a MIME type for FileResponse."""
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    return mapping.get(suffix.lower(), "application/octet-stream")


def _raise_not_found_or_conflict(exc: ValueError) -> None:
    """Map a service ValueError to 404 or 409 — typed dispatch via
    ``isinstance``, no string matching and no raise-then-catch indirection
    (pattern precedent: ``DuplicateNoGoError`` in no_go_service.py /
    customers.py). ``ConsultationNotFoundError`` -> 404; any other
    ``ValueError`` is a business-rule conflict -> 409.

    Both raises use ``from None``: consultation ValueErrors can carry
    design-IP wish text in ``__context__`` (the underlying exception chain),
    and FastAPI/logging may render that chain — suppressing it keeps that
    text from leaking, matching the tested no_go_service pattern (see
    ``DuplicateNoGoError`` in ``services/no_go_service.py``).
    """
    if isinstance(exc, ConsultationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from None
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None


# ─── Create ─────────────────────────────────────────────────────────────────


@router.post(
    "/",
    response_model=ConsultationRead,
    status_code=status.HTTP_201_CREATED,
)
@require_permission(Permission.CONSULTATION_CREATE)
async def create_consultation(
    consultation_in: ConsultationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Neue Beratung anlegen (Start eines Beratungsgesprächs).

    Requires CONSULTATION_CREATE permission.
    """
    try:
        return await ConsultationService.create_consultation(
            db, consultation_in, conducted_by_user_id=current_user.id
        )
    except ValueError as exc:
        _raise_not_found_or_conflict(exc)


# ─── List ───────────────────────────────────────────────────────────────────


@router.get("/", response_model=List[ConsultationListItem])
@require_permission(Permission.CONSULTATION_VIEW)
async def list_consultations(
    customer_id: Optional[int] = Query(None, gt=0, description="Nach Kunde filtern"),
    status: Optional[ConsultationStatus] = Query(
        None, description="Nach Status filtern"
    ),
    limit: int = Query(100, ge=1, le=500, description="Maximale Ergebnisanzahl"),
    offset: int = Query(0, ge=0, description="Datensaetze ueberspringen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Beratungen auflisten, optional gefiltert nach Kunde und Status.

    Requires CONSULTATION_VIEW permission.
    """
    return await ConsultationService.list_consultations(
        db, customer_id=customer_id, status=status, limit=limit, offset=offset
    )


# ─── Get ────────────────────────────────────────────────────────────────────


@router.get("/{consultation_id}", response_model=ConsultationRead)
@require_permission(Permission.CONSULTATION_VIEW)
async def get_consultation(
    consultation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Einzelne Beratung abrufen.

    Requires CONSULTATION_VIEW permission.
    """
    consultation = await ConsultationService.get_consultation(db, consultation_id)
    if consultation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consultation {consultation_id} not found",
        )
    return consultation


# ─── Update (autosave) ────────────────────────────────────────────────────────


@router.patch("/{consultation_id}", response_model=ConsultationRead)
@require_permission(Permission.CONSULTATION_EDIT)
async def update_consultation(
    consultation_id: int,
    update_in: ConsultationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Beratung aktualisieren (Autosave — nur gesetzte Felder werden übernommen).

    404 wenn die Beratung nicht existiert, 409 wenn sie bereits konvertiert
    wurde und ein nicht mehr veränderbares Feld geändert werden soll.

    Requires CONSULTATION_EDIT permission.
    """
    try:
        return await ConsultationService.update_consultation(
            db, consultation_id, update_in
        )
    except ValueError as exc:
        _raise_not_found_or_conflict(exc)


# ─── Convert ────────────────────────────────────────────────────────────────


@router.post("/{consultation_id}/convert", response_model=ConsultationRead)
@require_permission(Permission.CONSULTATION_EDIT)
async def convert_consultation(
    consultation_id: int,
    convert_in: ConsultationConvertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Beratung in Auftrag oder Kostenvoranschlag überführen.

    Idempotent: eine bereits konvertierte Beratung liefert 409 mit den
    vorhandenen Ziel-IDs im detail-Body (order_id/quote_id).

    Requires CONSULTATION_EDIT permission.
    """
    try:
        return await ConsultationService.convert_consultation(
            db, consultation_id, convert_in.target, current_user
        )
    except AlreadyConvertedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Beratung wurde bereits konvertiert",
                "order_id": exc.order_id,
                "quote_id": exc.quote_id,
            },
        )
    except ValidationError:
        # OrderCreate/QuoteCreate rejected the derived content (e.g. the
        # SQL-keyword sanitizer on title/description/notes tripped on the
        # consultation's wishes text). pydantic.ValidationError IS a
        # ValueError subclass, so this MUST be checked before the generic
        # ValueError branch below — and its detail must stay GENERIC: the
        # underlying error embeds the offending input value, which can be
        # customer wish text / business-confidential design intent.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Beratung konnte nicht konvertiert werden — ungültige Eingabe.",
        ) from None
    except ConsultationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from None
    except ValueError as exc:
        # Defensive fallback for any other service-layer ValueError (e.g. an
        # order-service business rule) — preserves the pre-existing
        # blanket-404 behaviour for anything not explicitly typed above.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ─── Photos: upload ─────────────────────────────────────────────────────────


@router.post(
    "/{consultation_id}/photos",
    response_model=ConsultationPhotoRead,
    status_code=status.HTTP_201_CREATED,
)
@require_permission(Permission.CONSULTATION_EDIT)
async def upload_consultation_photo(
    consultation_id: int,
    file: UploadFile = FastAPIFile(..., description="JPEG, PNG oder WEBP (max 8 MB)"),
    kind: ConsultationPhotoKind = Form(ConsultationPhotoKind.SKETCH),
    notes: Optional[str] = Form(default=None, max_length=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Skizze/Referenzfoto zu einer Beratung hochladen.

    Accepts JPEG, PNG, and WEBP files up to PHOTO_MAX_SIZE_MB.
    File type is validated via magic bytes — not by filename or Content-Type.

    Requires CONSULTATION_EDIT permission.
    """
    try:
        photo = await ConsultationPhotoService.upload_photo(
            db,
            consultation_id=consultation_id,
            file=file,
            user_id=current_user.id,
            kind=kind,
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


# ─── Photos: list ───────────────────────────────────────────────────────────


@router.get("/{consultation_id}/photos", response_model=List[ConsultationPhotoRead])
@require_permission(Permission.CONSULTATION_VIEW)
async def list_consultation_photos(
    consultation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fotos einer Beratung auflisten.

    Requires CONSULTATION_VIEW permission.
    """
    return await ConsultationPhotoService.list_photos(db, consultation_id)


# ─── Photos: serve original ─────────────────────────────────────────────────


@router.get("/photos/{photo_id}")
@require_permission(Permission.CONSULTATION_VIEW)
async def get_consultation_photo_file(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Original-Foto herunterladen.

    Requires CONSULTATION_VIEW permission.
    """
    try:
        path = await ConsultationPhotoService.get_photo_path(db, photo_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if not path.exists():
        logger.warning(
            "Consultation photo record exists but file is missing on disk",
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


# ─── Photos: serve thumbnail ──────────────────────────────────────────────────


@router.get("/photos/{photo_id}/thumbnail")
@require_permission(Permission.CONSULTATION_VIEW)
async def get_consultation_photo_thumbnail(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Miniaturansicht herunterladen. Fällt auf das Original zurück, falls keine
    Miniaturansicht existiert (z. B. bei fehlgeschlagener Thumbnail-Erzeugung).

    Requires CONSULTATION_VIEW permission.
    """
    try:
        thumb_path = await ConsultationPhotoService.get_photo_path(
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

    # Fallback: serve original if thumbnail is missing (mirrors photos.py)
    original_path = await ConsultationPhotoService.get_photo_path(db, photo_id)
    if original_path.exists():
        logger.debug(
            "Consultation thumbnail missing, serving original",
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


# ─── Photos: delete ─────────────────────────────────────────────────────────


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permission(Permission.CONSULTATION_EDIT)
async def delete_consultation_photo(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Foto löschen (Datei, Thumbnail und Datenbankeintrag).

    Requires CONSULTATION_EDIT permission.
    """
    try:
        await ConsultationPhotoService.delete_photo(db, photo_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    await db.commit()
