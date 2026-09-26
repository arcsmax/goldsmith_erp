# src/goldsmith_erp/services/media_store.py
"""
Storage backend for media assets (ARCH phase 4, ADR-2026-09-25-media).

``MediaStore`` is the only code that knows where media bytes live. Callers
hold an opaque ``storage_key`` and go through ``put`` / ``open`` /
``delete`` / ``url_for``. ``LocalMediaStore`` implements it on the local
filesystem under the same root the photo services have always used
(``settings.PHOTO_STORAGE_PATH``), so backups and the GDPR file erasure keep
covering one tree.

Key layout (content-addressed, sharded by the sha256 prefix):

    {namespace}/{sha256[:2]}/{sha256}.{ext}
    {namespace}/{sha256[:2]}/thumbs/{sha256}.jpg      (thumbnail)

``namespace`` is the owner's directory (``"42"`` for order 42,
``"repairs/7"``, ``"consultations/3"``), so identical bytes are stored once
per owner and a GDPR erasure of one customer can never unlink a file that
another customer's record still points at. The thumbnail sits in a
``thumbs/`` sibling, the same convention the legacy photo tables use, so the
existing erasure sweep and PDF/email readers keep working on either layout.

Compatibility branch: rows copied from the legacy photo tables keep their
old absolute ``file_path`` as ``storage_key``. ``open`` / ``delete`` accept
those too, as long as they resolve inside the root (path-traversal guard via
``image_validation.resolve_within_root``).
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import BinaryIO, Optional, Protocol

from goldsmith_erp.core.config import settings
from goldsmith_erp.services.image_validation import resolve_within_root

logger = logging.getLogger(__name__)

THUMBNAIL_DIR = "thumbs"
THUMBNAIL_EXT = "jpg"
DEFAULT_NAMESPACE = "media"

MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}
EXT_TO_MIME: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
}

_NAMESPACE_RE = re.compile(r"^[a-z0-9_-]+(/[a-z0-9_-]+)*$")


class MediaStoreError(Exception):
    """A storage key is invalid, escapes the root, or names no stored file."""


def sha256_hex(data: bytes) -> str:
    """Return the hex sha256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def mime_for_suffix(suffix: str) -> str:
    """Map a file suffix (``".jpg"`` or ``"jpg"``) to a MIME type."""
    return EXT_TO_MIME.get(suffix.lower().lstrip("."), "application/octet-stream")


def thumbnail_key_for(key: str) -> str:
    """Return the thumbnail key that belongs to ``key``.

    Same derivation for content-addressed and legacy keys:
    ``<parent>/thumbs/<stem>.jpg``.
    """
    original = Path(key)
    return str(original.parent / THUMBNAIL_DIR / f"{original.stem}.{THUMBNAIL_EXT}")


class MediaStore(Protocol):
    """Storage contract for media bytes. Keys are opaque to callers."""

    def put(self, data: bytes, mime: str, *, namespace: str = ...) -> str:
        """Store ``data`` and return its key (idempotent for equal bytes)."""

    def open(self, key: str) -> BinaryIO:
        """Open a stored file for binary reading."""

    def delete(self, key: str) -> bool:
        """Delete a stored file; False when it was already gone."""

    def url_for(self, key: str) -> str:
        """Return a backend-specific URI for ``key``."""

    def exists(self, key: str) -> bool:
        """Return whether ``key`` names a stored file."""


class LocalMediaStore:
    """``MediaStore`` on the local filesystem, rooted at ``root``."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root_override = root

    @property
    def root(self) -> Path:
        """Resolved storage root (read per call so tests can patch settings)."""
        base = self._root_override or Path(settings.PHOTO_STORAGE_PATH)
        return base.resolve()

    # ── key helpers ─────────────────────────────────────────────────────

    @staticmethod
    def key_for(sha256: str, ext: str, namespace: str = DEFAULT_NAMESPACE) -> str:
        """Content-addressed key for a digest, extension and namespace."""
        if not _NAMESPACE_RE.match(namespace):
            raise MediaStoreError(f"Ungueltiger Medien-Namensraum: {namespace!r}")
        return f"{namespace}/{sha256[:2]}/{sha256}.{ext}"

    def path_for(self, key: str) -> Path:
        """Absolute path for ``key``; refuses anything outside the root."""
        root = self.root
        resolved = resolve_within_root(key, root)
        if resolved is None or resolved == root:
            raise MediaStoreError("Speicherschluessel ausserhalb des Medienordners")
        return resolved

    # ── MediaStore contract ────────────────────────────────────────────

    def put(self, data: bytes, mime: str, *, namespace: str = DEFAULT_NAMESPACE) -> str:
        """Write ``data`` under its content address; return the key."""
        ext = MIME_TO_EXT.get(mime)
        if ext is None:
            raise MediaStoreError(f"Nicht unterstuetzter Medientyp: {mime}")
        key = self.key_for(sha256_hex(data), ext, namespace)
        path = self.path_for(key)
        if path.exists():
            # Content-addressed: same bytes, same key — nothing to write.
            return key
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f".{path.name}.partial")
        partial.write_bytes(data)
        partial.replace(path)  # atomic rename within one filesystem
        return key

    def open(self, key: str) -> BinaryIO:
        """Open ``key`` for reading (legacy absolute paths included)."""
        path = self.path_for(key)
        if not path.is_file():
            raise MediaStoreError("Mediendatei nicht gefunden")
        return path.open("rb")

    def delete(self, key: str) -> bool:
        """Unlink ``key``; False when it did not exist."""
        path = self.path_for(key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def url_for(self, key: str) -> str:
        """``file://`` URI of ``key`` (an object store would presign here)."""
        return self.path_for(key).as_uri()

    def exists(self, key: str) -> bool:
        """True when ``key`` is inside the root and names a regular file."""
        try:
            return self.path_for(key).is_file()
        except MediaStoreError:
            return False


_DEFAULT_STORE = LocalMediaStore()


def get_media_store() -> LocalMediaStore:
    """The process-wide media store (local filesystem today)."""
    return _DEFAULT_STORE
