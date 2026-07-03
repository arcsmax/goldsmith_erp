# src/goldsmith_erp/services/email_service.py
"""
Asynchronous email service backed by aiosmtplib.

Design contract:
- All public methods return bool (True = sent, False = skipped/failed).
- Methods NEVER raise — callers must not be disrupted by email failures.
- Email is disabled by default; enabled via EMAIL_NOTIFICATIONS_ENABLED=true
  together with a valid SMTP_HOST in settings.
- PII: recipient addresses are logged only at DEBUG level and anonymised in
  INFO/ERROR entries (first char + domain) to comply with GDPR logging rules.
"""
from __future__ import annotations

import logging
import re
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import unescape as _html_unescape
from pathlib import Path
from typing import Any, Optional

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from markupsafe import Markup, escape

from goldsmith_erp.core.config import settings

logger = logging.getLogger(__name__)

# ─── Plain-text derivation (multipart/alternative text part) ──────────────────
#
# Regex-based HTML→text conversion — NOT a general HTML→text engine. Limits
# (documented per plan Task 4):
#   - Whole <head>/<style>/<script> ELEMENTS (tags AND their content) are
#     removed first — base.html carries a ~70-line <style> block in <head>,
#     so a naive tag-strip alone would open every plain-text part with raw
#     CSS (customer-facing regression caught in review).
#   - Block-level tags are then turned into newlines before stripping so
#     paragraphs / list items / headings don't run together; every other
#     tag simply disappears (no bullet markers, no link URLs surfaced).
#   - Does not handle malformed/unclosed HTML or nested comments — safe for
#     our controlled template set but must NOT be reused on arbitrary
#     third-party HTML.
#   - Entities are unescaped via the stdlib `html` module (covers named +
#     numeric references).
#   - Consecutive blank lines collapse to at most one.
_HEAD_RE = re.compile(r"(?is)<head\b[^>]*>.*?</head\s*>")
_STYLE_RE = re.compile(r"(?is)<style\b[^>]*>.*?</style\s*>")
_SCRIPT_RE = re.compile(r"(?is)<script\b[^>]*>.*?</script\s*>")
_BLOCK_BREAK_RE = re.compile(r"(?i)<\s*(br|/p|/div|/li|/tr|/h[1-6])\s*/?\s*>")
_TAG_RE = re.compile(r"<[^>]+>")
_INLINE_WS_RE = re.compile(r"[ \t]+")


def _html_to_plain_text(html_body: str) -> str:
    """Derive a readable plain-text alternative from a rendered HTML email body."""
    # Element-content removal must run BEFORE the generic tag strip — the
    # tag strip removes <style> tags but would leave the CSS text behind.
    text = _HEAD_RE.sub("", html_body)
    text = _STYLE_RE.sub("", text)
    text = _SCRIPT_RE.sub("", text)
    text = _BLOCK_BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = _html_unescape(text)
    lines = [_INLINE_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    collapsed: list[str] = []
    for line in lines:
        if line == "" and collapsed and collapsed[-1] == "":
            continue
        collapsed.append(line)
    return "\n".join(collapsed).strip()


def _nl2br(value: Optional[str]) -> Markup:
    """
    Escape `value` for HTML, then convert newlines to ``<br>`` tags.

    Used by ``customer_update.html`` to render the goldsmith-edited free-text
    ``body`` (untrusted customer-facing content) safely while preserving her
    paragraph breaks. This is deliberately NOT the naive
    ``{{ body | e | replace('\\n', '<br>') | safe }}`` template idiom: since
    ``markupsafe.Markup.replace()`` re-escapes ITS OWN arguments (a
    well-known Jinja2 gotcha), that chain HTML-escapes the ``<br>`` we insert
    too, producing a literal ``&lt;br&gt;`` in the rendered email instead of
    a line break. Building the ``Markup("<br>\\n")`` join value in Python
    (where it is trusted, not user input) and joining already-escaped pieces
    sidesteps that trap.
    """
    if not value:
        return Markup("")
    escaped_lines = escape(value).split("\n")
    return Markup("<br>\n").join(escaped_lines)


# Jinja2 environment pointing at the email template directory.
_TEMPLATE_DIR = Path(__file__).parents[1] / "templates" / "email"
_jinja_env: Optional[Environment] = None


def _get_jinja_env() -> Environment:
    """Lazy-initialise the Jinja2 environment (avoids import-time I/O)."""
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )
        _jinja_env.filters["nl2br"] = _nl2br
    return _jinja_env


def _anonymise_email(address: str) -> str:
    """Return a privacy-safe representation: first char + domain."""
    try:
        local, domain = address.split("@", 1)
        return f"{local[0]}***@{domain}"
    except Exception:
        return "***"


class EmailService:
    """Static-method email service — all methods are safe to call fire-and-forget."""

    # ------------------------------------------------------------------
    # Template preview (dry-run / no SMTP required)
    # ------------------------------------------------------------------

    # Sample context data keyed by template stem (without .html extension).
    _PREVIEW_CONTEXTS: dict[str, dict] = {
        "order_confirmed": {
            "order_id": 1042,
            "deadline": "15.04.2026",
        },
        "repair_received": {
            "order_id": 1043,
            "description": "Goldring 750 — Stein gefasst und poliert",
            "bag_number": "T-2026-087",
        },
        "quote_sent": {
            "quote_number": "KV-2026-019",
            "total": "1.240,00 €",
            "valid_until": "30.04.2026",
        },
        "ready_for_pickup": {
            "order_id": 1044,
        },
        "pickup_complete": {
            "order_id": 1045,
        },
        "fitting_reminder": {
            "order_id": 1046,
            "date": "12.04.2026 um 14:00 Uhr",
        },
    }

    @classmethod
    def render_preview(cls, template_name: str) -> tuple[str, str]:
        """
        Render a template with sample data for admin preview.

        Parameters
        ----------
        template_name:
            Template stem without ``.html`` extension (e.g. ``order_confirmed``).

        Returns
        -------
        Tuple of (html_content, subject) where html_content is the rendered
        HTML string and subject is the email subject line for that template.

        Raises
        ------
        ValueError
            If ``template_name`` is not a recognised template.
        TemplateNotFound
            Propagated from Jinja2 if the .html file is missing.
        """
        known_templates = set(cls._PREVIEW_CONTEXTS.keys())
        if template_name not in known_templates:
            raise ValueError(
                f"Unknown template '{template_name}'. "
                f"Available: {sorted(known_templates)}"
            )
        context = cls._PREVIEW_CONTEXTS[template_name]
        html = cls._render_template(f"{template_name}.html", context)
        if not html:
            raise ValueError(
                f"Template '{template_name}.html' could not be rendered. "
                "Check the templates directory and Jinja2 syntax."
            )
        # Build a representative subject line for each template.
        subjects: dict[str, str] = {
            "order_confirmed": f"[Vorschau] Ihr Auftrag #1042 wurde bestätigt",
            "repair_received": f"[Vorschau] Ihre Reparatur #1043 wurde angenommen",
            "quote_sent": f"[Vorschau] Ihr Kostenvoranschlag KV-2026-019",
            "ready_for_pickup": f"[Vorschau] Ihr Schmuckstück ist fertig zur Abholung",
            "pickup_complete": f"[Vorschau] Vielen Dank für Ihren Auftrag #1045",
            "fitting_reminder": f"[Vorschau] Erinnerung: Ihre Anprobe am 12.04.2026",
        }
        subject = subjects.get(template_name, f"[Vorschau] {template_name}")
        return html, subject

    # ------------------------------------------------------------------
    # Core send primitive
    # ------------------------------------------------------------------

    @staticmethod
    async def send_email(
        to: str,
        subject: str,
        html_body: str,
        attachments: list[tuple[str, bytes]] | None = None,
        plain_body: Optional[str] = None,
    ) -> bool:
        """
        Send an HTML email via SMTP.

        Parameters
        ----------
        to:
            Recipient email address.
        subject:
            Email subject line.
        html_body:
            Rendered HTML string.
        attachments:
            Optional list of (filename, bytes) tuples — used for PDF invoices /
            quotes.  Each item is attached as application/octet-stream.
        plain_body:
            Optional explicit plain-text alternative. When omitted, a plain-text
            version is derived from `html_body` via `_html_to_plain_text` (a
            simple tag-strip — see that function's docstring for limits).

        Returns
        -------
        True if the message was accepted by the SMTP server, False otherwise.
        This method never raises.

        Message structure
        ------------------
        multipart/mixed
          └── multipart/alternative
                ├── text/plain  (plain_body or derived from html_body)
                └── text/html   (html_body)
          └── application/* attachments (if any)
        """
        if not settings.EMAIL_NOTIFICATIONS_ENABLED:
            logger.debug("Email notifications disabled, skipping send")
            return False

        if not settings.SMTP_HOST:
            logger.debug("SMTP_HOST not configured, skipping send")
            return False

        if not settings.SMTP_FROM:
            logger.warning("SMTP_FROM not configured — cannot send email")
            return False

        safe_to = _anonymise_email(to)

        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = settings.SMTP_FROM
            msg["To"] = to
            msg["Subject"] = subject

            alternative = MIMEMultipart("alternative")
            text = (
                plain_body if plain_body is not None else _html_to_plain_text(html_body)
            )
            alternative.attach(MIMEText(text, "plain", "utf-8"))
            alternative.attach(MIMEText(html_body, "html", "utf-8"))
            msg.attach(alternative)

            for filename, data in (attachments or []):
                part = MIMEApplication(data, Name=filename)
                part["Content-Disposition"] = f'attachment; filename="{filename}"'
                msg.attach(part)

            smtp_kwargs: dict = {
                "hostname": settings.SMTP_HOST,
                "port": settings.SMTP_PORT,
                "start_tls": settings.SMTP_PORT == 587,
                "use_tls": settings.SMTP_PORT == 465,
            }
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                smtp_kwargs["username"] = settings.SMTP_USER
                smtp_kwargs["password"] = settings.SMTP_PASSWORD

            await aiosmtplib.send(msg, **smtp_kwargs)

            logger.info(
                "Email sent",
                extra={"to": safe_to, "subject": subject},
            )
            return True

        except Exception as exc:
            logger.error(
                "Failed to send email — operation continues normally",
                extra={"to": safe_to, "subject": subject, "error": str(exc)},
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------
    # Template helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_template(template_name: str, context: dict) -> str:
        """
        Render a Jinja2 HTML template.

        Injects WORKSHOP_NAME from settings automatically.
        Returns an empty string on render failure so callers can still
        fall through gracefully.
        """
        try:
            env = _get_jinja_env()
            tmpl = env.get_template(template_name)
            return tmpl.render(
                workshop_name=settings.WORKSHOP_NAME,
                **context,
            )
        except TemplateNotFound:
            logger.error(
                "Email template not found",
                extra={"template": template_name},
            )
            return ""
        except Exception as exc:
            logger.error(
                "Email template render failed",
                extra={"template": template_name, "error": str(exc)},
                exc_info=True,
            )
            return ""

    # ------------------------------------------------------------------
    # Typed notification senders — one per business event
    # ------------------------------------------------------------------

    @staticmethod
    async def send_order_confirmed(
        to: str,
        order_id: int,
        deadline: Optional[str],
    ) -> bool:
        """Notify customer that their order has been confirmed."""
        html = EmailService._render_template(
            "order_confirmed.html",
            {"order_id": order_id, "deadline": deadline or "—"},
        )
        if not html:
            return False
        subject = f"Ihr Auftrag #{order_id} wurde bestätigt — {settings.WORKSHOP_NAME}"
        return await EmailService.send_email(to, subject, html)

    @staticmethod
    async def send_repair_received(
        to: str,
        order_id: int,
        description: str,
        bag_number: str,
    ) -> bool:
        """Notify customer that their repair item has been received."""
        html = EmailService._render_template(
            "repair_received.html",
            {"order_id": order_id, "description": description, "bag_number": bag_number},
        )
        if not html:
            return False
        subject = f"Ihre Reparatur #{order_id} wurde angenommen — {settings.WORKSHOP_NAME}"
        return await EmailService.send_email(to, subject, html)

    @staticmethod
    async def send_quote(
        to: str,
        quote_number: str,
        total: str,
        valid_until: str,
        pdf_bytes: Optional[bytes] = None,
    ) -> bool:
        """Send a price quote to the customer, optionally with a PDF attachment."""
        html = EmailService._render_template(
            "quote_sent.html",
            {"quote_number": quote_number, "total": total, "valid_until": valid_until},
        )
        if not html:
            return False
        attachments = []
        if pdf_bytes:
            attachments.append((f"Kostenvoranschlag-{quote_number}.pdf", pdf_bytes))
        subject = f"Ihr Kostenvoranschlag KV-{quote_number} — {settings.WORKSHOP_NAME}"
        return await EmailService.send_email(to, subject, html, attachments)

    @staticmethod
    async def send_ready_for_pickup(
        to: str,
        order_id: int,
    ) -> bool:
        """Notify customer that their piece is ready for pickup."""
        html = EmailService._render_template(
            "ready_for_pickup.html",
            {"order_id": order_id},
        )
        if not html:
            return False
        subject = f"Ihr Schmuckstück ist fertig zur Abholung — {settings.WORKSHOP_NAME}"
        return await EmailService.send_email(to, subject, html)

    @staticmethod
    async def send_pickup_complete(
        to: str,
        order_id: int,
        invoice_pdf_bytes: Optional[bytes] = None,
    ) -> bool:
        """Send thank-you + invoice after the customer picks up their order."""
        html = EmailService._render_template(
            "pickup_complete.html",
            {"order_id": order_id},
        )
        if not html:
            return False
        attachments = []
        if invoice_pdf_bytes:
            attachments.append((f"Rechnung-Auftrag-{order_id}.pdf", invoice_pdf_bytes))
        subject = f"Vielen Dank für Ihren Auftrag #{order_id} — {settings.WORKSHOP_NAME}"
        return await EmailService.send_email(to, subject, html, attachments)

    @staticmethod
    async def send_fitting_reminder(
        to: str,
        order_id: int,
        fitting_date: str,
    ) -> bool:
        """Remind customer of an upcoming fitting appointment."""
        html = EmailService._render_template(
            "fitting_reminder.html",
            {"order_id": order_id, "date": fitting_date},
        )
        if not html:
            return False
        subject = f"Erinnerung: Ihre Anprobe am {fitting_date} — {settings.WORKSHOP_NAME}"
        return await EmailService.send_email(to, subject, html)

    # ------------------------------------------------------------------
    # V1.2 Customer Updates & §649 BGB Cost Approval (Kundeninfo)
    # ------------------------------------------------------------------

    @staticmethod
    async def send_customer_update(
        to: str,
        subject: str,
        customer_name: str,
        body: str,
        order_ref: str,
        photo_count: int = 0,
        attachments: list[tuple[str, bytes]] | None = None,
    ) -> bool:
        """
        Send a Kundeninfo update (progress / ready-for-pickup / custom kind).

        `subject` and `body` are the goldsmith-edited, already-final text
        (CustomerUpdate.subject/body — Task 5 owns creation/editing); this
        method only renders them into the shared German template and sends.
        `attachments` should be the explicitly-selected, EXIF-stripped
        email-variant photos (see `image_validation.create_email_variant`) —
        never all order photos (design-IP rule).
        """
        html = EmailService._render_template(
            "customer_update.html",
            {
                "customer_name": customer_name,
                "body": body,
                "order_ref": order_ref,
                "photo_count": photo_count,
            },
        )
        if not html:
            return False
        return await EmailService.send_email(to, subject, html, attachments)

    @staticmethod
    async def send_cost_change(
        to: str,
        subject: str,
        customer_name: str,
        order_ref: str,
        original_amount: str,
        new_amount: str,
        delta_percent: str,
        reason: str,
        line_items: Optional[list[Any]] = None,
    ) -> bool:
        """
        Send a §649 BGB cost-change notice (Kostenänderungsanzeige).

        Amount/percent values are pre-formatted strings (e.g. "1.234,56 €",
        "18 %") — this service only renders what it is given (plan Task 4:
        "template just renders what it gets"); the caller (Task 5's
        CostChangeService) owns NET-vs-GROSS presentation decisions.
        `line_items` entries need only expose `.label` / `.amount` / `.kind`
        (attribute or mapping access both work in Jinja2).
        """
        html = EmailService._render_template(
            "cost_change.html",
            {
                "customer_name": customer_name,
                "order_ref": order_ref,
                "original_amount": original_amount,
                "new_amount": new_amount,
                "delta_percent": delta_percent,
                "reason": reason,
                "line_items": line_items or [],
            },
        )
        if not html:
            return False
        return await EmailService.send_email(to, subject, html)
