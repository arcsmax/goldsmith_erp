# src/goldsmith_erp/services/consultation_photo_service.py
"""
Photo upload service for consultation sketches and reference images.

Mirrors `photo_service.py`'s structure. File validation (JPEG / PNG / WEBP via
magic bytes, size checking, thumbnail generation) is delegated to the shared
`services/image_validation.py` module rather than re-implemented here.

Storage layout (content-addressed via MediaStore since ARCH phase 4; older
rows keep consultations/{consultation_id}/{uuid}.{ext}):
  {PHOTO_STORAGE_PATH}/consultations/{consultation_id}/{sha256[:2]}/{sha256}.{ext}
  {PHOTO_STORAGE_PATH}/consultations/{consultation_id}/{sha256[:2]}/thumbs/{sha256}.jpg

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
from datetime import datetime
from pathlib import Path
from typing import List, Optional, cast

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Consultation,
    ConsultationPhoto,
    ConsultationPhotoKind,
    MediaOwnerType,
)
from goldsmith_erp.services.image_validation import resolve_within_root
from goldsmith_erp.services.media_service import MediaService
from goldsmith_erp.services.media_service import (
    unlink_with_thumbnail as _unlink_with_thumbnail,
)

logger = logging.getLogger(__name__)


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _storage_root() -> Path:
    """Return the resolved photo storage root as a Path."""
    return Path(settings.PHOTO_STORAGE_PATH).resolve()


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

        # Storage, EXIF stripping (fatal on failure, GDPR-19), content
        # addressing and the thumbnail are MediaService's job (ARCH phase 4).
        stored = await MediaService.store_upload(
            file, MediaOwnerType.CONSULTATION, consultation_id
        )
        logger.info(
            "Consultation photo saved",
            extra={
                "consultation_id": consultation_id,
                "user_id": user_id,
                "kind": kind.value,
                "size_bytes": stored.size,
            },
        )

        # Legacy row (deprecated, dual-written for one release) plus the
        # media_assets row sharing its uuid.
        file_uuid = str(uuid.uuid4())
        photo = ConsultationPhoto(
            id=file_uuid,
            consultation_id=consultation_id,
            kind=kind,
            file_path=str(stored.path),
            taken_by=user_id,
            notes=notes,
        )
        db.add(photo)
        await db.flush()  # get the ID without committing — caller owns the transaction
        await MediaService.record_asset(
            db,
            stored,
            owner_type=MediaOwnerType.CONSULTATION,
            owner_id=consultation_id,
            user_id=user_id,
            caption=notes,
            tag=kind.value,
            legacy_id=file_uuid,
            media_id=file_uuid,
            taken_at=cast(Optional[datetime], photo.timestamp),
        )
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
            ValueError: If no photo with `photo_id` exists, or if the stored
                ``file_path`` does not resolve inside the photo storage root
                (defense-in-depth — consultation paths were never
                client-writable, but the guard is cheap and shared).
        """
        photo = await ConsultationPhotoService._get_or_raise(db, photo_id)
        original = ConsultationPhotoService._anchored_path_or_raise(photo)
        if thumbnail:
            # Derived from the already-anchored original — stays inside root.
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
            ValueError: If no photo with `photo_id` exists, or if the stored
                ``file_path`` does not resolve inside the photo storage root
                (the row is left untouched — nothing outside the root is
                ever unlinked).
        """
        photo = await ConsultationPhotoService._get_or_raise(db, photo_id)
        original = ConsultationPhotoService._anchored_path_or_raise(photo)

        # Media-backed rows: MediaService refcounts the shared file.
        if not await MediaService.delete_for_legacy(
            db, MediaOwnerType.CONSULTATION, photo_id
        ):
            _unlink_with_thumbnail(original, photo_id, "Consultation photo")

        await db.delete(photo)
        await db.flush()

    @staticmethod
    def _anchored_path_or_raise(photo: ConsultationPhoto) -> Path:
        """Resolve ``photo.file_path`` anchored to the storage root.

        Defense-in-depth twin of ``RepairPhotoService._anchored_path_or_raise``:
        consultation ``file_path`` values were never client-writable (the
        service has always written them itself), so no tainted data exists —
        but the guard is cheap, shared (``image_validation.resolve_within_root``),
        and protects against any future write path or DB tampering. Refused
        values raise an ID-only ValueError (→ 404 at the router; the raw path
        is logged server-side but never echoed to the client).
        """
        # cast(): mypy sees Column[str] at the class level; the ORM instance
        # attribute is a plain str at runtime. cast() is a no-op annotation.
        resolved = resolve_within_root(cast(str, photo.file_path), _storage_root())
        if resolved is None:
            logger.error(
                "Consultation photo path escapes storage root — refused",
                extra={
                    "photo_id": photo.id,
                    "raw_path": photo.file_path,
                    "storage_root": str(_storage_root()),
                },
            )
            raise ValueError(
                f"Consultation photo {photo.id} has an invalid storage path"
            )
        return resolved

    @staticmethod
    async def _get_or_raise(db: AsyncSession, photo_id: str) -> ConsultationPhoto:
        result = await db.execute(
            select(ConsultationPhoto).where(ConsultationPhoto.id == photo_id)
        )
        photo = result.scalar_one_or_none()
        if photo is None:
            raise ValueError(f"Consultation photo {photo_id} not found")
        return photo
