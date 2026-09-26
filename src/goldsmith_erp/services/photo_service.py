# src/goldsmith_erp/services/photo_service.py
"""
Photo upload service for order documentation.

Handles file validation (JPEG / PNG / WEBP via magic bytes), size checking,
filesystem storage, thumbnail generation (Pillow), and OrderPhoto DB records.

Storage layout (content-addressed via MediaStore since ARCH phase 4; rows
written before that keep the old {order_id}/{uuid}.{ext} paths):
  {PHOTO_STORAGE_PATH}/{order_id}/{sha256[:2]}/{sha256}.{ext}
  {PHOTO_STORAGE_PATH}/{order_id}/{sha256[:2]}/thumbs/{sha256}.jpg

Thumbnail width is fixed at THUMBNAIL_WIDTH px (height auto-scaled).

Security notes:
  - File type is determined by magic bytes, NOT the client-supplied Content-Type
    or filename extension, to prevent content-type spoofing.
  - File names are random UUIDs — no user input is used in filesystem paths.
  - Storage path is configured via settings (never derived from request data).
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, cast

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import MediaOwnerType, OrderPhoto
from goldsmith_erp.services.image_validation import (  # noqa: F401 (re-exports)
    _MAX_MAGIC_BYTES,
    THUMBNAIL_WIDTH,
    PhotoValidationError,
    create_thumbnail_bounded,
)
from goldsmith_erp.services.image_validation import (
    detect_image_type as _detect_image_type,
)
from goldsmith_erp.services.image_validation import (  # noqa: F401 (re-exports)
    read_validated_image,
    store_processed_original,
)
from goldsmith_erp.services.media_service import MediaService, unlink_with_thumbnail

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Kept for backward compatibility — not referenced internally (type detection
# is delegated to image_validation.detect_image_type), but part of this
# module's public surface.
ALLOWED_MIME_TYPES: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpg",  # JPEG
    b"\x89PNG\r\n\x1a\n": "png",  # PNG
    b"RIFF": "webp",  # WEBP (checked separately — needs offset 8)
}


# ─── Internal helpers ─────────────────────────────────────────────────────────
#
# _detect_image_type, _MAX_MAGIC_BYTES, and PhotoValidationError now live in
# services/image_validation.py (shared with consultation_photo_service) and
# are re-exported above so existing imports of this module keep working.
# Original storage and thumbnailing go through store_processed_original() /
# create_thumbnail_bounded() (also image_validation.py) — both time-bounded
# and run off the event loop (SEC-18), and the former strips EXIF metadata
# from every stored original before it ever touches disk (GDPR-19).


def _storage_root() -> Path:
    """Return the resolved photo storage root as a Path."""
    return Path(settings.PHOTO_STORAGE_PATH).resolve()


# ─── Public service ──────────────────────────────────────────────────────────


class PhotoService:
    """
    Service for uploading, listing, serving, and deleting order photos.

    All methods are async and accept an AsyncSession as first parameter
    (following the project service layer convention).
    """

    @staticmethod
    async def upload_photo(
        db: AsyncSession,
        order_id: int,
        file: UploadFile,
        user_id: int,
        notes: Optional[str] = None,
        time_entry_id: Optional[str] = None,
    ) -> OrderPhoto:
        """
        Validate and store an uploaded photo for an order.

        Steps:
          1. Read up to MAX_SIZE bytes (+ 1 to detect oversized uploads).
          2. Validate image type via magic bytes (reject if unsupported).
          3. Write to {PHOTO_STORAGE_PATH}/{order_id}/{uuid}.{ext}.
          4. Generate 200px-wide JPEG thumbnail.
          5. Create OrderPhoto DB record and flush (caller commits).

        Args:
            db:            Async database session.
            order_id:      ID of the order to attach the photo to.
            file:          FastAPI UploadFile from the multipart request.
            user_id:       ID of the user performing the upload.
            notes:         Optional free-text notes for the photo.
            time_entry_id: Optional UUID of an associated time entry.

        Returns:
            The newly created (unflushed) OrderPhoto ORM instance.

        Raises:
            PhotoValidationError: If file type is unsupported or size exceeds limit.
        """
        # Storage, EXIF stripping, content addressing and the thumbnail are
        # MediaService's job (ARCH phase 4). A failure there is FATAL: the
        # raw, unprocessed bytes are never stored (GDPR-19).
        stored = await MediaService.store_upload(file, MediaOwnerType.ORDER, order_id)
        logger.info(
            "Photo saved",
            extra={
                "order_id": order_id,
                "user_id": user_id,
                "size_bytes": stored.size,
            },
        )

        # Legacy row (deprecated, dual-written for one release) plus the
        # media_assets row sharing its uuid.
        file_uuid = str(uuid.uuid4())
        photo = OrderPhoto(
            id=file_uuid,
            order_id=order_id,
            file_path=str(stored.path),
            taken_by=user_id,
            notes=notes,
            time_entry_id=time_entry_id,
        )
        db.add(photo)
        await db.flush()  # get the ID without committing — caller owns the transaction
        await MediaService.record_asset(
            db,
            stored,
            owner_type=MediaOwnerType.ORDER,
            owner_id=order_id,
            user_id=user_id,
            caption=notes,
            legacy_id=file_uuid,
            media_id=file_uuid,
            taken_at=cast(Optional[datetime], photo.timestamp),
        )
        return photo

    @staticmethod
    async def get_photos(
        db: AsyncSession,
        order_id: int,
    ) -> list[OrderPhoto]:
        """
        Return all photos for an order, sorted by timestamp ascending.

        Args:
            db:       Async database session.
            order_id: ID of the order.

        Returns:
            List of OrderPhoto ORM instances (may be empty).
        """
        result = await db.execute(
            select(OrderPhoto)
            .where(OrderPhoto.order_id == order_id)
            .order_by(OrderPhoto.timestamp)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_photo(
        db: AsyncSession,
        photo_id: str,
    ) -> Optional[OrderPhoto]:
        """
        Return a single OrderPhoto by its UUID primary key.

        Args:
            db:       Async database session.
            photo_id: UUID string of the photo.

        Returns:
            OrderPhoto instance or None if not found.
        """
        result = await db.execute(select(OrderPhoto).where(OrderPhoto.id == photo_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_photo(
        db: AsyncSession,
        photo_id: str,
        user_id: int,
    ) -> bool:
        """
        Delete a photo file, its thumbnail, and the DB record.

        The filesystem deletion is best-effort — missing files are logged
        but do not prevent the DB record from being removed.

        Args:
            db:       Async database session.
            photo_id: UUID string of the photo.
            user_id:  ID of the requesting user (for audit logging).

        Returns:
            True if the record was found and deleted, False if not found.
        """
        result = await db.execute(select(OrderPhoto).where(OrderPhoto.id == photo_id))
        photo = result.scalar_one_or_none()
        if not photo:
            return False

        # Files of a media-backed photo are refcounted by MediaService (two
        # rows can share one content-addressed file); pre-media rows keep the
        # old direct unlink.
        if await MediaService.delete_for_legacy(db, MediaOwnerType.ORDER, photo_id):
            logger.info(
                "Photo deleted", extra={"photo_id": photo_id, "user_id": user_id}
            )
        else:
            unlink_with_thumbnail(Path(cast(str, photo.file_path)), photo_id, "Photo")

        await db.delete(photo)
        await db.flush()
        return True

    @staticmethod
    async def get_photo_by_order(
        db: AsyncSession,
        photo_id: str,
        order_id: int,
    ) -> Optional[OrderPhoto]:
        """
        Return a photo only if it belongs to the specified order.

        Used by endpoints to prevent cross-order access.
        """
        result = await db.execute(
            select(OrderPhoto).where(
                OrderPhoto.id == photo_id,
                OrderPhoto.order_id == order_id,
            )
        )
        return result.scalar_one_or_none()


# ─── Path resolution helpers ─────────────────────────────────────────────────


def get_photo_path(photo: OrderPhoto) -> Optional[Path]:
    """
    Resolve the filesystem path of a photo's original file.

    Returns a Path if the stored file_path is set, otherwise None.
    """
    if not photo.file_path:
        return None
    return Path(photo.file_path)


def get_thumbnail_path(photo: OrderPhoto) -> Optional[Path]:
    """
    Derive the filesystem path of a photo's thumbnail from its original path.

    Thumbnails are stored in a 'thumbs/' subdirectory alongside the original,
    with a forced .jpg extension.
    """
    if not photo.file_path:
        return None
    original = Path(photo.file_path)
    return original.parent / "thumbs" / f"{original.stem}.jpg"
