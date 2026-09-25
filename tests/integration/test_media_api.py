"""Integration tests for /api/v1/media (ARCH phase 4, ADR-2026-09-25-media)."""

from __future__ import annotations

import io
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from PIL import Image

from goldsmith_erp.core.security import create_access_token, get_password_hash
from goldsmith_erp.db.models import MediaAsset, Order, OrderPhoto, User, UserRole

MEDIA_URL = "/api/v1/media"


def _jpeg_bytes(color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 150), color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    return tmp_path.resolve()


@pytest_asyncio.fixture
async def viewer_headers(db_session) -> dict:
    user = User(
        email=f"viewer_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("viewerpassword123"),
        first_name="View",
        last_name="Er",
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


async def _upload(client, headers, order_id: int, color: str = "white") -> str:
    resp = await client.post(
        f"/api/v1/orders/{order_id}/photos",
        files={"file": ("p.jpg", _jpeg_bytes(color), "image/jpeg")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_uploaded_order_photo_is_served_via_media(
    client: AsyncClient, admin_auth_headers, sample_order: Order, media_root
):
    photo_id = await _upload(client, admin_auth_headers, sample_order.id)

    original = await client.get(f"{MEDIA_URL}/{photo_id}", headers=admin_auth_headers)
    assert original.status_code == 200
    assert original.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(original.content)) as img:
        assert img.size == (300, 150)

    thumb = await client.get(
        f"{MEDIA_URL}/{photo_id}/thumbnail", headers=admin_auth_headers
    )
    assert thumb.status_code == 200
    with Image.open(io.BytesIO(thumb.content)) as img:
        assert img.width == 200

    # The legacy endpoints keep serving the same bytes.
    legacy = await client.get(
        f"/api/v1/photos/{photo_id}/file", headers=admin_auth_headers
    )
    assert legacy.status_code == 200 and legacy.content == original.content


@pytest.mark.asyncio
async def test_list_media_for_owner(
    client: AsyncClient, auth_headers, sample_order: Order, media_root
):
    first = await _upload(client, auth_headers, sample_order.id, "white")
    second = await _upload(client, auth_headers, sample_order.id, "black")

    resp = await client.get(
        MEDIA_URL,
        params={"owner_type": "order", "owner_id": sample_order.id},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [item["id"] for item in body] == [first, second]
    assert body[0]["customer_visible"] is False
    assert body[0]["legacy_id"] == first
    assert "storage_key" not in body[0]  # internal path never leaves the server


@pytest.mark.asyncio
async def test_viewer_gets_403_on_design_photos(
    client: AsyncClient,
    admin_auth_headers,
    viewer_headers,
    sample_order: Order,
    media_root,
):
    photo_id = await _upload(client, admin_auth_headers, sample_order.id)

    for url in (f"{MEDIA_URL}/{photo_id}", f"{MEDIA_URL}/{photo_id}/thumbnail"):
        resp = await client.get(url, headers=viewer_headers)
        assert resp.status_code == 403, url
    listing = await client.get(
        MEDIA_URL,
        params={"owner_type": "order", "owner_id": sample_order.id},
        headers=viewer_headers,
    )
    assert listing.status_code == 403


@pytest.mark.asyncio
async def test_unknown_and_deleted_media_are_404(
    client: AsyncClient, admin_auth_headers, sample_order: Order, media_root
):
    assert (
        await client.get(f"{MEDIA_URL}/{uuid.uuid4()}", headers=admin_auth_headers)
    ).status_code == 404

    photo_id = await _upload(client, admin_auth_headers, sample_order.id)
    deleted = await client.delete(
        f"/api/v1/photos/{photo_id}", headers=admin_auth_headers
    )
    assert deleted.status_code == 204
    assert (
        await client.get(f"{MEDIA_URL}/{photo_id}", headers=admin_auth_headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_migrated_legacy_path_is_served_through_compat_branch(
    client: AsyncClient,
    admin_auth_headers,
    db_session,
    sample_order: Order,
    admin_user: User,
    media_root,
):
    # A pre-media row: old {order_id}/{uuid}.jpg layout, bridged the way the
    # arch4 data migration copies it (storage_key = the old absolute path).
    legacy_file = media_root / str(sample_order.id) / f"{uuid.uuid4()}.jpg"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_bytes(_jpeg_bytes("gray"))
    photo_id = str(uuid.uuid4())
    db_session.add(
        OrderPhoto(
            id=photo_id,
            order_id=sample_order.id,
            file_path=str(legacy_file),
            taken_by=admin_user.id,
        )
    )
    db_session.add(
        MediaAsset(
            id=photo_id,
            owner_type="order",
            owner_id=sample_order.id,
            kind="photo",
            storage_key=str(legacy_file),
            mime="image/jpeg",
            legacy_id=photo_id,
        )
    )
    await db_session.commit()

    resp = await client.get(f"{MEDIA_URL}/{photo_id}", headers=admin_auth_headers)
    assert resp.status_code == 200
    assert resp.content == legacy_file.read_bytes()
    # No thumbnail was ever made: falls back to the original.
    thumb = await client.get(
        f"{MEDIA_URL}/{photo_id}/thumbnail", headers=admin_auth_headers
    )
    assert thumb.status_code == 200 and thumb.content == resp.content


@pytest.mark.asyncio
async def test_storage_key_outside_root_is_refused(
    client: AsyncClient, admin_auth_headers, db_session, sample_order, media_root
):
    media_id = str(uuid.uuid4())
    db_session.add(
        MediaAsset(
            id=media_id,
            owner_type="order",
            owner_id=sample_order.id,
            kind="photo",
            storage_key="/etc/passwd",
            mime="image/jpeg",
        )
    )
    await db_session.commit()

    resp = await client.get(f"{MEDIA_URL}/{media_id}", headers=admin_auth_headers)
    assert resp.status_code == 404
    assert "passwd" not in resp.text
