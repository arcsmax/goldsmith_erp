"""Unit tests for services/media_store.py (ARCH phase 4)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from goldsmith_erp.services.media_store import (
    LocalMediaStore,
    MediaStoreError,
    mime_for_suffix,
    thumbnail_key_for,
)


@pytest.fixture
def store(tmp_path) -> LocalMediaStore:
    return LocalMediaStore(root=tmp_path)


def test_put_is_content_addressed_by_sha256_prefix(store, tmp_path):
    data = b"\x89PNG fake bytes"
    sha = hashlib.sha256(data).hexdigest()

    key = store.put(data, "image/png", namespace="42")

    assert key == f"42/{sha[:2]}/{sha}.png"
    assert (tmp_path / key).read_bytes() == data


def test_put_same_bytes_twice_returns_same_key_without_rewrite(store, tmp_path):
    first = store.put(b"same", "image/jpeg", namespace="repairs/7")
    mtime = (tmp_path / first).stat().st_mtime_ns

    second = store.put(b"same", "image/jpeg", namespace="repairs/7")

    assert first == second
    assert (tmp_path / second).stat().st_mtime_ns == mtime
    assert not list(tmp_path.rglob("*.partial"))


def test_namespaces_keep_owners_apart(store):
    assert store.put(b"x", "image/jpeg", namespace="1") != store.put(
        b"x", "image/jpeg", namespace="2"
    )


def test_open_and_delete_round_trip(store):
    key = store.put(b"abc", "image/webp")
    with store.open(key) as handle:
        assert handle.read() == b"abc"
    assert store.exists(key)

    assert store.delete(key) is True
    assert store.delete(key) is False
    assert not store.exists(key)
    with pytest.raises(MediaStoreError):
        store.open(key)


def test_legacy_absolute_path_inside_root_is_readable(store, tmp_path):
    legacy = tmp_path / "42" / "0b1c-legacy.jpg"
    legacy.parent.mkdir()
    legacy.write_bytes(b"old")

    with store.open(str(legacy)) as handle:
        assert handle.read() == b"old"
    assert store.url_for(str(legacy)) == legacy.resolve().as_uri()


@pytest.mark.parametrize("key", ["/etc/passwd", "../../etc/passwd", ""])
def test_keys_outside_the_root_are_refused(store, key):
    with pytest.raises(MediaStoreError):
        store.open(key)
    with pytest.raises(MediaStoreError):
        store.delete(key)
    assert store.exists(key) is False


def test_symlink_escaping_the_root_is_refused(store, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.jpg"
    outside.write_bytes(b"secret")
    link = store.root / "link.jpg"
    link.symlink_to(outside)

    with pytest.raises(MediaStoreError):
        store.open("link.jpg")


def test_unsupported_mime_and_bad_namespace_are_rejected(store):
    with pytest.raises(MediaStoreError):
        store.put(b"x", "text/html")
    with pytest.raises(MediaStoreError):
        store.put(b"x", "image/png", namespace="../evil")


def test_thumbnail_key_is_the_thumbs_sibling():
    assert thumbnail_key_for("42/ab/abcdef.png") == "42/ab/thumbs/abcdef.jpg"
    assert thumbnail_key_for("/data/photos/42/u.webp") == (
        "/data/photos/42/thumbs/u.jpg"
    )


def test_mime_for_suffix():
    assert mime_for_suffix(".JPG") == "image/jpeg"
    assert mime_for_suffix("webp") == "image/webp"
    assert mime_for_suffix(".exe") == "application/octet-stream"


def test_default_root_follows_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    assert LocalMediaStore().root == Path(tmp_path).resolve()
