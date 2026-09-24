"""Unit tests for SEC-18 (bounded image decoding) and GDPR-19 (EXIF stripped).

Covers `services/image_validation.py`'s hardening around the shared
`read_validated_image()` entry point used by every photo service
(order / repair / consultation photos):

  1. A JPEG carrying GPS + Orientation EXIF is re-encoded with no EXIF and
     its pixel data physically rotated per the Orientation tag.
  2. An image whose DECLARED header dimensions exceed
     settings.IMAGE_MAX_MEGAPIXELS is rejected quickly, without Pillow ever
     allocating the full pixel buffer (the crafted PNGs below are a few
     hundred bytes despite declaring gigapixel dimensions).
  3. Content that doesn't decode as a valid image — including content whose
     first bytes are forged to match a real magic-byte signature — is
     rejected.

Also covers the async, threadpool-bounded wrappers
(`store_processed_original`, `create_thumbnail_bounded`) that the photo
services call instead of writing raw bytes / calling Pillow synchronously
on the event loop.
"""

import io
import struct
import time
import zlib
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from goldsmith_erp.core.config import settings
from goldsmith_erp.services import image_validation as iv
from goldsmith_erp.services.image_validation import (
    PhotoValidationError,
    create_thumbnail_bounded,
    read_validated_image,
    store_processed_original,
    strip_exif_and_reencode,
)

# ─── Fixtures / helpers ─────────────────────────────────────────────────────


def _upload(raw: bytes, filename: str = "photo.jpg") -> UploadFile:
    """Wrap raw bytes as a FastAPI UploadFile, mirroring the other photo-
    service test suites' `_jpeg_upload()` helper."""
    return UploadFile(filename=filename, file=io.BytesIO(raw))


def _jpeg_with_gps_and_orientation(width: int = 16, height: int = 24) -> bytes:
    """
    A JPEG with a GPS EXIF tag and Orientation=6 ("rotate 90° CW to display
    correctly"). A solid-color top-left 8x8 block distinguishes orientation
    after re-encoding: large flat regions survive JPEG quantization almost
    losslessly at quality=100, so the block's average color stays reliably
    identifiable even after two full JPEG re-encodes.
    """
    img = Image.new("RGB", (width, height), (200, 0, 0))
    for y in range(8):
        for x in range(8):
            img.putpixel((x, y), (0, 200, 0))

    exif = img.getexif()
    exif[0x0112] = 6  # Orientation
    exif[0x8825] = {  # GPSInfo IFD
        1: "N",
        2: (IFDRational(52, 1), IFDRational(30, 1), IFDRational(0, 1)),
        3: "E",
        4: (IFDRational(13, 1), IFDRational(24, 1), IFDRational(0, 1)),
    }

    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif, quality=100)
    return buf.getvalue()


def _avg_region(
    img: Image.Image, x0: int, x1: int, y0: int, y1: int
) -> tuple[float, float, float]:
    """Average (R, G, B) over a rectangular region — used to check where the
    solid-color marker block ended up after orientation is applied, without
    depending on an exact per-pixel match (JPEG re-encoding isn't lossless)."""
    r_total = g_total = b_total = 0
    count = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = img.getpixel((x, y))
            r_total += r
            g_total += g
            b_total += b
            count += 1
    return r_total / count, g_total / count, b_total / count


def _crafted_bomb_png(width: int, height: int) -> bytes:
    """
    A structurally-valid PNG that DECLARES `width`x`height` in its IHDR
    chunk but carries only a single, deliberately-truncated IDAT scanline —
    the classic decompression-bomb shape. `Image.open()` reads `.size` from
    the IHDR chunk alone; it does not need (or read) a complete IDAT stream
    to do so, so this file stays a few hundred bytes regardless of how large
    `width`/`height` claim to be.
    """

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00" * width)  # one truncated scanline
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# ─── (1) GPS EXIF stripped, orientation applied ────────────────────────────


class TestExifStrippingAndOrientation:
    def test_strip_exif_and_reencode_removes_gps_and_applies_orientation(self):
        raw = _jpeg_with_gps_and_orientation()

        processed = strip_exif_and_reencode(raw, "jpg")

        result = Image.open(io.BytesIO(processed))
        assert dict(result.getexif()) == {}, "no EXIF tag may survive re-encoding"

        # Orientation=6 swaps width/height on display (16x24 source -> 24x16
        # stored) — this alone proves the pixel data was physically rotated,
        # not just that the tag was dropped.
        assert result.size == (24, 16)

        # The green marker block sat top-left in the un-rotated source; after
        # applying Orientation=6 and re-encoding it must land top-right, with
        # the original red now occupying the top-left.
        r, g, b = _avg_region(result, result.size[0] - 8, result.size[0], 0, 8)
        assert (
            g > 150 and g > r and g > b
        ), f"expected a greenish top-right corner after rotation, got ({r}, {g}, {b})"
        r, g, b = _avg_region(result, 0, 8, 0, 8)
        assert (
            r > 150 and r > g
        ), f"expected a reddish top-left corner after rotation, got ({r}, {g}, {b})"

    @pytest.mark.asyncio
    async def test_store_processed_original_writes_a_stripped_file_to_disk(
        self, tmp_path: Path
    ):
        raw = _jpeg_with_gps_and_orientation()
        dest = tmp_path / "sub" / "photo.jpg"

        await store_processed_original(raw, "jpg", dest)

        assert dest.exists()
        stored = Image.open(dest)
        assert dict(stored.getexif()) == {}
        assert stored.size == (24, 16)


# ─── (2) Decompression-bomb protection ─────────────────────────────────────


class TestDecompressionBombProtection:
    def test_rejects_declared_oversized_dimensions_without_full_decode(self):
        raw = _crafted_bomb_png(60_000, 60_000)  # 3.6 billion declared pixels
        assert len(raw) < 1024, "crafted file must stay tiny — no real pixel buffer"

        start = time.monotonic()
        with pytest.raises(PhotoValidationError, match="Megapixel"):
            iv._reject_oversized_or_corrupt(raw)
        elapsed = time.monotonic() - start

        # A generous bound: if this were decoding a real 3.6-billion-pixel
        # bitmap it would exhaust memory or take far longer than this, not
        # finish in well under a second.
        assert elapsed < 2.0, "rejection must come from the header, not a full decode"

    def test_rejects_dimensions_just_over_the_limit_not_only_extreme_ones(self):
        # 8000x7000 = 56,000,000 declared px: over IMAGE_MAX_MEGAPIXELS (40M)
        # but under Pillow's own hard-error tier (2x = 80M) — this only
        # trips Pillow's DecompressionBombWarning, which must still be
        # rejected as an error, not merely logged.
        raw = _crafted_bomb_png(8_000, 7_000)

        with pytest.raises(PhotoValidationError, match="Megapixel"):
            iv._reject_oversized_or_corrupt(raw)

    def test_accepts_a_small_valid_image(self):
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), "blue").save(buf, format="PNG")

        iv._reject_oversized_or_corrupt(buf.getvalue())  # must not raise

    @pytest.mark.asyncio
    async def test_read_validated_image_rejects_oversized_dimensions(self):
        raw = _crafted_bomb_png(60_000, 60_000)

        with pytest.raises(PhotoValidationError, match="Megapixel"):
            await read_validated_image(_upload(raw, "bomb.png"), max_mb=8)


# ─── (3) Non-image / corrupt content rejected ──────────────────────────────


class TestNonImageContentRejected:
    @pytest.mark.asyncio
    async def test_rejects_plain_text_with_an_image_extension(self):
        raw = b"this is definitely not an image" * 10
        upload = _upload(raw, "not-a-photo.jpg")

        with pytest.raises(PhotoValidationError, match="Dateiformat"):
            await read_validated_image(upload, max_mb=8)

    @pytest.mark.asyncio
    async def test_rejects_corrupt_content_with_forged_magic_bytes(self):
        # A real JPEG SOI marker followed by garbage — passes the
        # magic-byte sniff but must fail Pillow's structural check.
        raw = b"\xff\xd8\xff" + b"\x00" * 100
        upload = _upload(raw, "forged.jpg")

        with pytest.raises(PhotoValidationError):
            await read_validated_image(upload, max_mb=8)


# ─── Time-bounded processing (off the event loop) ──────────────────────────


class TestTimeBoundedProcessing:
    @pytest.mark.asyncio
    async def test_create_thumbnail_bounded_produces_a_thumbnail(self, tmp_path: Path):
        source = tmp_path / "photo.jpg"
        Image.new("RGB", (400, 200), "green").save(source, format="JPEG")
        thumb = tmp_path / "thumbs" / "photo.jpg"

        await create_thumbnail_bounded(source, thumb)

        assert thumb.exists()

    @pytest.mark.asyncio
    async def test_store_processed_original_raises_on_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        def _slow_strip(raw: bytes, ext: str) -> bytes:
            time.sleep(0.3)
            return raw

        monkeypatch.setattr(iv, "strip_exif_and_reencode", _slow_strip)
        monkeypatch.setattr(settings, "IMAGE_PROCESSING_TIMEOUT_SECONDS", 0.01)

        raw = _jpeg_with_gps_and_orientation()
        dest = tmp_path / "photo.jpg"

        with pytest.raises(PhotoValidationError, match="Zeitlimit"):
            await store_processed_original(raw, "jpg", dest)

        assert not dest.exists(), "a timed-out write must not leave a partial file"
