# src/goldsmith_erp/services/photo_service.py
"""
Photo upload service for order documentation.

Handles file validation (JPEG / PNG / WEBP via magic bytes), size checking,
filesystem storage, thumbnail generation (Pillow), and OrderPhoto DB records.

Storage layout:
  {PHOTO_STORAGE_PATH}/{order_id}/{uuid}.{ext}
  {PHOTO_STORAGE_PATH}/{order_id}/thumbs/{uuid}.jpg

Thumbnail width is fixed at THUMBNAIL_WIDTH px (height auto-scaled).

Security notes:
  - File type is determined by magic bytes, NOT the client-supplied Content-Type
    or filename extension, to prevent content-type spoofing.
  - File names are random UUIDs — no user input is used in filesystem paths.
  - Storage path is configured via settings (never derived from request data).
"""

import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import OrderPhoto

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

THUMBNAIL_WIDTH: int = 200
ALLOWED_MIME_TYPES: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpg",        # JPEG
    b"\x89PNG\r\n\x1a\n": "png",  # PNG
    b"RIFF": "webp",               # WEBP (checked separately — needs offset 8)
}
_MAX_MAGIC_BYTES: int = 12  # Enough to cover all signatures above


class PhotoValidationError(ValueError):
    """Raised when an uploaded photo fails validation (type or size)."""


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _detect_image_type(header: bytes) -> Optional[str]:
    """
    Detect image type from the first bytes of the file.

    Returns file extension ("jpg", "png", "webp") or None if unsupported.
    The caller must pass at least _MAX_MAGIC_BYTES bytes.
    """
    if header[:3] == b"\xff\xd8\xff":
        return "jpg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    # WEBP: 'RIFF' at offset 0 and 'WEBP' at offset 8
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


def _storage_root() -> Path:
    """Return the resolved photo storage root as a Path."""
    return Path(settings.PHOTO_STORAGE_PATH).resolve()


def _order_dir(order_id: int) -> Path:
    """Return the directory for a specific order's photos."""
    return _storage_root() / str(order_id)


def _thumb_dir(order_id: int) -> Path:
    """Return the thumbnail subdirectory for a specific order."""
    return _order_dir(order_id) / "thumbs"


def _create_thumbnail(source_path: Path, thumb_path: Path) -> None:
    """
    Create a thumbnail of `source_path` at `thumb_path`.

    The thumbnail is THUMBNAIL_WIDTH pixels wide; height is auto-scaled.
    Output is always saved as JPEG for consistency and small file size.
    """
    with Image.open(source_path) as img:
        # Convert RGBA/P images to RGB so they can be saved as JPEG.
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        w_orig, h_orig = img.size
        if w_orig == 0:
            raise PhotoValidationError("Image has zero width — corrupt file.")
        scale = THUMBNAIL_WIDTH / w_orig
        new_h = max(1, int(h_orig * scale))
        img_resized = img.resize((THUMBNAIL_WIDTH, new_h), Image.LANCZOS)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        img_resized.save(thumb_path, format="JPEG", quality=85, optimize=True)


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
        max_bytes = settings.PHOTO_MAX_SIZE_MB * 1024 * 1024

        # Read the whole file (bounded by max_bytes + 1 to detect overflow).
        raw = await file.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise PhotoValidationError(
                f"Datei zu groß. Maximum: {settings.PHOTO_MAX_SIZE_MB} MB."
            )

        # Magic-byte detection
        header = raw[:_MAX_MAGIC_BYTES]
        ext = _detect_image_type(header)
        if ext is None:
            raise PhotoValidationError(
                "Ungültiges Dateiformat. Erlaubt: JPEG, PNG, WEBP."
            )

        # Build storage paths
        file_uuid = str(uuid.uuid4())
        order_dir = _order_dir(order_id)
        order_dir.mkdir(parents=True, exist_ok=True)
        photo_path = order_dir / f"{file_uuid}.{ext}"
        thumb_path = _thumb_dir(order_id) / f"{file_uuid}.jpg"

        # Write original file
        photo_path.write_bytes(raw)
        logger.info(
            "Photo saved",
            extra={
                "order_id": order_id,
                "user_id": user_id,
                "path": str(photo_path),
                "size_bytes": len(raw),
            },
        )

        # Generate thumbnail (non-fatal — log warning if it fails)
        try:
            _create_thumbnail(photo_path, thumb_path)
        except Exception:
            logger.warning(
                "Thumbnail generation failed — photo still stored",
                extra={"photo_path": str(photo_path)},
                exc_info=True,
            )

        # Persist DB record
        photo = OrderPhoto(
            id=file_uuid,
            order_id=order_id,
            file_path=str(photo_path),
            taken_by=user_id,
            notes=notes,
            time_entry_id=time_entry_id,
        )
        db.add(photo)
        await db.flush()  # get the ID without committing — caller owns the transaction
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
        result = await db.execute(
            select(OrderPhoto).where(OrderPhoto.id == photo_id)
        )
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
        result = await db.execute(
            select(OrderPhoto).where(OrderPhoto.id == photo_id)
        )
        photo = result.scalar_one_or_none()
        if not photo:
            return False

        # Remove original file
        photo_path = Path(photo.file_path)
        if photo_path.exists():
            photo_path.unlink()
            logger.info(
                "Photo file deleted",
                extra={"photo_id": photo_id, "user_id": user_id},
            )
        else:
            logger.warning(
                "Photo file not found on disk during deletion",
                extra={"photo_id": photo_id, "path": str(photo_path)},
            )

        # Remove thumbnail (derive path from original location)
        thumb_path = get_thumbnail_path(photo)
        if thumb_path and thumb_path.exists():
            thumb_path.unlink()

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
