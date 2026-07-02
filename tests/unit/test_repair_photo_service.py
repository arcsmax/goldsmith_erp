"""Unit tests for RepairPhotoService.

Mirrors ``test_consultation_photo_service.py``'s coverage: upload + list
happy path, rejection of non-image uploads via the shared
PhotoValidationError, get_photo_path/delete_photo behavior, and the
"repair job must exist" guard. Unlike ConsultationPhoto, RepairPhoto.id is
a DB-assigned Integer — file names on disk are still uuid4-based.
"""

import io

import pytest
import pytest_asyncio
from fastapi import UploadFile
from PIL import Image

from goldsmith_erp.db.models import (
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    RepairPhotoPhase,
)
from goldsmith_erp.services.photo_service import PhotoValidationError
from goldsmith_erp.services.repair_photo_service import RepairPhotoService


def _jpeg_upload(name: str = "intake.jpg") -> UploadFile:
    """A minimal valid 4x4 white JPEG, Pillow-generated in-memory."""
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="JPEG")
    buf.seek(0)
    return UploadFile(filename=name, file=buf)


@pytest_asyncio.fixture
async def repair(db_session, sample_customer, sample_user) -> RepairJob:
    job = RepairJob(
        repair_number="REP-2026-0001",
        bag_number="BAG-0001",
        customer_id=sample_customer.id,
        received_by=sample_user.id,
        item_description="Ehering Gelbgold 585",
        item_type=RepairItemType.RING,
        status=RepairJobStatus.RECEIVED,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.mark.asyncio
async def test_upload_and_list(db_session, tmp_path, monkeypatch, repair, sample_user):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )

    photo = await RepairPhotoService.upload_photo(
        db_session,
        repair_id=repair.id,
        file=_jpeg_upload(),
        user_id=sample_user.id,
        phase=RepairPhotoPhase.INTAKE,
    )
    await db_session.flush()

    photos = await RepairPhotoService.list_photos(db_session, repair.id)
    assert len(photos) == 1
    assert photos[0].phase is RepairPhotoPhase.INTAKE
    assert photos[0].id == photo.id
    # id is a DB-assigned integer, NOT the uuid4 filename stem.
    assert isinstance(photo.id, int)
    assert (tmp_path / "repairs" / str(repair.id)).exists()
    assert (tmp_path / "repairs" / str(repair.id) / "thumbs").exists()


@pytest.mark.asyncio
async def test_upload_rejects_non_image(
    db_session, tmp_path, monkeypatch, repair, sample_user
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    bad = UploadFile(filename="x.pdf", file=io.BytesIO(b"%PDF-1.4 not an image"))

    with pytest.raises(PhotoValidationError):
        await RepairPhotoService.upload_photo(
            db_session,
            repair_id=repair.id,
            file=bad,
            user_id=sample_user.id,
            phase=RepairPhotoPhase.INTAKE,
        )

    # Nothing was persisted for the rejected upload.
    photos = await RepairPhotoService.list_photos(db_session, repair.id)
    assert photos == []


@pytest.mark.asyncio
async def test_upload_unknown_repair_raises(
    db_session, tmp_path, monkeypatch, sample_user
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )

    with pytest.raises(ValueError, match="99999"):
        await RepairPhotoService.upload_photo(
            db_session,
            repair_id=99999,
            file=_jpeg_upload(),
            user_id=sample_user.id,
            phase=RepairPhotoPhase.INTAKE,
        )


@pytest.mark.asyncio
async def test_get_photo_path_and_thumbnail(
    db_session, tmp_path, monkeypatch, repair, sample_user
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    photo = await RepairPhotoService.upload_photo(
        db_session,
        repair_id=repair.id,
        file=_jpeg_upload(),
        user_id=sample_user.id,
        phase=RepairPhotoPhase.INTAKE,
    )
    await db_session.flush()

    original_path = await RepairPhotoService.get_photo_path(db_session, photo.id)
    assert original_path.exists()
    assert original_path.suffix == ".jpg"

    thumb_path = await RepairPhotoService.get_photo_path(
        db_session, photo.id, thumbnail=True
    )
    assert thumb_path.exists()
    assert thumb_path.parent.name == "thumbs"


@pytest.mark.asyncio
async def test_get_photo_path_missing_raises(db_session):
    with pytest.raises(ValueError):
        await RepairPhotoService.get_photo_path(db_session, 999999)


@pytest.mark.asyncio
async def test_delete_photo_removes_file_thumb_and_row(
    db_session, tmp_path, monkeypatch, repair, sample_user
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    photo = await RepairPhotoService.upload_photo(
        db_session,
        repair_id=repair.id,
        file=_jpeg_upload(),
        user_id=sample_user.id,
        phase=RepairPhotoPhase.INTAKE,
    )
    await db_session.flush()

    original_path = await RepairPhotoService.get_photo_path(db_session, photo.id)
    thumb_path = await RepairPhotoService.get_photo_path(
        db_session, photo.id, thumbnail=True
    )
    assert original_path.exists()
    assert thumb_path.exists()

    await RepairPhotoService.delete_photo(db_session, photo.id)

    assert not original_path.exists()
    assert not thumb_path.exists()
    photos = await RepairPhotoService.list_photos(db_session, repair.id)
    assert photos == []


@pytest.mark.asyncio
async def test_delete_photo_missing_raises(db_session):
    with pytest.raises(ValueError):
        await RepairPhotoService.delete_photo(db_session, 999999)
