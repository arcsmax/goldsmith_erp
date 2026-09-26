"""Unit tests for services/media_service.py (ARCH phase 4)."""

from __future__ import annotations

import hashlib
import io
import uuid

import pytest
from fastapi import UploadFile
from PIL import Image
from sqlalchemy import select

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    MediaAsset,
    MediaOwnerType,
    OrderPhoto,
    User,
    UserRole,
)
from goldsmith_erp.services.image_validation import PhotoValidationError
from goldsmith_erp.services.media_service import MediaService, namespace_for
from goldsmith_erp.services.photo_service import PhotoService


def _jpeg_with_gps(width: int = 16, height: int = 24) -> bytes:
    img = Image.new("RGB", (width, height), "red")
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (52.0, 31.0, 12.0)}  # GPSInfo
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _upload(data: bytes, name: str = "p.jpg") -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data))


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    return tmp_path.resolve()


def _user(role: UserRole) -> User:
    return User(
        id=1,
        email=f"{role.value}@example.com",
        hashed_password=get_password_hash("x" * 12),
        role=role,
        is_active=True,
    )


def _asset(owner_type: MediaOwnerType) -> MediaAsset:
    return MediaAsset(
        id=str(uuid.uuid4()),
        owner_type=owner_type.value,
        owner_id=1,
        kind="photo",
        storage_key="1/ab/x.jpg",
        mime="image/jpeg",
    )


# ── storage ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_upload_strips_exif_hashes_and_thumbnails(media_root):
    stored = await MediaService.store_upload(
        _upload(_jpeg_with_gps()), MediaOwnerType.ORDER, 42
    )

    data = stored.path.read_bytes()
    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    assert stored.key == f"42/{stored.sha256[:2]}/{stored.sha256}.jpg"
    assert stored.path == media_root / stored.key
    assert (stored.width, stored.height) == (16, 24)
    assert stored.size == len(data) and stored.mime == "image/jpeg"
    with Image.open(stored.path) as img:
        assert 0x8825 not in img.getexif()  # GPS gone (GDPR-19)
    thumb = stored.path.parent / "thumbs" / f"{stored.sha256}.jpg"
    with Image.open(thumb) as img:
        assert img.width == 200


@pytest.mark.asyncio
async def test_store_upload_rejects_non_images(media_root):
    with pytest.raises(PhotoValidationError):
        await MediaService.store_upload(
            _upload(b"not an image at all"), MediaOwnerType.ORDER, 1
        )
    assert not list(media_root.rglob("*.*"))


def test_namespaces_match_the_legacy_owner_directories():
    assert namespace_for(MediaOwnerType.ORDER, 5) == "5"
    assert namespace_for(MediaOwnerType.REPAIR, 5) == "repairs/5"
    assert namespace_for(MediaOwnerType.CONSULTATION, 5) == "consultations/5"
    assert namespace_for(MediaOwnerType.CUSTOMER_UPDATE, 5) == "customer-updates/5"


# ── authorization ──────────────────────────────────────────────────────


@pytest.mark.parametrize("owner_type", list(MediaOwnerType))
def test_viewer_can_never_view_design_photos(owner_type):
    viewer = _user(UserRole.VIEWER)
    assert MediaService.can_view(viewer, _asset(owner_type)) is False
    assert MediaService.can_edit(viewer, _asset(owner_type)) is False


@pytest.mark.parametrize("role", [UserRole.GOLDSMITH, UserRole.ADMIN])
@pytest.mark.parametrize("owner_type", list(MediaOwnerType))
def test_goldsmith_and_admin_can_view_and_edit(role, owner_type):
    user = _user(role)
    assert MediaService.can_view(user, _asset(owner_type)) is True
    assert MediaService.can_edit(user, _asset(owner_type)) is True


# ── dual write + lifecycle ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_order_upload_dual_writes_legacy_row_and_asset(
    db_session, media_root, sample_order, sample_user
):
    photo = await PhotoService.upload_photo(
        db_session, sample_order.id, _upload(_jpeg_with_gps()), sample_user.id, "n"
    )
    await db_session.commit()

    asset = await MediaService.get(db_session, photo.id)
    assert asset.legacy_id == photo.id
    assert asset.owner_type == "order" and asset.owner_id == sample_order.id
    assert asset.caption == "n" and asset.uploaded_by == sample_user.id
    assert asset.customer_visible is False
    assert MediaService.original_path(asset) == media_root / asset.storage_key
    assert photo.file_path == str(media_root / asset.storage_key)


@pytest.mark.asyncio
async def test_shared_file_is_kept_until_last_asset_is_deleted(
    db_session, media_root, sample_order, sample_user
):
    raw = _jpeg_with_gps()
    first = await PhotoService.upload_photo(
        db_session, sample_order.id, _upload(raw), sample_user.id
    )
    second = await PhotoService.upload_photo(
        db_session, sample_order.id, _upload(raw), sample_user.id
    )
    await db_session.commit()
    assert first.file_path == second.file_path  # content-addressed
    shared = media_root / (await MediaService.get(db_session, first.id)).storage_key

    assert await PhotoService.delete_photo(db_session, first.id, sample_user.id)
    await db_session.commit()
    assert shared.exists()  # still used by `second`

    assert await PhotoService.delete_photo(db_session, second.id, sample_user.id)
    await db_session.commit()
    assert not shared.exists()
    assert not (shared.parent / "thumbs" / f"{shared.stem}.jpg").exists()
    remaining = (
        await db_session.execute(
            select(OrderPhoto).where(OrderPhoto.order_id == sample_order.id)
        )
    ).all()
    assert remaining == []
    deleted = (
        (
            await db_session.execute(
                select(MediaAsset).where(MediaAsset.owner_id == sample_order.id)
            )
        )
        .scalars()
        .all()
    )
    assert deleted and all(a.deleted_at is not None for a in deleted)


@pytest.mark.asyncio
async def test_sort_order_increments_per_owner(
    db_session, media_root, sample_order, sample_user
):
    for color in ("red", "blue"):
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), color).save(buf, format="PNG")
        await PhotoService.upload_photo(
            db_session,
            sample_order.id,
            _upload(buf.getvalue(), "a.png"),
            sample_user.id,
        )
    assets = await MediaService.list_for_owner(
        db_session, MediaOwnerType.ORDER, sample_order.id
    )
    assert [a.sort_order for a in assets] == [0, 1]


@pytest.mark.asyncio
async def test_repair_and_consultation_uploads_are_bridged(
    db_session, media_root, sample_customer, sample_user
):
    from goldsmith_erp.db.models import (
        ConsultationPhotoKind,
        RepairItemType,
        RepairJob,
        RepairJobStatus,
        RepairPhotoPhase,
    )
    from goldsmith_erp.models.consultation import ConsultationCreate
    from goldsmith_erp.services.consultation_photo_service import (
        ConsultationPhotoService,
    )
    from goldsmith_erp.services.consultation_service import ConsultationService
    from goldsmith_erp.services.repair_photo_service import RepairPhotoService

    repair = RepairJob(
        repair_number="REP-2026-0900",
        bag_number="BAG-0900",
        customer_id=sample_customer.id,
        received_by=sample_user.id,
        item_description="Kette",
        item_type=RepairItemType.RING,
        status=RepairJobStatus.RECEIVED,
    )
    db_session.add(repair)
    await db_session.commit()
    consultation = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id, wishes="Ring"),
        conducted_by_user_id=sample_user.id,
    )

    repair_photo = await RepairPhotoService.upload_photo(
        db_session,
        repair.id,
        _upload(_jpeg_with_gps()),
        sample_user.id,
        RepairPhotoPhase.COMPLETED,
    )
    sketch = await ConsultationPhotoService.upload_photo(
        db_session,
        consultation.id,
        _upload(_jpeg_with_gps()),
        sample_user.id,
        ConsultationPhotoKind.SKETCH,
    )
    await db_session.commit()

    repair_asset = await MediaService.get_by_legacy(
        db_session, MediaOwnerType.REPAIR, str(repair_photo.id)
    )
    assert repair_asset is not None
    assert repair_asset.tag == "completed"
    assert repair_asset.storage_key.startswith(f"repairs/{repair.id}/")
    sketch_asset = await MediaService.get(db_session, sketch.id)
    assert sketch_asset.tag == "sketch"
    assert sketch_asset.storage_key.startswith(f"consultations/{consultation.id}/")

    await RepairPhotoService.delete_photo(db_session, repair_photo.id)
    await ConsultationPhotoService.delete_photo(db_session, sketch.id)
    await db_session.commit()
    assert not (media_root / repair_asset.storage_key).exists()
    assert not (media_root / sketch_asset.storage_key).exists()
    assert (
        await MediaService.get_by_legacy(
            db_session, MediaOwnerType.REPAIR, str(repair_photo.id)
        )
        is None
    )
