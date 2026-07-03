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

import io
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from PIL import Image

# ─── Constants ────────────────────────────────────────────────────────────────

THUMBNAIL_WIDTH: int = 200
EMAIL_VARIANT_MAX_PX: int = 1600
_JPEG_QUALITY: int = 85
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


# ─── Thumbnail / email-variant generation ──────────────────────────────────────
#
# Both create_thumbnail and create_email_variant re-encode a source image as
# a resized JPEG. They differ only in HOW the target size is derived
# (fixed-width upscale-or-downscale vs. longest-side cap, no upscale) — the
# convert-to-RGB and resize-via-LANCZOS mechanics are shared via the two
# helpers below so neither function duplicates that logic.


def _convert_for_jpeg(img: Image.Image) -> Image.Image:
    """Convert RGBA/P/LA images to RGB so they can be saved as JPEG."""
    if img.mode in ("RGBA", "P", "LA"):
        return img.convert("RGB")
    return img


def _resize_to(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize `img` to `size` via LANCZOS resampling; no-op if already that size."""
    if img.size == size:
        return img
    return img.resize(size, Image.LANCZOS)


def create_thumbnail(source_path: Path, thumb_path: Path) -> None:
    """
    Create a thumbnail of `source_path` at `thumb_path`.

    The thumbnail is THUMBNAIL_WIDTH pixels wide; height is auto-scaled.
    Output is always saved as JPEG for consistency and small file size.
    """
    with Image.open(source_path) as opened:
        # Explicit `Image.Image` annotation: `_convert_for_jpeg`/`_resize_to`
        # return the base `Image.Image` type, wider than the `ImageFile`
        # subtype mypy infers for the `with ... as` target — annotating the
        # rebind target up front avoids an "incompatible assignment" report.
        img: Image.Image = opened
        img = _convert_for_jpeg(img)
        w_orig, h_orig = img.size
        if w_orig == 0:
            raise PhotoValidationError("Image has zero width — corrupt file.")
        scale = THUMBNAIL_WIDTH / w_orig
        new_h = max(1, int(h_orig * scale))
        img_resized = _resize_to(img, (THUMBNAIL_WIDTH, new_h))
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        img_resized.save(
            thumb_path, format="JPEG", quality=_JPEG_QUALITY, optimize=True
        )


def create_email_variant(source: Path, max_px: int = EMAIL_VARIANT_MAX_PX) -> bytes:
    """
    Produce an email-safe JPEG variant of `source`.

    - Longest side is capped at `max_px` (no upscaling — smaller images pass
      through at their original size, unlike `create_thumbnail`'s fixed-width
      scaling).
    - Re-saved as JPEG at quality 85, same as `create_thumbnail`.
    - EXIF metadata is stripped as a side effect: Pillow only embeds EXIF on
      save when explicitly passed via the `exif=` kwarg, which this function
      never does, so re-encoding through `Image.save()` here drops GPS/camera
      metadata even when the source carried it (design-IP / customer-privacy
      requirement — photos shared with customers must not leak shoot location
      or device details).

    Returns the encoded JPEG bytes directly (no filesystem write) — the
    caller (EmailService attachments, PDFService photo embeds) consumes the
    bytes immediately.

    Raises:
        PhotoValidationError: if the source image has a zero width or height
            (corrupt file).
    """
    with Image.open(source) as opened:
        img: Image.Image = opened
        img = _convert_for_jpeg(img)
        w_orig, h_orig = img.size
        if w_orig == 0 or h_orig == 0:
            raise PhotoValidationError("Image has zero dimension — corrupt file.")
        longest = max(w_orig, h_orig)
        if longest > max_px:
            scale = max_px / longest
            new_w = max(1, int(w_orig * scale))
            new_h = max(1, int(h_orig * scale))
            img = _resize_to(img, (new_w, new_h))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        return buffer.getvalue()
