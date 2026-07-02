# src/goldsmith_erp/services/repair_photo_service.py
"""
Photo upload service for repair job documentation (Reparaturauftrag-Fotos).

Mirrors `consultation_photo_service.py`'s structure. File validation (JPEG /
PNG / WEBP via magic bytes, size checking, thumbnail generation) is delegated
to the shared `services/image_validation.py` module rather than
re-implemented here.

Storage layout:
  {PHOTO_STORAGE_PATH}/repairs/{repair_id}/{uuid}.{ext}
  {PHOTO_STORAGE_PATH}/repairs/{repair_id}/thumbs/{uuid}.jpg

Order photo dirs are integer-named (e.g. {PHOTO_STORAGE_PATH}/{order_id}/...),
so the literal "repairs" directory segment cannot collide with an order id.

Unlike ``ConsultationPhoto`` (whose primary key IS the uuid4 filename stem),
``RepairPhoto.id`` is a DB-assigned Integer (autoincrement) — the file name
on disk is still a uuid4, generated independently of the row's id, to keep
the "no user input in filesystem paths" security property from the shared
photo-upload pattern.

Security notes:
  - File type is determined by magic bytes, NOT the client-supplied Content-Type
    or filename extension, to prevent content-type spoofing.
  - File names are random UUIDs — no user input is used in filesystem paths.
  - Storage path is configured via settings (never derived from request data).
"""

import logging
import uuid
from pathlib import Path
from typing import Any, List, Optional, cast

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import RepairJob, RepairPhoto, RepairPhotoPhase
from goldsmith_erp.services.image_validation import (
    create_thumbnail,
    read_validated_image,
    resolve_within_root,
)

logger = logging.getLogger(__name__)


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _storage_root() -> Path:
    """Return the resolved photo storage root as a Path."""
    return Path(settings.PHOTO_STORAGE_PATH).resolve()


def _repair_dir(repair_id: int) -> Path:
    """Return the directory for a specific repair job's photos."""
    return _storage_root() / "repairs" / str(repair_id)


def _thumb_dir(repair_id: int) -> Path:
    """Return the thumbnail subdirectory for a specific repair job."""
    return _repair_dir(repair_id) / "thumbs"


# ─── Public service ──────────────────────────────────────────────────────────


class RepairPhotoService:
    """
    Service for uploading, listing, resolving paths for, and deleting
    repair job photos (intake / during-repair / completed documentation).

    All methods are async and accept an AsyncSession as first parameter
    (following the project service layer convention).
    """

    @staticmethod
    async def upload_photo(
        db: AsyncSession,
        repair_id: int,
        file: UploadFile,
        user_id: int,
        phase: RepairPhotoPhase,
        notes: Optional[str] = None,
    ) -> RepairPhoto:
        """
        Validate and store an uploaded photo for a repair job.

        Steps:
          1. Verify the repair job exists.
          2. Read + validate the file (size limit, magic-byte type check).
          3. Write to {PHOTO_STORAGE_PATH}/repairs/{repair_id}/{uuid}.{ext}.
          4. Generate 200px-wide JPEG thumbnail (non-fatal on failure).
          5. Create RepairPhoto DB record and flush (caller commits).

        Args:
            db:        Async database session.
            repair_id: ID of the repair job to attach the photo to.
            file:      FastAPI UploadFile from the multipart request.
            user_id:   ID of the user performing the upload.
            phase:     Photo phase (intake, during_repair, completed).
            notes:     Optional free-text notes for the photo.

        Returns:
            The newly created (unflushed, but flushed for the ID) RepairPhoto
            ORM instance.

        Raises:
            ValueError: If the repair job does not exist.
            PhotoValidationError: If file type is unsupported or size exceeds limit.
        """
        exists = await db.execute(
            select(RepairJob.id).filter(RepairJob.id == repair_id)
        )
        if exists.scalar_one_or_none() is None:
            raise ValueError(f"Reparaturauftrag #{repair_id} nicht gefunden")

        raw, ext = await read_validated_image(file, settings.PHOTO_MAX_SIZE_MB)

        # Build storage paths — filename is a fresh uuid4, independent of the
        # DB-assigned integer primary key (which isn't known until flush).
        file_uuid = str(uuid.uuid4())
        repair_dir = _repair_dir(repair_id)
        repair_dir.mkdir(parents=True, exist_ok=True)
        photo_path = repair_dir / f"{file_uuid}.{ext}"
        thumb_path = _thumb_dir(repair_id) / f"{file_uuid}.jpg"

        # Write original file
        photo_path.write_bytes(raw)
        logger.info(
            "Repair photo saved",
            extra={
                "repair_id": repair_id,
                "user_id": user_id,
                "phase": phase.value,
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

        # Persist DB record — id is DB-assigned (autoincrement), unlike
        # ConsultationPhoto's uuid4-as-pk.
        photo = RepairPhoto(
            repair_job_id=repair_id,
            phase=phase,
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
        repair_id: int,
    ) -> List[RepairPhoto]:
        """
        Return all photos for a repair job, sorted by timestamp ascending.

        Args:
            db:        Async database session.
            repair_id: ID of the repair job.

        Returns:
            List of RepairPhoto ORM instances (may be empty).
        """
        result = await db.execute(
            select(RepairPhoto)
            .where(RepairPhoto.repair_job_id == repair_id)
            .order_by(RepairPhoto.timestamp)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_photo_path(
        db: AsyncSession,
        photo_id: int,
        thumbnail: bool = False,
    ) -> Path:
        """
        Resolve the filesystem path of a repair photo.

        Args:
            db:        Async database session.
            photo_id:  Integer ID of the photo.
            thumbnail: If True, return the thumbnail path instead of the original.

        Returns:
            Path to the original file, or its thumbnail if `thumbnail=True`.

        Raises:
            ValueError: If no photo with `photo_id` exists, or if the stored
                ``file_path`` does not resolve inside the photo storage root
                (legacy client-supplied strings / tampered rows). The error
                message is ID-only — the raw path is never echoed.
        """
        photo = await RepairPhotoService._get_or_raise(db, photo_id)
        original = RepairPhotoService._anchored_path_or_raise(photo)
        if thumbnail:
            # Derived from the already-anchored original, so the thumb
            # path is guaranteed to stay inside the storage root too.
            return original.parent / "thumbs" / f"{original.stem}.jpg"
        return original

    @staticmethod
    async def delete_photo(db: AsyncSession, photo_id: int) -> None:
        """
        Delete a repair photo file, its thumbnail, and the DB record.

        The filesystem deletion is best-effort — a missing file is logged
        but does not prevent the DB record from being removed.

        Any intake-checklist item on the parent repair that links this
        photo (``status="photo"``, ``photo_id`` = this id) is downgraded
        back to ``status="open"`` in the SAME transaction — otherwise the
        checklist would keep asserting photo-documented condition while
        the photo 404s, undermining its dispute-protection purpose.

        Args:
            db:       Async database session.
            photo_id: Integer ID of the photo.

        Raises:
            ValueError: If no photo with `photo_id` exists, or if the stored
                ``file_path`` does not resolve inside the photo storage root
                (the row is left untouched — nothing outside the root is
                ever unlinked).
        """
        photo = await RepairPhotoService._get_or_raise(db, photo_id)
        original = RepairPhotoService._anchored_path_or_raise(photo)
        repair_job_id = photo.repair_job_id

        if original.exists():
            original.unlink()
            logger.info(
                "Repair photo file deleted",
                extra={"photo_id": photo_id},
            )
        else:
            logger.warning(
                "Repair photo file not found on disk during deletion",
                extra={"photo_id": photo_id, "path": str(original)},
            )

        thumb_path = original.parent / "thumbs" / f"{original.stem}.jpg"
        if thumb_path.exists():
            thumb_path.unlink()

        await db.delete(photo)
        await RepairPhotoService._downgrade_checklist_items(
            db, int(repair_job_id), photo_id
        )
        await db.flush()

    @staticmethod
    async def _downgrade_checklist_items(
        db: AsyncSession, repair_job_id: int, photo_id: int
    ) -> None:
        """Reset checklist items linking ``photo_id`` back to ``open``.

        Called from :meth:`delete_photo` inside the same session/transaction
        (caller commits) so the photo row deletion and the checklist
        downgrade land atomically. No-op when the repair has no checklist
        or no item links the deleted photo.
        """
        result = await db.execute(
            select(RepairJob).where(RepairJob.id == repair_job_id)
        )
        repair = result.scalar_one_or_none()
        if repair is None or not repair.intake_checklist:
            return

        # cast(): mypy sees Column[Any] at class level for the JSON column;
        # on a mapped instance it holds the runtime list (Task 1 review-nit
        # pattern).
        current_items = cast(List[Any], repair.intake_checklist)

        downgraded = 0
        new_items = []
        for item in current_items:
            if isinstance(item, dict) and item.get("photo_id") == photo_id:
                new_items.append({**item, "status": "open", "photo_id": None})
                downgraded += 1
            else:
                new_items.append(item)

        if downgraded:
            # Whole-value reassignment — SQLAlchemy's JSON column
            # change-tracking compares by reference, so an in-place edit
            # of the existing list would not be persisted.
            repair.intake_checklist = cast(Any, new_items)
            logger.info(
                "Intake checklist item(s) downgraded to open after photo deletion",
                extra={
                    "repair_id": repair_job_id,
                    "photo_id": photo_id,
                    "downgraded_items": downgraded,
                },
            )

    @staticmethod
    def _anchored_path_or_raise(photo: RepairPhoto) -> Path:
        """Resolve ``photo.file_path`` anchored to the storage root.

        The legacy repair-photo API accepted arbitrary client strings into
        ``repair_photos.file_path`` — a stored value is NOT trustworthy.
        Any value that does not resolve inside ``PHOTO_STORAGE_PATH`` is
        refused with an ID-only ValueError (→ 404 at the router; the raw
        path is logged server-side but never echoed to the client).
        """
        resolved = resolve_within_root(photo.file_path, _storage_root())
        if resolved is None:
            logger.error(
                "Repair photo path escapes storage root — refused",
                extra={
                    "photo_id": photo.id,
                    "raw_path": photo.file_path,
                    "storage_root": str(_storage_root()),
                },
            )
            raise ValueError(
                f"Reparatur-Foto #{photo.id} hat einen ungueltigen Speicherpfad"
            )
        return resolved

    @staticmethod
    async def _get_or_raise(db: AsyncSession, photo_id: int) -> RepairPhoto:
        result = await db.execute(select(RepairPhoto).where(RepairPhoto.id == photo_id))
        photo = result.scalar_one_or_none()
        if photo is None:
            raise ValueError(f"Reparatur-Foto #{photo_id} nicht gefunden")
        return photo
