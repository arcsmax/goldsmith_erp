# src/goldsmith_erp/services/consultation_photo_service.py
"""
Photo upload service for consultation sketches and reference images.

Mirrors `photo_service.py`'s structure. File validation (JPEG / PNG / WEBP via
magic bytes, size checking, thumbnail generation) is delegated to the shared
`services/image_validation.py` module rather than re-implemented here.

Storage layout:
  {PHOTO_STORAGE_PATH}/consultations/{consultation_id}/{uuid}.{ext}
  {PHOTO_STORAGE_PATH}/consultations/{consultation_id}/thumbs/{uuid}.jpg

Order photo dirs are integer-named (e.g. {PHOTO_STORAGE_PATH}/{order_id}/...),
so the literal "consultations" directory segment cannot collide with an order id.

Security notes:
  - File type is determined by magic bytes, NOT the client-supplied Content-Type
    or filename extension, to prevent content-type spoofing.
  - File names are random UUIDs — no user input is used in filesystem paths.
  - Storage path is configured via settings (never derived from request data).
"""

import logging
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Consultation,
    ConsultationPhoto,
    ConsultationPhotoKind,
)
from goldsmith_erp.services.image_validation import (
    create_thumbnail,
    read_validated_image,
)

logger = logging.getLogger(__name__)


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _storage_root() -> Path:
    """Return the resolved photo storage root as a Path."""
    return Path(settings.PHOTO_STORAGE_PATH).resolve()


def _consultation_dir(consultation_id: int) -> Path:
    """Return the directory for a specific consultation's photos."""
    return _storage_root() / "consultations" / str(consultation_id)


def _thumb_dir(consultation_id: int) -> Path:
    """Return the thumbnail subdirectory for a specific consultation."""
    return _consultation_dir(consultation_id) / "thumbs"


# ─── Public service ──────────────────────────────────────────────────────────


class ConsultationPhotoService:
    """
    Service for uploading, listing, resolving paths for, and deleting
    consultation photos (sketches, references, inspiration images).

    All methods are async and accept an AsyncSession as first parameter
    (following the project service layer convention).
    """

    @staticmethod
    async def upload_photo(
        db: AsyncSession,
        consultation_id: int,
        file: UploadFile,
        user_id: int,
        kind: ConsultationPhotoKind,
        notes: Optional[str] = None,
    ) -> ConsultationPhoto:
        """
        Validate and store an uploaded photo for a consultation.

        Steps:
          1. Verify the consultation exists.
          2. Read + validate the file (size limit, magic-byte type check).
          3. Write to {PHOTO_STORAGE_PATH}/consultations/{consultation_id}/{uuid}.{ext}.
          4. Generate 200px-wide JPEG thumbnail (non-fatal on failure).
          5. Create ConsultationPhoto DB record and flush (caller commits).

        Args:
            db:              Async database session.
            consultation_id: ID of the consultation to attach the photo to.
            file:            FastAPI UploadFile from the multipart request.
            user_id:         ID of the user performing the upload.
            kind:            Photo kind (sketch, reference, inspiration, ...).
            notes:           Optional free-text notes for the photo.

        Returns:
            The newly created (unflushed) ConsultationPhoto ORM instance.

        Raises:
            ValueError: If the consultation does not exist.
            PhotoValidationError: If file type is unsupported or size exceeds limit.
        """
        exists = await db.execute(
            select(Consultation.id).filter(Consultation.id == consultation_id)
        )
        if exists.scalar_one_or_none() is None:
            raise ValueError(f"Consultation {consultation_id} not found")

        raw, ext = await read_validated_image(file, settings.PHOTO_MAX_SIZE_MB)

        # Build storage paths
        file_uuid = str(uuid.uuid4())
        consultation_dir = _consultation_dir(consultation_id)
        consultation_dir.mkdir(parents=True, exist_ok=True)
        photo_path = consultation_dir / f"{file_uuid}.{ext}"
        thumb_path = _thumb_dir(consultation_id) / f"{file_uuid}.jpg"

        # Write original file
        photo_path.write_bytes(raw)
        logger.info(
            "Consultation photo saved",
            extra={
                "consultation_id": consultation_id,
                "user_id": user_id,
                "kind": kind.value,
                "path": str(photo_path),
                "size_bytes": len(raw),
            },
        )

        # Generate thumbnail (non-fatal — log warning if it fails)
        try:
            create_thumbnail(photo_path, thumb_path)
        except Exception:
            logger.warning(
                "Thumbnail generation failed — photo still stored",
                extra={"photo_path": str(photo_path)},
                exc_info=True,
            )

        # Persist DB record
        photo = ConsultationPhoto(
            id=file_uuid,
            consultation_id=consultation_id,
            kind=kind,
            file_path=str(photo_path),
            taken_by=user_id,
            notes=notes,
        )
        db.add(photo)
        await db.flush()  # get the ID without committing — caller owns the transaction
        return photo

    @staticmethod
    async def list_photos(
        db: AsyncSession,
        consultation_id: int,
    ) -> List[ConsultationPhoto]:
        """
        Return all photos for a consultation, sorted by timestamp ascending.

        Args:
            db:              Async database session.
            consultation_id: ID of the consultation.

        Returns:
            List of ConsultationPhoto ORM instances (may be empty).
        """
        result = await db.execute(
            select(ConsultationPhoto)
            .where(ConsultationPhoto.consultation_id == consultation_id)
            .order_by(ConsultationPhoto.timestamp)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_photo_path(
        db: AsyncSession,
        photo_id: str,
        thumbnail: bool = False,
    ) -> Path:
        """
        Resolve the filesystem path of a consultation photo.

        Args:
            db:        Async database session.
            photo_id:  UUID string of the photo.
            thumbnail: If True, return the thumbnail path instead of the original.

        Returns:
            Path to the original file, or its thumbnail if `thumbnail=True`.

        Raises:
            ValueError: If no photo with `photo_id` exists.
        """
        photo = await ConsultationPhotoService._get_or_raise(db, photo_id)
        original = Path(photo.file_path)
        if thumbnail:
            return original.parent / "thumbs" / f"{original.stem}.jpg"
        return original

    @staticmethod
    async def delete_photo(db: AsyncSession, photo_id: str) -> None:
        """
        Delete a consultation photo file, its thumbnail, and the DB record.

        The filesystem deletion is best-effort — a missing file is logged
        but does not prevent the DB record from being removed.

        Args:
            db:       Async database session.
            photo_id: UUID string of the photo.

        Raises:
            ValueError: If no photo with `photo_id` exists.
        """
        photo = await ConsultationPhotoService._get_or_raise(db, photo_id)

        original = Path(photo.file_path)
        if original.exists():
            original.unlink()
            logger.info(
                "Consultation photo file deleted",
                extra={"photo_id": photo_id},
            )
        else:
            logger.warning(
                "Consultation photo file not found on disk during deletion",
                extra={"photo_id": photo_id, "path": str(original)},
            )

        thumb_path = original.parent / "thumbs" / f"{original.stem}.jpg"
        if thumb_path.exists():
            thumb_path.unlink()

        await db.delete(photo)
        await db.flush()

    @staticmethod
    async def _get_or_raise(db: AsyncSession, photo_id: str) -> ConsultationPhoto:
        result = await db.execute(
            select(ConsultationPhoto).where(ConsultationPhoto.id == photo_id)
        )
        photo = result.scalar_one_or_none()
        if photo is None:
            raise ValueError(f"Consultation photo {photo_id} not found")
        return photo
