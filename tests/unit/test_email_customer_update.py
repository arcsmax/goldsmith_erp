# tests/unit/test_email_customer_update.py
"""
Unit tests for the V1.2 Task 4 EmailService / image_validation extensions.

Covers:
- send_email's new nested multipart/alternative (text/plain + text/html)
  structure inside the existing multipart/mixed envelope, with attachments
  unaffected (regression guard for the pre-existing single-part behavior).
- plain-text derivation from HTML (`_html_to_plain_text`) vs. an explicit
  `plain_body` override.
- never-raises contract preserved when the (mocked) SMTP send fails.
- the two new typed senders (`send_customer_update`, `send_cost_change`)
  render the German templates with sentinel context and forward to
  `send_email`.
- `image_validation.create_email_variant`: EXIF stripped, longest-side cap
  (no upscaling), JPEG output.
- `image_validation.create_thumbnail` regression guard: its public
  fixed-width-scale behavior must be unchanged after the shared
  convert/resize helpers were extracted for `create_email_variant`.

No existing dedicated test file mocked `aiosmtplib.send` or exercised
`create_thumbnail` directly prior to this (verified by grep across tests/) —
so this file also establishes that guard rather than merely extending one.
"""
import io

import pytest
from PIL import Image

from goldsmith_erp.core.config import settings
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.email_service import EmailService, _html_to_plain_text
from goldsmith_erp.services.image_validation import (
    THUMBNAIL_WIDTH,
    create_email_variant,
    create_thumbnail,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flip settings into 'SMTP configured' mode for the duration of a test —
    monkeypatch reverts automatically at teardown."""
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)


class _CapturingSend:
    """Stand-in for `aiosmtplib.send` — captures the built MIMEMultipart
    message instead of touching a real network socket."""

    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.sent_messages: list = []

    async def __call__(self, msg, **kwargs):
        if self.should_raise:
            raise ConnectionRefusedError("SMTP unreachable (test double)")
        self.sent_messages.append(msg)
        return None


def _make_jpeg_with_exif(path, size=(400, 300)) -> None:
    """Write a JPEG with real embedded EXIF (Make tag) using Pillow only —
    piexif is not a project dependency, so the EXIF payload is built via
    Pillow's own `Image.Exif` container."""
    img = Image.new("RGB", size, color=(200, 50, 50))
    exif = Image.Exif()
    exif[271] = "TestCam"  # 271 = Make
    img.save(path, format="JPEG", exif=exif.tobytes())


def _plain_and_html_parts(msg):
    """Extract (plain_text, html_text) from a message built by send_email."""
    alternative = msg.get_payload()[0]
    assert alternative.get_content_type() == "multipart/alternative"
    plain_part, html_part = alternative.get_payload()
    return (
        plain_part.get_payload(decode=True).decode("utf-8"),
        html_part.get_payload(decode=True).decode("utf-8"),
    )


# ---------------------------------------------------------------------------
# send_email — nested multipart/alternative structure
# ---------------------------------------------------------------------------


async def test_send_email_builds_nested_alternative_with_plain_and_html(monkeypatch):
    _enable_smtp(monkeypatch)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

    ok = await EmailService.send_email(
        to="kunde@example.com",
        subject="Test",
        html_body="<p>Hallo<br>Welt</p>",
    )

    assert ok is True
    assert len(capture.sent_messages) == 1
    msg = capture.sent_messages[0]

    assert msg.get_content_type() == "multipart/mixed"
    mixed_parts = msg.get_payload()
    assert len(mixed_parts) == 1  # no attachments in this test

    plain_text, html_text = _plain_and_html_parts(msg)
    assert "Hallo" in plain_text
    assert "Welt" in plain_text
    assert "<p>" not in plain_text
    assert html_text == "<p>Hallo<br>Welt</p>"


async def test_send_email_derives_plain_text_from_html_when_omitted(monkeypatch):
    _enable_smtp(monkeypatch)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

    await EmailService.send_email(
        to="kunde@example.com",
        subject="Test",
        html_body="<p>Zeile eins</p><p>Zeile zwei &amp; mehr</p>",
    )

    plain_text, _ = _plain_and_html_parts(capture.sent_messages[0])
    assert "Zeile eins" in plain_text
    assert "Zeile zwei & mehr" in plain_text
    assert "<p>" not in plain_text


async def test_send_email_uses_explicit_plain_body_when_provided(monkeypatch):
    _enable_smtp(monkeypatch)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

    await EmailService.send_email(
        to="kunde@example.com",
        subject="Test",
        html_body="<p>Anders als Klartext</p>",
        plain_body="Ganz eigener Klartext.",
    )

    plain_text, _ = _plain_and_html_parts(capture.sent_messages[0])
    assert plain_text == "Ganz eigener Klartext."


async def test_send_email_still_attaches_files_alongside_alternative(monkeypatch):
    """Regression guard: attachments must remain siblings of the alternative
    part inside the mixed envelope, not nested inside it."""
    _enable_smtp(monkeypatch)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

    ok = await EmailService.send_email(
        to="kunde@example.com",
        subject="Test",
        html_body="<p>Mit Anhang</p>",
        attachments=[("update.pdf", b"%PDF-1.4 fake")],
    )

    assert ok is True
    mixed_parts = capture.sent_messages[0].get_payload()
    assert len(mixed_parts) == 2
    assert mixed_parts[0].get_content_type() == "multipart/alternative"
    assert mixed_parts[1].get_filename() == "update.pdf"


async def test_send_email_never_raises_on_smtp_failure(monkeypatch):
    _enable_smtp(monkeypatch)
    capture = _CapturingSend(should_raise=True)
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

    ok = await EmailService.send_email(
        to="kunde@example.com", subject="Test", html_body="<p>x</p>"
    )
    assert ok is False


async def test_send_email_never_logs_subject_text(monkeypatch, caplog):
    """Fix round 1 (PII): with V1.2 kind=custom updates the subject is
    staff-authored free text that may carry a customer name — it must
    never appear in log records (success OR failure path). send_email
    logs subject_len instead."""
    import logging

    _enable_smtp(monkeypatch)
    sentinel = "SENTINEL_SUBJECT_Erika_Musterfrau"

    # Success path (INFO log line).
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)
    with caplog.at_level(logging.DEBUG):
        ok = await EmailService.send_email(
            to="kunde@example.com", subject=sentinel, html_body="<p>x</p>"
        )
    assert ok is True
    for record in caplog.records:
        assert sentinel not in record.getMessage()
        assert sentinel not in str(record.__dict__)
    caplog.clear()

    # Failure path (ERROR log line).
    failing = _CapturingSend(should_raise=True)
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", failing)
    with caplog.at_level(logging.DEBUG):
        ok = await EmailService.send_email(
            to="kunde@example.com", subject=sentinel, html_body="<p>x</p>"
        )
    assert ok is False
    for record in caplog.records:
        assert sentinel not in record.getMessage()
        assert sentinel not in str(record.__dict__)


def test_html_to_plain_text_strips_tags_and_unescapes_entities():
    html = "<h2>Titel</h2><p>Erste Zeile</p><p>Zweite &amp; dritte Zeile</p>"
    text = _html_to_plain_text(html)
    assert "<" not in text
    assert "Titel" in text
    assert "Erste Zeile" in text
    assert "Zweite & dritte Zeile" in text


def test_html_to_plain_text_removes_style_and_head_content():
    """Style/head ELEMENT CONTENT must be removed, not just the tags — a
    naive tag-strip leaves the raw CSS text behind."""
    html = (
        "<head><style>body { font-family: Arial; color: #333; }</style></head>"
        "<body><p>Sichtbarer Inhalt</p></body>"
    )
    text = _html_to_plain_text(html)
    assert "Sichtbarer Inhalt" in text
    assert "font-family" not in text
    assert "{" not in text


def test_real_template_plain_text_contains_no_css():
    """Regression guard (review finding): base.html carries a ~70-line
    <style> block in <head> — the derived text/plain part of EVERY outgoing
    email (all existing typed senders included) must not open with raw CSS."""
    html = EmailService._render_template(
        "customer_update.html",
        {
            "customer_name": "Erika Musterfrau",
            "body": "SENTINEL_BODY_TEXT",
            "order_ref": "Auftrag #1042",
            "photo_count": 0,
        },
    )
    assert html  # template rendered

    text = _html_to_plain_text(html)

    assert "SENTINEL_BODY_TEXT" in text
    assert "font-family" not in text
    assert "{" not in text


# ---------------------------------------------------------------------------
# Typed senders — customer_update / cost_change (template render + send)
# ---------------------------------------------------------------------------


async def test_send_customer_update_renders_template_and_sends(monkeypatch):
    _enable_smtp(monkeypatch)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

    ok = await EmailService.send_customer_update(
        to="kunde@example.com",
        subject="Update zu Ihrem Auftrag",
        customer_name="Erika Musterfrau",
        body="SENTINEL_BODY_TEXT",
        order_ref="Auftrag #1042",
        photo_count=3,
    )

    assert ok is True
    _, html_text = _plain_and_html_parts(capture.sent_messages[0])
    assert "SENTINEL_BODY_TEXT" in html_text
    assert "Auftrag #1042" in html_text
    assert "3" in html_text
    assert "Erika Musterfrau" in html_text


async def test_send_customer_update_forwards_photo_attachments(monkeypatch):
    _enable_smtp(monkeypatch)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

    ok = await EmailService.send_customer_update(
        to="kunde@example.com",
        subject="Update",
        customer_name="Erika Musterfrau",
        body="Body",
        order_ref="Auftrag #1042",
        photo_count=1,
        attachments=[("foto-1.jpg", b"\xff\xd8\xff\xe0fakejpeg")],
    )

    assert ok is True
    mixed_parts = capture.sent_messages[0].get_payload()
    assert mixed_parts[1].get_filename() == "foto-1.jpg"


async def test_send_cost_change_renders_template_with_line_items(monkeypatch):
    _enable_smtp(monkeypatch)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

    ok = await EmailService.send_cost_change(
        to="kunde@example.com",
        subject="Kostenänderung",
        customer_name="Erika Musterfrau",
        order_ref="Auftrag #1042",
        original_amount="1.200,00 €",
        new_amount="1.450,00 €",
        delta_percent="20,8 %",
        reason="SENTINEL_REASON_TEXT",
        line_items=[{"label": "Zusatzfassung", "amount": "150,00 €", "kind": "add"}],
    )

    assert ok is True
    _, html_text = _plain_and_html_parts(capture.sent_messages[0])
    assert "SENTINEL_REASON_TEXT" in html_text
    assert "1.200,00" in html_text
    assert "1.450,00" in html_text
    assert "20,8 %" in html_text
    assert "Zusatzfassung" in html_text
    assert "649" in html_text  # §649 BGB reference


async def test_send_cost_change_without_line_items_still_renders(monkeypatch):
    _enable_smtp(monkeypatch)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

    ok = await EmailService.send_cost_change(
        to="kunde@example.com",
        subject="Kostenänderung",
        customer_name="Erika Musterfrau",
        order_ref="Auftrag #1042",
        original_amount="1.200,00 €",
        new_amount="1.450,00 €",
        delta_percent="20,8 %",
        reason="Kein Einzelposten diesmal",
    )

    assert ok is True


# ---------------------------------------------------------------------------
# image_validation.create_email_variant
# ---------------------------------------------------------------------------


def test_create_email_variant_strips_exif(tmp_path):
    source = tmp_path / "with_exif.jpg"
    _make_jpeg_with_exif(source, size=(400, 300))

    # Sanity-check the fixture actually embedded EXIF before testing removal.
    with Image.open(source) as src_img:
        assert len(src_img.getexif()) > 0

    variant_bytes = create_email_variant(source)

    with Image.open(io.BytesIO(variant_bytes)) as out_img:
        assert len(out_img.getexif()) == 0


def test_create_email_variant_caps_longest_side(tmp_path):
    source = tmp_path / "large.jpg"
    Image.new("RGB", (3200, 1600), color=(10, 200, 10)).save(source, format="JPEG")

    variant_bytes = create_email_variant(source, max_px=1600)

    with Image.open(io.BytesIO(variant_bytes)) as out_img:
        assert max(out_img.size) == 1600
        assert out_img.size == (1600, 800)  # 2:1 aspect preserved


def test_create_email_variant_does_not_upscale_smaller_images(tmp_path):
    source = tmp_path / "small.jpg"
    Image.new("RGB", (400, 300), color=(10, 10, 200)).save(source, format="JPEG")

    variant_bytes = create_email_variant(source, max_px=1600)

    with Image.open(io.BytesIO(variant_bytes)) as out_img:
        assert out_img.size == (400, 300)


def test_create_email_variant_returns_nonempty_jpeg_bytes(tmp_path):
    source = tmp_path / "img.jpg"
    Image.new("RGB", (100, 100), color=(0, 0, 0)).save(source, format="JPEG")

    variant_bytes = create_email_variant(source)

    assert isinstance(variant_bytes, bytes)
    assert len(variant_bytes) > 0
    with Image.open(io.BytesIO(variant_bytes)) as out_img:
        assert out_img.format == "JPEG"


def test_create_email_variant_converts_rgba_source(tmp_path):
    """RGBA (e.g. PNG) sources must convert cleanly to JPEG-compatible RGB."""
    source = tmp_path / "rgba.png"
    Image.new("RGBA", (500, 250), color=(255, 0, 0, 128)).save(source, format="PNG")

    variant_bytes = create_email_variant(source)

    with Image.open(io.BytesIO(variant_bytes)) as out_img:
        assert out_img.mode == "RGB"
        assert out_img.format == "JPEG"


# ---------------------------------------------------------------------------
# image_validation.create_thumbnail — regression guard
# ---------------------------------------------------------------------------


def test_create_thumbnail_still_scales_to_fixed_width(tmp_path):
    """Regression guard: create_thumbnail's public behavior (fixed-width
    scale, aspect-preserving height, JPEG output, RGB conversion) must be
    unchanged after the create_email_variant refactor extracted shared
    convert/resize helpers."""
    source = tmp_path / "source.png"
    Image.new("RGBA", (800, 400), color=(255, 0, 0, 128)).save(source, format="PNG")
    thumb_path = tmp_path / "out" / "thumb.jpg"

    create_thumbnail(source, thumb_path)

    assert thumb_path.exists()
    with Image.open(thumb_path) as thumb:
        assert thumb.size == (THUMBNAIL_WIDTH, THUMBNAIL_WIDTH // 2)
        assert thumb.format == "JPEG"
        assert thumb.mode == "RGB"


def test_create_thumbnail_upscales_smaller_source(tmp_path):
    """create_thumbnail always scales to THUMBNAIL_WIDTH — unlike
    create_email_variant it upscales smaller sources too (pre-existing
    behavior, preserved as-is)."""
    source = tmp_path / "tiny.jpg"
    Image.new("RGB", (50, 50), color=(0, 255, 0)).save(source, format="JPEG")
    thumb_path = tmp_path / "thumb.jpg"

    create_thumbnail(source, thumb_path)

    with Image.open(thumb_path) as thumb:
        assert thumb.size == (THUMBNAIL_WIDTH, THUMBNAIL_WIDTH)
