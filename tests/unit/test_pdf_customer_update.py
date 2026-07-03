# tests/unit/test_pdf_customer_update.py
"""
Unit tests for PDFService.render_customer_update_pdf (V1.2 Task 4).

`update` only needs to expose `.subject` / `.body` (see
`_render_customer_update_fpdf`'s `getattr` usage) — a `SimpleNamespace`
stand-in avoids needing a live DB session for these renderer-level tests
(consistent with there being no existing dedicated PDFService test file to
extend; verified by grep across tests/ before writing this one).

Visible-content coverage: fpdf2 page streams are glyph-index encoded (not
text-searchable in the output bytes), so the document's textual content is
verified through the pure `_compose_update_pdf_lines` seam the renderer
consumes, plus /Info metadata byte checks for the reference string.
"""
import io
import re
from types import SimpleNamespace
from unittest import mock

from PIL import Image

import goldsmith_erp.services.pdf_service as pdf_service_module
from goldsmith_erp.services.pdf_service import (
    _UPDATE_BODY_MAX_CHARS,
    _UPDATE_TRUNCATION_MARKER,
    PDFService,
    _compose_update_pdf_lines,
)


def _make_jpeg_bytes(size=(400, 300), color=(120, 60, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_update(
    subject: str = "Fortschritts-Update", body: str = "Alles im Plan."
) -> SimpleNamespace:
    return SimpleNamespace(id=7, subject=subject, body=body)


def _page_count(pdf_bytes: bytes) -> int:
    """Extract the page count from fpdf2 output via the /Pages object's
    literal, uncompressed `/Count N` entry."""
    match = re.search(rb"/Count (\d+)", pdf_bytes)
    assert match is not None, "no /Count entry found in PDF output"
    return int(match.group(1))


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


def test_render_customer_update_pdf_log_carries_numeric_ids_only():
    """Review fix: order_ref may carry the order's free-text title
    (business-confidential per CLAUDE.md) — the render-start log line
    must carry numeric ids only, never order_ref.

    Uses a spy on the module logger instead of caplog: root-handler capture
    proved environment-dependent in CI (setup_logging() reconfigures the
    root logger at app import) — established pattern, see
    tests/unit/test_no_go_service.py."""
    update = SimpleNamespace(id=42, order_id=7, subject="s", body="b")

    with mock.patch.object(pdf_service_module.logger, "info") as info_spy:
        PDFService.render_customer_update_pdf(
            update=update,
            order_ref="Auftrag geheime Sonderanfertigung fuer Herrn X",
            customer_name="Erika Musterfrau",
            photos=[],
            workshop_name="Goldschmiede Test",
        )

    render_calls = [
        c
        for c in info_spy.call_args_list
        if c.args and c.args[0] == "Rendering customer update PDF"
    ]
    assert len(render_calls) == 1
    extra = render_calls[0].kwargs.get("extra", {})
    assert extra.get("update_id") == 42
    assert extra.get("order_id") == 7
    assert "order_ref" not in extra
    for c in info_spy.call_args_list:
        serialized = " ".join(str(a) for a in c.args) + " " + str(c.kwargs)
        assert "Sonderanfertigung" not in serialized


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


def test_render_customer_update_pdf_many_photos_paginate():
    """`pdf.image()` bypasses fpdf2's auto-page-break — 6 tall photos
    (~74mm each incl. margin) cannot fit one A4 page, so the grid must
    add pages instead of drawing off the bottom edge."""
    photos = [_make_jpeg_bytes(size=(300, 600)) for _ in range(6)]

    pdf_bytes = PDFService.render_customer_update_pdf(
        update=_make_update(),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
        photos=photos,
        workshop_name="Goldschmiede Test",
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert _page_count(pdf_bytes) > 1


# ---------------------------------------------------------------------------
# _compose_update_pdf_lines — visible-content seam
# ---------------------------------------------------------------------------


def test_compose_update_pdf_lines_contains_subject_body_and_reference():
    """The pure composition helper is the renderer's single source of drawn
    text — a regression dropping a draw input (e.g. the body) fails here
    even though fpdf2's glyph-encoded page streams hide it from byte checks."""
    lines = _compose_update_pdf_lines(
        _make_update(subject="SENTINEL_SUBJECT", body="SENTINEL_BODY_TEXT"),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
    )

    kinds = [kind for kind, _ in lines]
    assert kinds == ["title", "kv", "kv", "section", "body", "footer"]

    texts = [text for _, text in lines]
    assert any("SENTINEL_SUBJECT" in t for t in texts)
    assert any("SENTINEL_BODY_TEXT" in t for t in texts)
    assert any("Auftrag #1042" in t for t in texts)
    assert any("Erika Musterfrau" in t for t in texts)
    # Reference appears in the footer line too.
    assert "Auftrag #1042" in dict(zip(kinds, texts))["footer"]


def test_compose_update_pdf_lines_truncates_long_body_with_visible_marker():
    long_body = "x" * (_UPDATE_BODY_MAX_CHARS + 500)

    # Logger spy instead of caplog (env-dependent capture in CI — see above).
    with mock.patch.object(pdf_service_module.logger, "info") as info_spy:
        lines = _compose_update_pdf_lines(
            _make_update(body=long_body),
            order_ref="Auftrag #1042",
            customer_name="Erika Musterfrau",
        )

    body_text = next(text for kind, text in lines if kind == "body")
    assert body_text.endswith(_UPDATE_TRUNCATION_MARKER)
    assert len(body_text) < len(long_body)
    # Truncation is never silent — INFO log carries the update id.
    assert any(
        c.args and "truncated" in str(c.args[0]) for c in info_spy.call_args_list
    )


def test_compose_update_pdf_lines_short_body_untouched():
    lines = _compose_update_pdf_lines(
        _make_update(body="Kurzer Text."),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
    )
    body_text = next(text for kind, text in lines if kind == "body")
    assert body_text == "Kurzer Text."
    assert _UPDATE_TRUNCATION_MARKER not in body_text


def test_compose_update_pdf_lines_empty_subject_falls_back_to_update():
    lines = _compose_update_pdf_lines(
        _make_update(subject=""),
        order_ref="Auftrag #1042",
        customer_name="Erika Musterfrau",
    )
    section_text = next(text for kind, text in lines if kind == "section")
    assert section_text == "Update"
