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
  - Images are rejected from their DECLARED header dimensions before Pillow
    decodes the full pixel buffer (SEC-18: decompression-bomb protection).
  - Every stored original is re-encoded with EXIF metadata (GPS, camera,
    etc.) stripped; the EXIF Orientation tag is applied to the pixel data
    first so removing it doesn't change how the photo displays (GDPR-19).
"""

import asyncio
import io
import logging
import warnings
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError

from goldsmith_erp.core.config import settings

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

THUMBNAIL_WIDTH: int = 200
EMAIL_VARIANT_MAX_PX: int = 1600
_JPEG_QUALITY: int = 85
_MAX_MAGIC_BYTES: int = 12  # Enough to cover all signatures below

_SAVE_FORMAT: dict[str, str] = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}

# SEC-18: bounds every Pillow decode in this process — not just the explicit
# header check in `_reject_oversized_or_corrupt` below, in case some other
# code path calls Image.open() directly (e.g. pdf_service.py embedding an
# already-stored photo). `Image.open()` itself compares the DECLARED header
# dimensions against this value before returning: it warns
# (DecompressionBombWarning) above this count and raises
# (DecompressionBombError) above 2x it. `_reject_oversized_or_corrupt` scopes
# the warning-to-error conversion locally so the single-threshold reject at
# IMAGE_MAX_MEGAPIXELS holds without touching this process's global warning
# filters.
Image.MAX_IMAGE_PIXELS = settings.IMAGE_MAX_MEGAPIXELS * 1_000_000


class PhotoValidationError(ValueError):
    """Raised when an uploaded photo fails validation (type, size, or content)."""


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
        PhotoValidationError: If the file exceeds the size limit, its type
            cannot be determined from magic bytes, its declared pixel
            dimensions exceed settings.IMAGE_MAX_MEGAPIXELS, or the content
            cannot be decoded as a valid image (corrupt file / content that
            doesn't match its magic-byte type).
    """
    # A second, independent ceiling from Settings (IMAGE_MAX_UPLOAD_BYTES)
    # alongside the caller-supplied max_mb — whichever is smaller wins, so
    # this module's own bound can never be silently loosened by a caller
    # passing a larger max_mb.
    max_bytes = min(max_mb * 1024 * 1024, settings.IMAGE_MAX_UPLOAD_BYTES)

    # Read the whole file (bounded by max_bytes + 1 to detect overflow).
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise PhotoValidationError(f"Datei zu groß. Maximum: {max_mb} MB.")

    header = raw[:_MAX_MAGIC_BYTES]
    ext = detect_image_type(header)
    if ext is None:
        raise PhotoValidationError("Ungültiges Dateiformat. Erlaubt: JPEG, PNG, WEBP.")

    _reject_oversized_or_corrupt(raw)

    return raw, ext


def _reject_oversized_or_corrupt(raw: bytes) -> None:
    """
    Reject an image whose DECLARED header dimensions exceed
    settings.IMAGE_MAX_MEGAPIXELS, or whose content fails Pillow's
    structural integrity check — before any pixel buffer is allocated.

    `Image.open()` only parses the file header (width/height/mode); it does
    NOT decode pixel data until `.load()` / `.verify()` / `.resize()` /
    `.save()` is called. It DOES, however, compare those header dimensions
    against `Image.MAX_IMAGE_PIXELS` (set from settings at import time,
    above) internally, before returning — so `Image.open()` itself already
    rejects from the header in constant time, regardless of how large the
    file claims to be (a ~150 Mpx image can be declared in a file of a few
    hundred bytes, the classic decompression-bomb shape). Pillow's own check
    is two-tier (warn above the limit, hard error above 2x it); the
    `catch_warnings` scope below turns that warning into an error too, so
    this function rejects at a single, exact threshold
    (IMAGE_MAX_MEGAPIXELS) instead of Pillow's fuzzier default.

    `verify()` runs only for images that passed the size gate above, so it
    is itself bounded to already-small-enough images; it also catches
    structurally-corrupt content that happens to start with a valid
    magic-byte signature.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                probe.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise PhotoValidationError(
            f"Bild zu groß. Maximum: {settings.IMAGE_MAX_MEGAPIXELS} Megapixel."
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PhotoValidationError(
            "Ungültiges oder beschädigtes Bild — Datei konnte nicht gelesen werden."
        ) from exc


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


# ─── Original storage — EXIF stripped, orientation applied (GDPR-19) ──────────


def _apply_exif_orientation(img: Image.Image) -> Image.Image:
    """
    Apply the EXIF Orientation tag to the pixel data, then drop the tag.

    `ImageOps.exif_transpose()` physically rotates/flips the pixel buffer
    according to the image's Orientation tag (values 2-8) and returns a new
    image with the tag already removed. It MUST run before the image is
    re-encoded without EXIF below — stripping the tag without applying it
    would silently change how the photo displays.
    """
    transposed = ImageOps.exif_transpose(img)
    return transposed if transposed is not None else img


def strip_exif_and_reencode(raw: bytes, ext: str) -> bytes:
    """
    Re-encode an uploaded image for storage with all EXIF metadata removed.

    GDPR-19: stored originals must never carry GPS or camera EXIF. Pillow
    only embeds EXIF on save when explicitly passed via the `exif=` kwarg —
    none of the `.save()` calls below ever do, so re-encoding through this
    function drops GPS/camera/all other metadata as a side effect, for
    every one of the three accepted formats (JPEG/PNG/WEBP). Orientation is
    applied to the pixel data FIRST (`_apply_exif_orientation`) so removing
    the tag doesn't change how the photo displays.

    Args:
        raw: Validated image bytes — the caller (`read_validated_image`) has
             already run `_reject_oversized_or_corrupt` on this content, so
             the decode below is bounded.
        ext: One of "jpg" / "png" / "webp", as returned by
             `detect_image_type`.

    Returns:
        Re-encoded image bytes in the same format as `ext`, with no EXIF.

    Raises:
        PhotoValidationError: if the content cannot be decoded as a valid
            image, or has a zero width/height (corrupt file).
    """
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            img: Image.Image = opened
            img.load()  # decode — bounded by MAX_IMAGE_PIXELS + the pre-check above
            img = _apply_exif_orientation(img)
            width, height = img.size
            if width == 0 or height == 0:
                raise PhotoValidationError("Image has zero dimension — corrupt file.")

            save_format = _SAVE_FORMAT[ext]
            buffer = io.BytesIO()
            if save_format == "JPEG":
                img = _convert_for_jpeg(img)
                img.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
            elif save_format == "PNG":
                img.save(buffer, format="PNG", optimize=True)
            else:  # WEBP
                img.save(buffer, format="WEBP", quality=_JPEG_QUALITY)
            return buffer.getvalue()
    except PhotoValidationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise PhotoValidationError(
            "Ungültiges oder beschädigtes Bild — Datei konnte nicht verarbeitet werden."
        ) from exc


async def store_processed_original(raw: bytes, ext: str, dest: Path) -> None:
    """
    Strip EXIF (orientation applied first) and write the processed original
    to `dest`, off the event loop and time-bounded (SEC-18).

    `strip_exif_and_reencode` is synchronous, CPU-bound Pillow work; calling
    it directly in an async request handler would block the event loop —
    and every other in-flight request — for as long as the decode/re-encode
    takes. `run_in_threadpool` moves the work to a worker thread;
    `asyncio.wait_for` bounds how long a pathological (but dimension-valid)
    image may occupy that thread before the request fails loudly instead of
    hanging indefinitely.

    Raises:
        PhotoValidationError: on decode failure (via `strip_exif_and_reencode`)
            or if processing exceeds settings.IMAGE_PROCESSING_TIMEOUT_SECONDS.
    """
    try:
        processed = await asyncio.wait_for(
            run_in_threadpool(strip_exif_and_reencode, raw, ext),
            timeout=settings.IMAGE_PROCESSING_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        logger.warning(
            "Image processing (EXIF strip / re-encode) timed out",
            extra={
                "dest": str(dest),
                "timeout_s": settings.IMAGE_PROCESSING_TIMEOUT_SECONDS,
            },
        )
        raise PhotoValidationError(
            "Bildverarbeitung hat das Zeitlimit überschritten."
        ) from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(processed)


async def create_thumbnail_bounded(source_path: Path, thumb_path: Path) -> None:
    """Time-bounded, off-event-loop wrapper around `create_thumbnail` (SEC-18)."""
    try:
        await asyncio.wait_for(
            run_in_threadpool(create_thumbnail, source_path, thumb_path),
            timeout=settings.IMAGE_PROCESSING_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise PhotoValidationError(
            "Thumbnail-Erstellung hat das Zeitlimit überschritten."
        ) from exc
