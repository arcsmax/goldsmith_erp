# src/goldsmith_erp/api/routers/photos.py
"""
Photo documentation router for order photos.

Provides multipart upload, listing, serving, and deletion of order photos.
Thumbnails (200px wide JPEG) are generated automatically on upload.

Endpoints:
  POST   /api/v1/orders/{order_id}/photos           - Upload photo (multipart)
  GET    /api/v1/orders/{order_id}/photos           - List photos for an order
  GET    /api/v1/photos/{photo_id}/file             - Serve original photo
  GET    /api/v1/photos/{photo_id}/thumbnail        - Serve thumbnail (200px JPEG)
  DELETE /api/v1/photos/{photo_id}                  - Delete photo + thumbnail

File type validation uses magic bytes (JPEG / PNG / WEBP only).
Maximum upload size is controlled by settings.PHOTO_MAX_SIZE_MB.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.order_photo import OrderPhotoRead
from goldsmith_erp.services.photo_service import (
    PhotoService,
    PhotoValidationError,
    get_photo_path,
    get_thumbnail_path,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Upload ───────────────────────────────────────────────────────────────────


@router.post(
    "/orders/{order_id}/photos",
    response_model=OrderPhotoRead,
    status_code=status.HTTP_201_CREATED,
)
@require_permission(Permission.ORDER_EDIT)
async def upload_photo(
    order_id: int,
    file: UploadFile = File(..., description="JPEG, PNG, or WEBP image (max 8 MB)"),
    notes: Optional[str] = Form(default=None, max_length=500),
    time_entry_id: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Foto hochladen (Upload a photo for an order).

    Accepts JPEG, PNG, and WEBP files up to PHOTO_MAX_SIZE_MB.
    File type is validated via magic bytes — not by filename or Content-Type.
    A 200px-wide JPEG thumbnail is created automatically.

    Requires ORDER_EDIT permission.
    """
    try:
        photo = await PhotoService.upload_photo(
            db=db,
            order_id=order_id,
            file=file,
            user_id=current_user.id,
            notes=notes,
            time_entry_id=time_entry_id,
        )
    except PhotoValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception:
        logger.exception(
            "Unexpected error during photo upload",
            extra={"order_id": order_id, "user_id": current_user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Foto-Upload fehlgeschlagen. Bitte versuchen Sie es später erneut.",
        )

    await db.commit()
    await db.refresh(photo)
    return photo


# ─── List ─────────────────────────────────────────────────────────────────────


@router.get(
    "/orders/{order_id}/photos",
    response_model=List[OrderPhotoRead],
)
@require_permission(Permission.ORDER_VIEW)
async def list_photos(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fotos eines Auftrags auflisten (List photos for an order).

    Returns metadata for all photos attached to the order, sorted by
    upload time (oldest first). Use the file/thumbnail endpoints to
    retrieve the actual image data.

    Requires ORDER_VIEW permission.
    """
    photos = await PhotoService.get_photos(db, order_id)
    return photos


# ─── Serve original ───────────────────────────────────────────────────────────


@router.get("/photos/{photo_id}/file")
@require_permission(Permission.ORDER_VIEW)
async def get_photo_file(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Originalfoto herunterladen (Serve the original photo file).

    Returns the full-resolution image via FileResponse.
    Content-Type is inferred from the file extension.

    Requires ORDER_VIEW permission.
    """
    photo = await PhotoService.get_photo(db, photo_id)
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Foto {photo_id} nicht gefunden",
        )

    path = get_photo_path(photo)
    if path is None or not path.exists():
        logger.warning(
            "Photo record exists but file is missing on disk",
            extra={"photo_id": photo_id, "path": str(path)},
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


# ─── Serve thumbnail ──────────────────────────────────────────────────────────


@router.get("/photos/{photo_id}/thumbnail")
@require_permission(Permission.ORDER_VIEW)
async def get_photo_thumbnail(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Miniaturansicht herunterladen (Serve the 200px thumbnail).

    Returns a 200px-wide JPEG thumbnail generated at upload time.
    Falls back to the original file if no thumbnail exists (e.g. for
    photos uploaded before thumbnail support was added).

    Requires ORDER_VIEW permission.
    """
    photo = await PhotoService.get_photo(db, photo_id)
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Foto {photo_id} nicht gefunden",
        )

    thumb_path = get_thumbnail_path(photo)
    if thumb_path and thumb_path.exists():
        return FileResponse(
            path=str(thumb_path),
            media_type="image/jpeg",
            filename=thumb_path.name,
        )

    # Fallback: serve original if thumbnail is missing
    original_path = get_photo_path(photo)
    if original_path and original_path.exists():
        logger.debug(
            "Thumbnail missing, serving original",
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


# ─── Delete ───────────────────────────────────────────────────────────────────


@router.delete(
    "/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@require_permission(Permission.ORDER_EDIT)
async def delete_photo(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Foto löschen (Delete a photo and its thumbnail).

    Removes both the filesystem files and the database record.
    Returns 204 No Content on success, 404 if not found.

    Requires ORDER_EDIT permission.
    """
    deleted = await PhotoService.delete_photo(db, photo_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Foto {photo_id} nicht gefunden",
        )
    await db.commit()


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
