"""customer_visible flag (ARCH phase 4): PATCH /media/{id}, status report
and Kundeninfo photo selection."""

from __future__ import annotations

import io
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from fastapi import UploadFile
from httpx import AsyncClient
from PIL import Image

from goldsmith_erp.core.security import create_access_token, get_password_hash
from goldsmith_erp.db.models import (
    MediaOwnerType,
    Order,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    RepairPhotoPhase,
    User,
    UserRole,
)
from goldsmith_erp.services import status_report_service
from goldsmith_erp.services.customer_message_service import (
    MessageKind,
    default_photo_ids,
)
from goldsmith_erp.services.media_service import MediaService
from goldsmith_erp.services.photo_service import PhotoService
from goldsmith_erp.services.repair_photo_service import RepairPhotoService

MEDIA_URL = "/api/v1/media"


def _upload(color: str) -> UploadFile:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, format="JPEG")
    buf.seek(0)
    return UploadFile(filename="p.jpg", file=buf)


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    return tmp_path


@pytest_asyncio.fixture
async def viewer_headers(db_session) -> dict:
    user = User(
        email=f"viewer_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("viewerpassword123"),
        role=UserRole.VIEWER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=timedelta(hours=1)
    )
    return {"Authorization": f"Bearer {token}"}


async def _order_photos(db, order: Order, user: User, colors) -> list:
    photos = [
        await PhotoService.upload_photo(db, order.id, _upload(color), user.id)
        for color in colors
    ]
    await db.commit()
    return photos


# ── PATCH /media/{id} ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_goldsmith_toggles_customer_visible(
    client: AsyncClient, auth_headers, db_session, sample_order, sample_user, media_root
):
    (photo,) = await _order_photos(db_session, sample_order, sample_user, ["red"])

    on = await client.patch(
        f"{MEDIA_URL}/{photo.id}", json={"customer_visible": True}, headers=auth_headers
    )
    assert on.status_code == 200, on.text
    assert on.json()["customer_visible"] is True
    listing = await client.get(
        MEDIA_URL,
        params={"owner_type": "order", "owner_id": sample_order.id},
        headers=auth_headers,
    )
    assert listing.json()[0]["customer_visible"] is True

    off = await client.patch(
        f"{MEDIA_URL}/{photo.id}",
        json={"customer_visible": False},
        headers=auth_headers,
    )
    assert off.status_code == 200 and off.json()["customer_visible"] is False


@pytest.mark.asyncio
async def test_patch_rules(
    client: AsyncClient,
    auth_headers,
    viewer_headers,
    db_session,
    sample_order,
    sample_user,
    media_root,
):
    (photo,) = await _order_photos(db_session, sample_order, sample_user, ["red"])
    url = f"{MEDIA_URL}/{photo.id}"

    viewer = await client.patch(
        url, json={"customer_visible": True}, headers=viewer_headers
    )
    assert viewer.status_code == 403
    extra = await client.patch(
        url, json={"customer_visible": True, "caption": "x"}, headers=auth_headers
    )
    assert extra.status_code == 422
    missing = await client.patch(
        f"{MEDIA_URL}/{uuid.uuid4()}",
        json={"customer_visible": True},
        headers=auth_headers,
    )
    assert missing.status_code == 404
    asset = await MediaService.get(db_session, photo.id)
    await db_session.refresh(asset)
    assert asset.customer_visible is False


# ── status report ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_report_uses_flagged_order_photos(
    db_session, sample_order, sample_user, media_root
):
    red, blue, green = await _order_photos(
        db_session, sample_order, sample_user, ["red", "blue", "green"]
    )
    # No flag and nothing sent yet: the pre-flag rule yields no photos.
    assert await status_report_service._order_photos(db_session, sample_order.id) == []

    for photo in (red, green):
        asset = await MediaService.get(db_session, photo.id)
        await MediaService.set_customer_visible(db_session, asset, True)
    await db_session.commit()

    photos = await status_report_service._order_photos(db_session, sample_order.id)
    assert len(photos) == 2
    assert all(data[:3] == b"\xff\xd8\xff" for data in photos)


@pytest.mark.asyncio
async def test_status_report_repair_flag_narrows_latest_photos(
    db_session, sample_customer, sample_user, media_root
):
    repair = RepairJob(
        repair_number=f"REP-2026-{uuid.uuid4().hex[:4]}",
        bag_number="BAG-7",
        customer_id=sample_customer.id,
        received_by=sample_user.id,
        item_description="Kette",
        item_type=RepairItemType.RING,
        status=RepairJobStatus.RECEIVED,
    )
    db_session.add(repair)
    await db_session.commit()
    uploaded = [
        await RepairPhotoService.upload_photo(
            db_session,
            repair.id,
            _upload(color),
            sample_user.id,
            RepairPhotoPhase.INTAKE,
        )
        for color in ("red", "blue", "green")
    ]
    # Without a flag: the latest photos (unchanged rule).
    assert len(await status_report_service._repair_photos(db_session, repair.id)) == 3

    asset = await MediaService.get_by_legacy(
        db_session, MediaOwnerType.REPAIR, str(uploaded[1].id)
    )
    await MediaService.set_customer_visible(db_session, asset, True)
    await db_session.commit()

    assert len(await status_report_service._repair_photos(db_session, repair.id)) == 1


# ── Kundeninfo photo selection ───────────────────────────────────────


@pytest.mark.asyncio
async def test_default_photo_ids_rules(
    db_session, sample_order, sample_user, media_root
):
    red, blue = await _order_photos(
        db_session, sample_order, sample_user, ["red", "blue"]
    )

    # No flag: nothing changes.
    assert (
        await default_photo_ids(
            db_session, MessageKind.PHOTO_UPDATE, sample_order.id, []
        )
        == []
    )

    asset = await MediaService.get(db_session, blue.id)
    await MediaService.set_customer_visible(db_session, asset, True)
    await db_session.commit()

    # Photo message without ticks -> flagged photos.
    assert await default_photo_ids(
        db_session, MessageKind.PHOTO_UPDATE, sample_order.id, None
    ) == [blue.id]
    # Ticked photos always win.
    assert await default_photo_ids(
        db_session, MessageKind.PHOTO_UPDATE, sample_order.id, [red.id]
    ) == [red.id]
    # Text-only messages never pick up photos implicitly.
    assert (
        await default_photo_ids(
            db_session, MessageKind.STATUS_UPDATE, sample_order.id, None
        )
        is None
    )
    assert (
        await default_photo_ids(db_session, MessageKind.PHOTO_UPDATE, None, None)
        is None
    )
