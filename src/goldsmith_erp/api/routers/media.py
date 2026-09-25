# src/goldsmith_erp/api/routers/media.py
"""
Unified media endpoints (ARCH phase 4, ADR-2026-09-25-media).

Endpoints:
  GET    /api/v1/media?owner_type=order&owner_id=42   - list an owner's media
  GET    /api/v1/media/{media_id}                     - serve the original
  GET    /api/v1/media/{media_id}/thumbnail           - serve the thumbnail

Authorization is owner based and mirrors the photo routers: every read
needs DESIGN_VIEW (design IP, SEC-09 / GDPR-04 — VIEWER gets 403) plus the
owner's view permission (see ``MediaService.OWNER_PERMISSIONS``). Uploads
stay on the owner routes (``/orders/{id}/photos`` …), which store through
the same ``MediaService``.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import (
    Permission,
    has_permission,
    require_permission,
)
from goldsmith_erp.db.models import MediaAsset, MediaOwnerType, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.media_asset import MediaAssetRead
from goldsmith_erp.services.media_service import (
    OWNER_PERMISSIONS,
    MediaNotFoundError,
    MediaService,
)
from goldsmith_erp.services.media_store import mime_for_suffix

logger = logging.getLogger(__name__)

router = APIRouter()

_NOT_FOUND = "Medium nicht gefunden"
_FILE_MISSING = "Mediendatei nicht auf dem Server gefunden"
_FORBIDDEN = "Keine Berechtigung für dieses Medium"


async def _viewable_asset(db: AsyncSession, media_id: str, user: User) -> MediaAsset:
    """Load a live asset and enforce the owner-based read rule."""
    try:
        asset = await MediaService.get(db, media_id)
    except MediaNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if not MediaService.can_view(user, asset):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN)
    return asset


@router.get("", response_model=List[MediaAssetRead])
@require_permission(Permission.DESIGN_VIEW)  # type: ignore[misc]
async def list_media(
    owner_type: MediaOwnerType = Query(...),
    owner_id: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[MediaAsset]:
    """Medien eines Auftrags / einer Reparatur / Beratung auflisten."""
    view_perm, _ = OWNER_PERMISSIONS[owner_type]
    if not has_permission(current_user, view_perm):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN)
    return await MediaService.list_for_owner(db, owner_type, owner_id)


@router.get("/{media_id}")
@require_permission(Permission.DESIGN_VIEW)  # type: ignore[misc]
async def get_media_file(
    media_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Originaldatei eines Mediums ausliefern."""
    asset = await _viewable_asset(db, media_id, current_user)
    path = MediaService.original_path(asset)
    if path is None:
        logger.warning(
            "Media record exists but file is missing", extra={"media_id": media_id}
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_FILE_MISSING)
    return FileResponse(path=str(path), media_type=str(asset.mime), filename=path.name)


@router.get("/{media_id}/thumbnail")
@require_permission(Permission.DESIGN_VIEW)  # type: ignore[misc]
async def get_media_thumbnail(
    media_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Miniaturansicht ausliefern (Fallback: Original)."""
    asset = await _viewable_asset(db, media_id, current_user)
    path = MediaService.thumbnail_path(asset)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_FILE_MISSING)
    return FileResponse(
        path=str(path), media_type=mime_for_suffix(path.suffix), filename=path.name
    )
