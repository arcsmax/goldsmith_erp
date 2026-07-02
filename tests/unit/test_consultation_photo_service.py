"""Unit tests for ConsultationPhotoService.

Mirrors the (currently non-existent) photo_service test coverage: upload +
list happy path, and rejection of non-image uploads via the shared
PhotoValidationError. Also covers get_photo_path/delete_photo behavior and
the "consultation must exist" guard.
"""

import io

import pytest
import pytest_asyncio
from fastapi import UploadFile
from PIL import Image

from goldsmith_erp.db.models import Consultation, ConsultationPhotoKind
from goldsmith_erp.models.consultation import ConsultationCreate
from goldsmith_erp.services.consultation_photo_service import ConsultationPhotoService
from goldsmith_erp.services.consultation_service import ConsultationService
from goldsmith_erp.services.photo_service import PhotoValidationError


def _jpeg_upload(name: str = "sketch.jpg") -> UploadFile:
    """A minimal valid 4x4 white JPEG, Pillow-generated in-memory."""
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="JPEG")
    buf.seek(0)
    return UploadFile(filename=name, file=buf)


@pytest_asyncio.fixture
async def consultation(db_session, sample_customer, sample_user) -> Consultation:
    return await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id, wishes="Anhänger"),
        conducted_by_user_id=sample_user.id,
    )


@pytest.mark.asyncio
async def test_upload_and_list(
    db_session, tmp_path, monkeypatch, consultation, sample_user
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )

    photo = await ConsultationPhotoService.upload_photo(
        db_session,
        consultation_id=consultation.id,
        file=_jpeg_upload(),
        user_id=sample_user.id,
        kind=ConsultationPhotoKind.SKETCH,
    )
    await db_session.flush()

    photos = await ConsultationPhotoService.list_photos(db_session, consultation.id)
    assert len(photos) == 1
    assert photos[0].kind is ConsultationPhotoKind.SKETCH
    assert photos[0].id == photo.id
    assert (tmp_path / "consultations" / str(consultation.id)).exists()
    assert (tmp_path / "consultations" / str(consultation.id) / "thumbs").exists()


@pytest.mark.asyncio
async def test_upload_rejects_non_image(
    db_session, tmp_path, monkeypatch, consultation, sample_user
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    bad = UploadFile(filename="x.pdf", file=io.BytesIO(b"%PDF-1.4 not an image"))

    with pytest.raises(PhotoValidationError):
        await ConsultationPhotoService.upload_photo(
            db_session,
            consultation_id=consultation.id,
            file=bad,
            user_id=sample_user.id,
            kind=ConsultationPhotoKind.REFERENCE,
        )

    # Nothing was persisted for the rejected upload.
    photos = await ConsultationPhotoService.list_photos(db_session, consultation.id)
    assert photos == []


@pytest.mark.asyncio
async def test_upload_unknown_consultation_raises(
    db_session, tmp_path, monkeypatch, sample_user
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )

    with pytest.raises(ValueError, match="Consultation 99999 not found"):
        await ConsultationPhotoService.upload_photo(
            db_session,
            consultation_id=99999,
            file=_jpeg_upload(),
            user_id=sample_user.id,
            kind=ConsultationPhotoKind.SKETCH,
        )


@pytest.mark.asyncio
async def test_get_photo_path_and_thumbnail(
    db_session, tmp_path, monkeypatch, consultation, sample_user
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    photo = await ConsultationPhotoService.upload_photo(
        db_session,
        consultation_id=consultation.id,
        file=_jpeg_upload(),
        user_id=sample_user.id,
        kind=ConsultationPhotoKind.SKETCH,
    )
    await db_session.flush()

    original_path = await ConsultationPhotoService.get_photo_path(db_session, photo.id)
    assert original_path.exists()
    assert original_path.suffix == ".jpg"

    thumb_path = await ConsultationPhotoService.get_photo_path(
        db_session, photo.id, thumbnail=True
    )
    assert thumb_path.exists()
    assert thumb_path.parent.name == "thumbs"


@pytest.mark.asyncio
async def test_get_photo_path_missing_raises(db_session):
    with pytest.raises(ValueError):
        await ConsultationPhotoService.get_photo_path(db_session, "does-not-exist")


@pytest.mark.asyncio
async def test_delete_photo_removes_file_thumb_and_row(
    db_session, tmp_path, monkeypatch, consultation, sample_user
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    photo = await ConsultationPhotoService.upload_photo(
        db_session,
        consultation_id=consultation.id,
        file=_jpeg_upload(),
        user_id=sample_user.id,
        kind=ConsultationPhotoKind.SKETCH,
    )
    await db_session.flush()

    original_path = await ConsultationPhotoService.get_photo_path(db_session, photo.id)
    thumb_path = await ConsultationPhotoService.get_photo_path(
        db_session, photo.id, thumbnail=True
    )
    assert original_path.exists()
    assert thumb_path.exists()

    await ConsultationPhotoService.delete_photo(db_session, photo.id)

    assert not original_path.exists()
    assert not thumb_path.exists()
    photos = await ConsultationPhotoService.list_photos(db_session, consultation.id)
    assert photos == []


@pytest.mark.asyncio
async def test_delete_photo_missing_raises(db_session):
    with pytest.raises(ValueError):
        await ConsultationPhotoService.delete_photo(db_session, "does-not-exist")
