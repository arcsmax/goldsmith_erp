# src/goldsmith_erp/services/media_service.py
"""
One service for every stored photo (ARCH phase 4, ADR-2026-09-25-media).

The three photo services (order, repair, consultation) delegate storage,
thumbnailing and the ``media_assets`` row to this module. During the
one-release deprecation window they still write their legacy row too
(``legacy_id`` links the two), so every existing endpoint, PDF, e-mail and
erasure path keeps working unchanged.

Upload pipeline (unchanged guarantees):
  1. ``read_validated_image``: size limit, magic-byte type check, decompression
     bomb reject (SEC-18).
  2. EXIF stripped, orientation applied, off the event loop and time-bounded
     (GDPR-19 / SEC-18) — fatal on failure, never stores raw bytes.
  3. ``MediaStore.put``: content-addressed write (sha256 of the processed
     bytes), per-owner namespace.
  4. Bounded 200px JPEG thumbnail in the ``thumbs/`` sibling (non-fatal).

Authorization (owner based, same rules the photo routers enforce): reading
any photo needs ``DESIGN_VIEW`` (design IP, SEC-09 / GDPR-04 — VIEWER is
refused) plus the owner's view permission; changing one needs the owner's
edit permission.
"""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, cast

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, has_permission
from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models import MediaAsset, MediaKind, MediaOwnerType, User
from goldsmith_erp.services import image_validation
from goldsmith_erp.services.image_validation import (
    PhotoValidationError,
    create_thumbnail_bounded,
    read_validated_image,
)
from goldsmith_erp.services.media_store import (
    EXT_TO_MIME,
    LocalMediaStore,
    MediaStoreError,
    get_media_store,
    sha256_hex,
    thumbnail_key_for,
)

logger = logging.getLogger(__name__)

# Owner type -> (view permission, edit permission). DESIGN_VIEW is required
# on top of the view permission for every read (photos are design IP).
OWNER_PERMISSIONS: dict[MediaOwnerType, tuple[Permission, Permission]] = {
    MediaOwnerType.ORDER: (Permission.ORDER_VIEW, Permission.ORDER_EDIT),
    MediaOwnerType.REPAIR: (Permission.REPAIR_VIEW, Permission.REPAIR_EDIT),
    MediaOwnerType.CONSULTATION: (
        Permission.CONSULTATION_VIEW,
        Permission.CONSULTATION_EDIT,
    ),
    MediaOwnerType.CUSTOMER_UPDATE: (Permission.ORDER_VIEW, Permission.ORDER_EDIT),
}


class MediaNotFoundError(LookupError):
    """No live media asset with that id."""


@dataclass(frozen=True)
class StoredMedia:
    """Result of writing one processed upload to the store."""

    key: str
    path: Path
    mime: str
    size: int
    sha256: str
    width: Optional[int]
    height: Optional[int]


def namespace_for(owner_type: MediaOwnerType, owner_id: int) -> str:
    """Owner directory inside the media root (legacy layout, kept)."""
    if owner_type is MediaOwnerType.ORDER:
        return str(owner_id)
    if owner_type is MediaOwnerType.REPAIR:
        return f"repairs/{owner_id}"
    if owner_type is MediaOwnerType.CONSULTATION:
        return f"consultations/{owner_id}"
    return f"customer-updates/{owner_id}"


async def _process_original(raw: bytes, ext: str) -> bytes:
    """EXIF-strip + re-encode off the loop, bounded (GDPR-19 / SEC-18)."""
    try:
        return await asyncio.wait_for(
            run_in_threadpool(image_validation.strip_exif_and_reencode, raw, ext),
            timeout=settings.IMAGE_PROCESSING_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        logger.warning(
            "Image processing (EXIF strip / re-encode) timed out",
            extra={"timeout_s": settings.IMAGE_PROCESSING_TIMEOUT_SECONDS},
        )
        raise PhotoValidationError(
            "Bildverarbeitung hat das Zeitlimit überschritten."
        ) from exc


def image_dimensions(data: bytes) -> tuple[Optional[int], Optional[int]]:
    """Header-only (width, height) of an image, or (None, None)."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            return int(probe.width), int(probe.height)
    except Exception:  # noqa: BLE001 - dimensions are informational only
        logger.warning("Could not read image dimensions", exc_info=True)
        return None, None


def unlink_with_thumbnail(original: Path, photo_id: object, label: str) -> None:
    """Best-effort unlink of a pre-media photo file and its thumbs/ sibling."""
    if original.exists():
        original.unlink()
        logger.info(f"{label} file deleted", extra={"photo_id": photo_id})
    else:
        logger.warning(
            f"{label} file not found on disk during deletion",
            extra={"photo_id": photo_id},
        )
    thumb_path = original.parent / "thumbs" / f"{original.stem}.jpg"
    if thumb_path.exists():
        thumb_path.unlink()


class MediaService:
    """Storage, lookup, authorization and lifecycle of media assets."""

    # ── storage ────────────────────────────────────────────────────────

    @staticmethod
    def store() -> LocalMediaStore:
        """The media store in use."""
        return get_media_store()

    @staticmethod
    async def store_upload(
        file: UploadFile, owner_type: MediaOwnerType, owner_id: int
    ) -> StoredMedia:
        """Validate, EXIF-strip and store an upload; thumbnail best effort.

        Raises:
            PhotoValidationError: invalid type/size/content or timeout.
        """
        raw, ext = await read_validated_image(file, settings.PHOTO_MAX_SIZE_MB)
        processed = await _process_original(raw, ext)
        store = MediaService.store()
        mime = EXT_TO_MIME[ext]
        key = store.put(processed, mime, namespace=namespace_for(owner_type, owner_id))
        path = store.path_for(key)
        width, height = image_dimensions(processed)
        thumb_path = store.path_for(thumbnail_key_for(key))
        if not thumb_path.exists():
            try:
                await create_thumbnail_bounded(path, thumb_path)
            except Exception:
                logger.warning(
                    "Thumbnail generation failed — photo still stored",
                    extra={"owner_type": owner_type.value, "owner_id": owner_id},
                    exc_info=True,
                )
        logger.info(
            "Media stored",
            extra={
                "owner_type": owner_type.value,
                "owner_id": owner_id,
                "size_bytes": len(processed),
            },
        )
        return StoredMedia(
            key=key,
            path=path,
            mime=mime,
            size=len(processed),
            sha256=sha256_hex(processed),
            width=width,
            height=height,
        )

    @staticmethod
    async def record_asset(
        db: AsyncSession,
        stored: StoredMedia,
        *,
        owner_type: MediaOwnerType,
        owner_id: int,
        user_id: Optional[int],
        caption: Optional[str] = None,
        tag: Optional[str] = None,
        legacy_id: Optional[str] = None,
        media_id: Optional[str] = None,
        taken_at: Optional[datetime] = None,
    ) -> MediaAsset:
        """Add the ``media_assets`` row for a stored upload (flush only)."""
        next_sort = await db.scalar(
            select(func.coalesce(func.max(MediaAsset.sort_order), -1) + 1).where(
                MediaAsset.owner_type == owner_type.value,
                MediaAsset.owner_id == owner_id,
            )
        )
        asset = MediaAsset(
            owner_type=owner_type.value,
            owner_id=owner_id,
            kind=MediaKind.PHOTO.value,
            storage_key=stored.key,
            mime=stored.mime,
            bytes=stored.size,
            width=stored.width,
            height=stored.height,
            sha256=stored.sha256,
            customer_visible=False,
            caption=caption,
            sort_order=int(next_sort or 0),
            taken_at=taken_at or utcnow(),
            uploaded_by=user_id,
            legacy_id=legacy_id,
            tag=tag,
        )
        if media_id is not None:
            asset.id = media_id  # type: ignore[assignment]
        db.add(asset)
        await db.flush()
        return asset

    # ── lookup ─────────────────────────────────────────────────────────

    @staticmethod
    async def get(db: AsyncSession, media_id: str) -> MediaAsset:
        """Live asset by id, or ``MediaNotFoundError``."""
        asset = await db.scalar(
            select(MediaAsset).where(
                MediaAsset.id == media_id, MediaAsset.deleted_at.is_(None)
            )
        )
        if asset is None:
            raise MediaNotFoundError(media_id)
        return asset

    @staticmethod
    async def get_by_legacy(
        db: AsyncSession, owner_type: MediaOwnerType, legacy_id: str
    ) -> Optional[MediaAsset]:
        """Live asset bridged to a legacy photo row, if any."""
        return cast(
            Optional[MediaAsset],
            await db.scalar(
                select(MediaAsset).where(
                    MediaAsset.owner_type == owner_type.value,
                    MediaAsset.legacy_id == str(legacy_id),
                    MediaAsset.deleted_at.is_(None),
                )
            ),
        )

    @staticmethod
    async def list_for_owner(
        db: AsyncSession,
        owner_type: MediaOwnerType,
        owner_id: int,
        *,
        customer_visible_only: bool = False,
    ) -> List[MediaAsset]:
        """Live assets of one owner, in display order."""
        stmt = select(MediaAsset).where(
            MediaAsset.owner_type == owner_type.value,
            MediaAsset.owner_id == owner_id,
            MediaAsset.deleted_at.is_(None),
        )
        if customer_visible_only:
            stmt = stmt.where(MediaAsset.customer_visible.is_(True))
        stmt = stmt.order_by(MediaAsset.sort_order, MediaAsset.created_at)
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def customer_visible_legacy_ids(
        db: AsyncSession, owner_type: MediaOwnerType, owner_id: int
    ) -> List[str]:
        """Legacy photo ids of the owner's customer-visible photos."""
        assets = await MediaService.list_for_owner(
            db, owner_type, owner_id, customer_visible_only=True
        )
        return [
            cast(str, asset.legacy_id)
            for asset in assets
            if asset.legacy_id and asset.kind == MediaKind.PHOTO.value
        ]

    # ── file access ────────────────────────────────────────────────────

    @staticmethod
    def original_path(asset: MediaAsset) -> Optional[Path]:
        """Existing original file of ``asset`` inside the root, else None."""
        store = MediaService.store()
        try:
            path = store.path_for(cast(str, asset.storage_key))
        except MediaStoreError:
            logger.error(
                "Media storage key escapes the media root — refused",
                extra={"media_id": asset.id},
            )
            return None
        return path if path.is_file() else None

    @staticmethod
    def thumbnail_path(asset: MediaAsset) -> Optional[Path]:
        """Existing thumbnail, falling back to the original, else None."""
        store = MediaService.store()
        try:
            thumb = store.path_for(thumbnail_key_for(cast(str, asset.storage_key)))
        except MediaStoreError:
            return None
        if thumb.is_file():
            return thumb
        return MediaService.original_path(asset)

    # ── authorization ──────────────────────────────────────────────────

    @staticmethod
    def can_view(user: User, asset: MediaAsset) -> bool:
        """DESIGN_VIEW plus the owner's view permission."""
        owner_type = MediaOwnerType(cast(str, asset.owner_type))
        view_perm, _ = OWNER_PERMISSIONS[owner_type]
        return has_permission(user, Permission.DESIGN_VIEW) and has_permission(
            user, view_perm
        )

    @staticmethod
    def can_edit(user: User, asset: MediaAsset) -> bool:
        """``can_view`` plus the owner's edit permission."""
        owner_type = MediaOwnerType(cast(str, asset.owner_type))
        _, edit_perm = OWNER_PERMISSIONS[owner_type]
        return MediaService.can_view(user, asset) and has_permission(user, edit_perm)

    # ── mutation ───────────────────────────────────────────────────────

    @staticmethod
    async def set_customer_visible(
        db: AsyncSession, asset: MediaAsset, visible: bool
    ) -> MediaAsset:
        """Toggle the ``customer_visible`` flag (flush only)."""
        asset.customer_visible = visible  # type: ignore[assignment]
        await db.flush()
        return asset

    @staticmethod
    async def delete(db: AsyncSession, asset: MediaAsset) -> None:
        """Soft-delete ``asset``; unlink its file when no live row shares it.

        Content addressing means two rows of one owner can share a key. The
        file (and its thumbnail) is removed only when this was the last live
        row referencing it. Missing files are logged, not fatal.
        """
        asset.deleted_at = utcnow()  # type: ignore[assignment]
        await db.flush()
        key = cast(str, asset.storage_key)
        still_used = await db.scalar(
            select(func.count())
            .select_from(MediaAsset)
            .where(MediaAsset.storage_key == key, MediaAsset.deleted_at.is_(None))
        )
        if still_used:
            return
        MediaService._unlink_quietly(key, cast(str, asset.id))
        MediaService._unlink_quietly(thumbnail_key_for(key), cast(str, asset.id))

    @staticmethod
    async def delete_for_legacy(
        db: AsyncSession, owner_type: MediaOwnerType, legacy_id: str
    ) -> bool:
        """Delete the asset bridged to a legacy row; False when none exists."""
        asset = await MediaService.get_by_legacy(db, owner_type, legacy_id)
        if asset is None:
            return False
        await MediaService.delete(db, asset)
        return True

    @staticmethod
    async def soft_delete_for_owners(
        db: AsyncSession, owner_type: MediaOwnerType, owner_ids: Sequence[int]
    ) -> List[MediaAsset]:
        """Soft-delete every live asset of the given owners (erasure use)."""
        if not owner_ids:
            return []
        assets = list(
            (
                await db.execute(
                    select(MediaAsset).where(
                        MediaAsset.owner_type == owner_type.value,
                        MediaAsset.owner_id.in_(list(owner_ids)),
                        MediaAsset.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        now = utcnow()
        for asset in assets:
            asset.deleted_at = now  # type: ignore[assignment]
        await db.flush()
        return assets

    @staticmethod
    def _unlink_quietly(key: str, media_id: str) -> None:
        store = MediaService.store()
        try:
            if not store.delete(key):
                logger.warning(
                    "Media file already missing on delete",
                    extra={"media_id": media_id},
                )
        except MediaStoreError:
            logger.error(
                "Media storage key escapes the media root — not deleted",
                extra={"media_id": media_id},
            )
