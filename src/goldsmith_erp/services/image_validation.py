# src/goldsmith_erp/services/image_validation.py
"""
Shared image-upload validation for photo services.

Extracted from `photo_service.py` (order photos) so the same magic-byte
detection, size-limit enforcement, and thumbnail generation can be reused by
`consultation_photo_service.py` (consultation sketches/references) without
copy-pasting the validation logic.

Security notes:
  - File type is determined by magic bytes, NOT the client-supplied Content-Type
    or filename extension, to prevent content-type spoofing.
"""

from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from PIL import Image

# ─── Constants ────────────────────────────────────────────────────────────────

THUMBNAIL_WIDTH: int = 200
_MAX_MAGIC_BYTES: int = 12  # Enough to cover all signatures below


class PhotoValidationError(ValueError):
    """Raised when an uploaded photo fails validation (type or size)."""


# ─── Storage-root anchoring ────────────────────────────────────────────────────


def resolve_within_root(raw_path: str, root: Path) -> Optional[Path]:
    """
    Resolve ``raw_path`` and return it only if it lies inside ``root``.

    Shared path-traversal guard for the photo services (mirrors
    ``FileErasureService._safe_resolve``). DB path columns are not
    trustworthy by construction — the legacy repair-photo API accepted
    arbitrary client strings into ``repair_photos.file_path`` — so every
    read/serve/delete that starts from a stored path must be anchored
    here before any filesystem I/O.

    Behaviour:
      - Relative paths are anchored under ``root`` before resolution.
      - Absolute paths are resolved as-is so escapes are detectable.
      - Symlinks are followed (``Path.resolve``), so a link pointing
        outside ``root`` is refused too.

    Returns:
        The resolved absolute Path when it is inside (or equal to)
        ``root``; ``None`` when the candidate escapes the root, is
        empty, or cannot be resolved. Callers receiving ``None`` MUST
        NOT perform any filesystem I/O on the raw value and should
        surface an ID-only error (never echo the raw path to clients).
    """
    if not raw_path:
        return None

    candidate = Path(raw_path)
    root_resolved = root.resolve(strict=False)

    if not candidate.is_absolute():
        candidate = root_resolved / candidate

    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        # Pathological input (e.g. infinite symlink loop) — refuse.
        return None

    if not resolved.is_relative_to(root_resolved):
        return None

    return resolved


# ─── Type detection ────────────────────────────────────────────────────────────


def detect_image_type(header: bytes) -> Optional[str]:
    """
    Detect image type from the first bytes of the file.

    Returns file extension ("jpg", "png", "webp") or None if unsupported.
    The caller must pass at least _MAX_MAGIC_BYTES bytes.
    """
    if header[:3] == b"\xff\xd8\xff":
        return "jpg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    # WEBP: 'RIFF' at offset 0 and 'WEBP' at offset 8
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


# ─── Size + type validated read ────────────────────────────────────────────────


async def read_validated_image(file: UploadFile, max_mb: int) -> tuple[bytes, str]:
    """
    Read an uploaded file, enforcing the size limit and magic-byte type check.

    Args:
        file:   FastAPI UploadFile from the multipart request.
        max_mb: Maximum allowed size in megabytes.

    Returns:
        Tuple of (raw_bytes, extension) where extension is one of
        "jpg" / "png" / "webp".

    Raises:
        PhotoValidationError: If the file exceeds max_mb or its type cannot
            be determined from magic bytes.
    """
    max_bytes = max_mb * 1024 * 1024

    # Read the whole file (bounded by max_bytes + 1 to detect overflow).
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise PhotoValidationError(f"Datei zu groß. Maximum: {max_mb} MB.")

    header = raw[:_MAX_MAGIC_BYTES]
    ext = detect_image_type(header)
    if ext is None:
        raise PhotoValidationError("Ungültiges Dateiformat. Erlaubt: JPEG, PNG, WEBP.")

    return raw, ext


# ─── Thumbnail generation ──────────────────────────────────────────────────────


def create_thumbnail(source_path: Path, thumb_path: Path) -> None:
    """
    Create a thumbnail of `source_path` at `thumb_path`.

    The thumbnail is THUMBNAIL_WIDTH pixels wide; height is auto-scaled.
    Output is always saved as JPEG for consistency and small file size.
    """
    with Image.open(source_path) as img:
        # Convert RGBA/P images to RGB so they can be saved as JPEG.
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        w_orig, h_orig = img.size
        if w_orig == 0:
            raise PhotoValidationError("Image has zero width — corrupt file.")
        scale = THUMBNAIL_WIDTH / w_orig
        new_h = max(1, int(h_orig * scale))
        img_resized = img.resize((THUMBNAIL_WIDTH, new_h), Image.LANCZOS)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        img_resized.save(thumb_path, format="JPEG", quality=85, optimize=True)
