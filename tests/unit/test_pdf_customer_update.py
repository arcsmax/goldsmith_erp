# tests/unit/test_pdf_customer_update.py
"""
Unit tests for PDFService.render_customer_update_pdf (V1.2 Task 4).

`update` only needs to expose `.subject` / `.body` (see
`_render_customer_update_fpdf`'s `getattr` usage) — a `SimpleNamespace`
stand-in avoids needing a live DB session for these renderer-level tests
(consistent with there being no existing dedicated PDFService test file to
extend; verified by grep across tests/ before writing this one).
"""
import io
from types import SimpleNamespace

from PIL import Image

from goldsmith_erp.services.pdf_service import PDFService


def _make_jpeg_bytes(size=(400, 300), color=(120, 60, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_update(
    subject: str = "Fortschritts-Update", body: str = "Alles im Plan."
) -> SimpleNamespace:
    return SimpleNamespace(subject=subject, body=body)


def test_render_customer_update_pdf_returns_nonempty_bytes():
    pdf_bytes = PDFService.render_customer_update_pdf(
        update=_make_update(),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
        photos=[],
        workshop_name="Goldschmiede Test",
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")


def test_render_customer_update_pdf_contains_order_reference_and_subject():
    """
    fpdf2 renders page content through an embedded, subsetted Unicode TTF
    font — page text is glyph-index encoded, NOT ASCII-searchable in the
    output bytes (verified empirically: a raw `in` check on the content
    stream, even decompressed, does not find rendered text). The renderer
    therefore also writes `order_ref`/`subject` into the PDF's /Info
    metadata dict (`pdf.set_title` / `pdf.set_subject`), which fpdf2 stores
    as a literal, uncompressed PDF string — this is the reliable,
    dependency-free way to assert the reference string reached the output
    without adding a PDF text-extraction library.
    """
    pdf_bytes = PDFService.render_customer_update_pdf(
        update=_make_update(subject="SENTINEL_SUBJECT", body="SENTINEL_BODY_TEXT"),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
        photos=[],
        workshop_name="Goldschmiede Test",
    )
    assert b"Auftrag #1042" in pdf_bytes
    assert b"SENTINEL_SUBJECT" in pdf_bytes


def test_render_customer_update_pdf_with_no_photos_does_not_error():
    pdf_bytes = PDFService.render_customer_update_pdf(
        update=_make_update(),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
        photos=[],
        workshop_name="Goldschmiede Test",
    )
    assert len(pdf_bytes) > 0


def test_render_customer_update_pdf_embeds_photos():
    photos = [_make_jpeg_bytes(), _make_jpeg_bytes(size=(300, 600))]

    pdf_without_photos = PDFService.render_customer_update_pdf(
        update=_make_update(),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
        photos=[],
        workshop_name="Goldschmiede Test",
    )
    pdf_with_photos = PDFService.render_customer_update_pdf(
        update=_make_update(),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
        photos=photos,
        workshop_name="Goldschmiede Test",
    )

    assert len(pdf_with_photos) > len(pdf_without_photos)


def test_render_customer_update_pdf_skips_unreadable_photo_without_raising():
    """A corrupt photo entry must not abort the whole document (a bad photo
    must not block delivery of the rest of the update)."""
    photos = [b"not a real image", _make_jpeg_bytes()]

    pdf_bytes = PDFService.render_customer_update_pdf(
        update=_make_update(),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
        photos=photos,
        workshop_name="Goldschmiede Test",
    )

    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")
