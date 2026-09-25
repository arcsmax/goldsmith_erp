"""Unit tests for RepairPhotoService.

Mirrors ``test_consultation_photo_service.py``'s coverage: upload + list
happy path, rejection of non-image uploads via the shared
PhotoValidationError, get_photo_path/delete_photo behavior, and the
"repair job must exist" guard. Unlike ConsultationPhoto, RepairPhoto.id is
a DB-assigned Integer — file names on disk are still uuid4-based.

The publish tests mock ``pubsub.publish_event`` the way
tests/unit/test_realtime_publish.py does (module attribute, not the
function) — see conftest.py's autouse ``mock_publish_event`` docstring for
why that's the only pattern a monkeypatch can actually intercept.
"""

import io
import json

import pytest
import pytest_asyncio
from fastapi import UploadFile
from PIL import Image

from goldsmith_erp.core import pubsub
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
    # Content-addressed layout (ARCH phase 4): <owner>/<sha[:2]>/thumbs/.
    assert list((tmp_path / "repairs" / str(repair.id)).glob("*/thumbs"))


@pytest.mark.asyncio
async def test_upload_publishes_reduced_repair_event_after_commit(
    db_session, tmp_path, monkeypatch, repair, sample_user
):
    """W7 hygiene follow-up: publish AFTER commit, ids/action/phase/timestamp only."""
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    published: list[tuple[str, str]] = []

    async def _record(channel: str, message: str) -> bool:
        published.append((channel, message))
        return True

    monkeypatch.setattr(pubsub, "publish_event", _record)

    photo = await RepairPhotoService.upload_photo(
        db_session,
        repair_id=repair.id,
        file=_jpeg_upload(),
        user_id=sample_user.id,
        phase=RepairPhotoPhase.INTAKE,
        notes="vertrauliche Notiz",
    )

    assert len(published) == 1
    channel, raw = published[0]
    assert channel == "repair_updates"
    payload = json.loads(raw)
    assert payload["action"] == "photo_added"
    assert payload["repair_id"] == repair.id
    assert payload["photo_id"] == photo.id
    assert payload["phase"] == RepairPhotoPhase.INTAKE.value
    assert payload["timestamp"]
    # Reduced payload only — never the image path or the notes.
    assert set(payload.keys()) == {
        "action",
        "repair_id",
        "photo_id",
        "phase",
        "timestamp",
    }
    assert "notes" not in raw
    assert "vertrauliche Notiz" not in raw


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


# ---------------------------------------------------------------------------
# Path anchoring — legacy client-supplied file_path values must never reach
# filesystem I/O (arbitrary file read/delete otherwise). The legacy JSON API
# accepted arbitrary strings into repair_photos.file_path; rows are crafted
# here via direct session insert to simulate surviving tainted data.
# ---------------------------------------------------------------------------


async def _insert_tainted_photo(db_session, repair, sample_user, file_path: str):
    """Insert a RepairPhoto row bypassing the service (legacy API simulation)."""
    from goldsmith_erp.db.models import RepairPhoto

    photo = RepairPhoto(
        repair_job_id=repair.id,
        phase=RepairPhotoPhase.INTAKE,
        file_path=file_path,
        taken_by=sample_user.id,
    )
    db_session.add(photo)
    await db_session.commit()
    await db_session.refresh(photo)
    return photo


@pytest.mark.parametrize(
    "hostile_path",
    ["/etc/passwd", "../../outside.txt"],
    ids=["absolute-escape", "relative-traversal"],
)
@pytest.mark.asyncio
async def test_get_photo_path_rejects_unanchored_path(
    db_session, tmp_path, monkeypatch, repair, sample_user, hostile_path
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    photo = await _insert_tainted_photo(db_session, repair, sample_user, hostile_path)

    with pytest.raises(ValueError) as excinfo:
        await RepairPhotoService.get_photo_path(db_session, photo.id)

    # ID-only message — the hostile path must never be echoed.
    assert str(photo.id) in str(excinfo.value)
    assert hostile_path not in str(excinfo.value)

    # Thumbnail resolution goes through the same guard.
    with pytest.raises(ValueError):
        await RepairPhotoService.get_photo_path(db_session, photo.id, thumbnail=True)


@pytest.mark.parametrize(
    "hostile_path",
    ["/etc/passwd", "../../outside.txt"],
    ids=["absolute-escape", "relative-traversal"],
)
@pytest.mark.asyncio
async def test_delete_photo_rejects_unanchored_path_and_keeps_row(
    db_session, tmp_path, monkeypatch, repair, sample_user, hostile_path
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    photo = await _insert_tainted_photo(db_session, repair, sample_user, hostile_path)

    with pytest.raises(ValueError) as excinfo:
        await RepairPhotoService.delete_photo(db_session, photo.id)
    assert hostile_path not in str(excinfo.value)

    # Row untouched — nothing outside the root was unlinked, nothing deleted.
    photos = await RepairPhotoService.list_photos(db_session, repair.id)
    assert [p.id for p in photos] == [photo.id]
    assert photos[0].file_path == hostile_path
