"""
Integration tests for the order photo API (api/routers/photos.py).

W7 hygiene follow-up: a successful upload now publishes a reduced
``order_updates`` event (ids/action/timestamp only — never the image bytes,
notes, or other PII) strictly AFTER the DB commit, so other devices refresh
their order view. Mirrors the mocking approach in
tests/unit/test_realtime_publish.py: monkeypatch ``pubsub.publish_event``
(the module attribute, not the function) and record what was published.
"""

from __future__ import annotations

import io
import json

import pytest
from httpx import AsyncClient
from PIL import Image

from goldsmith_erp.core import pubsub
from goldsmith_erp.db.models import Order

ORDERS_URL = "/api/v1/orders/"


def _jpeg_bytes() -> bytes:
    """A minimal valid 4x4 white JPEG, Pillow-generated in-memory."""
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_publishes_reduced_order_event_after_commit(
    client: AsyncClient,
    admin_auth_headers: dict,
    sample_order: Order,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )

    published: list[tuple[str, str]] = []

    async def _record(channel: str, message: str) -> bool:
        published.append((channel, message))
        return True

    monkeypatch.setattr(pubsub, "publish_event", _record)

    files = {"file": ("photo.jpg", _jpeg_bytes(), "image/jpeg")}
    resp = await client.post(
        f"{ORDERS_URL}{sample_order.id}/photos",
        files=files,
        headers=admin_auth_headers,
    )

    assert resp.status_code == 201, resp.text
    photo_id = resp.json()["id"]

    # Published exactly once, on order_updates, with a reduced payload.
    assert len(published) == 1
    channel, raw = published[0]
    assert channel == "order_updates"
    payload = json.loads(raw)
    assert payload["action"] == "photo_added"
    assert payload["order_id"] == sample_order.id
    assert payload["photo_id"] == photo_id
    assert payload["timestamp"]
    # Never the image, notes, or any other field — ids/action/timestamp only.
    assert set(payload.keys()) == {"action", "order_id", "photo_id", "timestamp"}


@pytest.mark.asyncio
async def test_rejected_upload_does_not_publish(
    client: AsyncClient,
    admin_auth_headers: dict,
    sample_order: Order,
    tmp_path,
    monkeypatch,
) -> None:
    """A validation failure means nothing was committed — nothing to publish."""
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )

    published: list[tuple[str, str]] = []

    async def _record(channel: str, message: str) -> bool:
        published.append((channel, message))
        return True

    monkeypatch.setattr(pubsub, "publish_event", _record)

    files = {"file": ("not-a-photo.pdf", b"%PDF-1.4 not an image", "application/pdf")}
    resp = await client.post(
        f"{ORDERS_URL}{sample_order.id}/photos",
        files=files,
        headers=admin_auth_headers,
    )

    assert resp.status_code == 422
    assert published == []
