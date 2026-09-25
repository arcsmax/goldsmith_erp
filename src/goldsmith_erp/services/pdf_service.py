# src/goldsmith_erp/services/pdf_service.py
"""
PDF generation service for invoices and scrap gold receipts.

Uses fpdf2 (pure Python, no system dependencies) as the rendering
backend and Jinja2 for HTML template rendering. The service renders
HTML to a string via Jinja2, then generates the PDF with fpdf2.

For templates: src/goldsmith_erp/templates/
  - invoice.html           → German Rechnung with MwSt line items
  - scrap_gold_receipt.html → Altgold Ankaufsbeleg with signature
"""

import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional

from fpdf import FPDF
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

logger = logging.getLogger(__name__)


def _embed_image_bytes(
    pdf: FPDF,
    img_data: bytes,
    rect: tuple[float, float, float, float],
    suffix: str = ".png",
) -> None:
    """Embed image bytes into the PDF via a secure temp file.

    fpdf2 needs a filesystem path, so the bytes are written to a
    NamedTemporaryFile (secure mkstemp-based API). The temp file is always
    removed afterwards, even if image embedding raises. ``rect`` is the
    placement box as ``(x, y, width, height)``. ``suffix`` selects the format
    fpdf2/Pillow infer from the extension (``.png`` for signatures, ``.jpg``
    for the JPEG email-variant photos used by ``render_customer_update_pdf``).
    """
    x, y, w, h = rect
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(img_data)
            tmp_path = tmp.name
        pdf.image(tmp_path, x=x, y=y, w=w, h=h)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _embed_png_signature(
    pdf: FPDF, img_data: bytes, rect: tuple[float, float, float, float]
) -> None:
    """Embed a PNG signature into the PDF via a secure temp file.

    Thin wrapper around ``_embed_image_bytes`` (kept as a distinct, named
    function since every existing call site already refers to it by this
    name) — see that function's docstring for the temp-file mechanics.
    """
    _embed_image_bytes(pdf, img_data, rect, suffix=".png")


# Path to Jinja2 templates directory
_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Path to bundled TTF fonts (DejaVu — public domain, full Unicode support)
_FONTS_DIR = Path(__file__).parent.parent / "fonts"
_FONT_REGULAR = str(_FONTS_DIR / "DejaVuSans.ttf")
_FONT_BOLD = str(_FONTS_DIR / "DejaVuSans-Bold.ttf")

# Font family names used throughout the service
_FONT = "DejaVu"  # regular weight
_FONT_B = "DejaVuBold"  # bold weight


def _get_jinja_env() -> Environment:
    """Return a configured Jinja2 environment pointing at the templates dir."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def _html_to_pdf_bytes(html_content: str, title: str = "Dokument") -> bytes:
    """
    Convert rendered HTML content to PDF bytes using fpdf2.

    fpdf2 does not do full HTML rendering — we extract the meaningful
    content and format it with FPDF's layout primitives. This keeps the
    output clean and avoids system-level dependencies (like libcairo).

    For production-grade HTML rendering, replace this function body with
    a WeasyPrint call once its system dependencies are available:

        from weasyprint import HTML
        return HTML(string=html_content).write_pdf()
    """
    # This function is the seam where WeasyPrint can be plugged in later.
    # Currently unused — callers use _render_invoice_fpdf / _render_scrap_gold_fpdf
    # which produce the PDF directly without going through HTML.
    raise NotImplementedError(
        "_html_to_pdf_bytes is a WeasyPrint stub. "
        "Use the dedicated FPDF render functions instead."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Internal FPDF helpers
# ─────────────────────────────────────────────────────────────────────────────

_GOLD = (139, 105, 20)  # RGB for #8B6914
_DARK = (34, 34, 34)  # Near-black
_GRAY = (120, 120, 120)
_LIGHT_GOLD_BG = (249, 245, 236)  # #F9F5EC


class _GoldsmithPDF(FPDF):
    """Base FPDF subclass with common layout helpers."""

    def __init__(self, workshop_name: str, footer_text: str = ""):
        super().__init__(unit="mm", format="A4")
        self._workshop_name = workshop_name
        self._footer_text = footer_text
        # Register bundled Unicode fonts (DejaVu — covers €, ä, ö, ü, etc.)
        self.add_font(_FONT, fname=_FONT_REGULAR)
        self.add_font(_FONT_B, fname=_FONT_BOLD)
        self.set_auto_page_break(auto=True, margin=25)
        self.add_page()

    def header(self) -> None:
        # Intentionally blank — header content is drawn inline per document type.
        pass

    def footer(self) -> None:
        self.set_y(-20)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)
        self.set_font(_FONT, "", 7)
        self.set_text_color(*_GRAY)
        text = self._footer_text or self._workshop_name
        self.cell(0, 4, text, align="C")
        self.set_text_color(*_DARK)

    # ---- Convenience drawing helpers ----------------------------------------

    def gold_rule(self, y: Optional[float] = None, thickness: float = 0.5) -> None:
        """Draw a gold horizontal rule at `y` (default: current position)."""
        _y = y if y is not None else self.get_y()
        self.set_draw_color(*_GOLD)
        self.set_line_width(thickness)
        self.line(10, _y, 200, _y)
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.2)

    def section_title(self, text: str) -> None:
        """Render a small uppercase gold section label."""
        self.set_font(_FONT_B, "", 7.5)
        self.set_text_color(*_GOLD)
        self.cell(0, 5, text.upper(), ln=True)
        self.gold_rule(thickness=0.3)
        self.ln(2)
        self.set_text_color(*_DARK)

    def kv_row(self, label: str, value: str, label_w: float = 55) -> None:
        """Print a label: value row in the current font."""
        self.set_font(_FONT, "", 9)
        self.set_text_color(*_GRAY)
        self.cell(label_w, 5, label)
        self.set_text_color(*_DARK)
        self.set_font(_FONT_B, "", 9)
        self.cell(0, 5, value, ln=True)
        self.set_font(_FONT, "", 9)

    def filled_header_row(self, cols: list[tuple[str, float, str]]) -> None:
        """
        Draw a gold-filled table header row.

        cols: list of (label, width_mm, align)  where align is 'L', 'C', 'R'
        """
        self.set_fill_color(*_GOLD)
        self.set_text_color(255, 255, 255)
        self.set_font(_FONT_B, "", 8.5)
        row_h = 6
        for label, w, align in cols:
            self.cell(w, row_h, label, border=0, align=align, fill=True)
        self.ln(row_h)
        self.set_text_color(*_DARK)
        self.set_fill_color(255, 255, 255)

    def table_data_row(
        self,
        cols: list[tuple[str, float, str]],
        even: bool = False,
    ) -> None:
        """Draw a data row; alternating rows get a light gold background."""
        self.set_fill_color(*(_LIGHT_GOLD_BG if even else (255, 255, 255)))
        self.set_font(_FONT, "", 9.5)
        row_h = 6
        for text, w, align in cols:
            self.cell(w, row_h, text, border=0, align=align, fill=True)
        self.ln(row_h)
        self.set_fill_color(255, 255, 255)


# ─────────────────────────────────────────────────────────────────────────────
# Invoice renderer
# ─────────────────────────────────────────────────────────────────────────────


KLEINUNTERNEHMER_NOTE = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."
_HOME_COUNTRY = "Deutschland"


def _paragraph(pdf: "_GoldsmithPDF", text: str) -> None:
    """Full-width wrapped text that returns to the left margin afterwards."""
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 4.5, text, new_x="LMARGIN", new_y="NEXT")


def _fmt_rate(rate: Any) -> str:
    """VAT rate as German percent label: 19 -> '19 %', 7.5 -> '7,5 %'."""
    try:
        value = float(rate)
    except (TypeError, ValueError):
        return "0 %"
    if value == int(value):
        return f"{int(value)} %"
    return f"{value:.1f}".replace(".", ",") + " %"


def _place(postal_code: Any, city: Any) -> str:
    return " ".join(part for part in (_safe_str(postal_code), _safe_str(city)) if part)


def _seller_address_lines(seller: Mapping[str, Any]) -> list[str]:
    """§14 Abs. 4 Nr. 1 UStG: the seller's full name and address."""
    lines = []
    if seller.get("owner_name"):
        lines.append(f"Inhaber/in: {seller['owner_name']}")
    lines.append(_safe_str(seller.get("street")))
    lines.append(_place(seller.get("postal_code"), seller.get("city")))
    country = _safe_str(seller.get("country"))
    if country and country != _HOME_COUNTRY:
        lines.append(country)
    if seller.get("phone"):
        lines.append(f"Tel. {seller['phone']}")
    if seller.get("email"):
        lines.append(_safe_str(seller.get("email")))
    if not seller.get("street") and seller.get("contact"):
        lines.append(_safe_str(seller.get("contact")))
    return [line for line in lines if line]


def _seller_tax_lines(seller: Mapping[str, Any]) -> list[str]:
    """§14 Abs. 4 Nr. 2 UStG: Steuernummer or USt-IdNr. (both if set)."""
    lines = []
    if seller.get("tax_number"):
        lines.append(f"Steuernummer: {seller['tax_number']}")
    if seller.get("vat_id"):
        lines.append(f"USt-IdNr.: {seller['vat_id']}")
    return lines


def _recipient_lines(customer: Any) -> list[str]:
    lines = [
        _safe_str(getattr(customer, "company_name", None)),
        _safe_str(getattr(customer, "address", None)),
        _safe_str(getattr(customer, "city", None)),
    ]
    country = _safe_str(getattr(customer, "country", None))
    if country and country != _HOME_COUNTRY:
        lines.append(country)
    return [line for line in lines if line]


def _is_storno(invoice: Any) -> bool:
    return bool(getattr(invoice, "cancels_invoice_number", None))


def _draw_invoice_header(
    pdf: "_GoldsmithPDF", invoice: Any, workshop_name: str
) -> None:
    pdf.set_font(_FONT_B, "", 18)
    pdf.set_text_color(*_GOLD)
    pdf.cell(110, 10, workshop_name)
    pdf.set_font(_FONT_B, "", 20)
    pdf.set_text_color(60, 60, 60)
    title = "STORNORECHNUNG" if _is_storno(invoice) else "RECHNUNG"
    pdf.cell(0, 10, title, align="R", ln=True)
    pdf.set_font(_FONT_B, "", 10)
    pdf.set_text_color(*_GOLD)
    pdf.cell(0, 5, invoice.invoice_number, align="R", ln=True)
    pdf.set_text_color(*_DARK)
    pdf.gold_rule()
    pdf.ln(4)


def _draw_column(
    pdf: "_GoldsmithPDF", x: float, label: str, name: str, lines: list[str]
) -> None:
    pdf.set_x(x)
    pdf.set_font(_FONT_B, "", 7)
    pdf.set_text_color(*_GRAY)
    pdf.cell(90, 4, label, ln=True)
    pdf.set_text_color(*_DARK)
    pdf.set_x(x)
    pdf.set_font(_FONT_B, "", 10)
    pdf.cell(90, 5, name, ln=True)
    pdf.set_font(_FONT, "", 9)
    for line in lines:
        pdf.set_x(x)
        pdf.cell(90, 4.5, line, ln=True)


def _draw_address_block(
    pdf: "_GoldsmithPDF",
    seller: Mapping[str, Any],
    customer: Any,
    workshop_name: str,
) -> None:
    x_left = pdf.get_x()
    y_top = pdf.get_y()
    seller_lines = _seller_address_lines(seller) + _seller_tax_lines(seller)
    _draw_column(pdf, x_left, "RECHNUNGSSTELLER", workshop_name, seller_lines)
    y_seller_end = pdf.get_y()
    pdf.set_xy(x_left + 100, y_top)
    customer_name = _safe_str(getattr(customer, "name", "")) or "Kunde"
    _draw_column(
        pdf,
        x_left + 100,
        "RECHNUNGSEMPFÄNGER",
        customer_name,
        _recipient_lines(customer),
    )
    pdf.set_xy(x_left, max(pdf.get_y(), y_seller_end, y_top + 28))
    pdf.ln(4)


def _invoice_meta_rows(invoice: Any) -> list[tuple[str, str]]:
    service_date = getattr(invoice, "service_date", None) or invoice.issue_date
    rows = [
        ("Rechnungsnummer:", invoice.invoice_number),
        ("Rechnungsdatum:", _fmt_date(invoice.issue_date)),
        ("Leistungsdatum:", _fmt_date(service_date)),
    ]
    if not _is_storno(invoice):
        rows.append(("Fälligkeitsdatum:", _fmt_date(invoice.due_date)))
    rows.append(("Auftragsnummer:", str(invoice.order_id)))
    if getattr(invoice, "payment_method", None):
        rows.append(("Zahlungsart:", str(invoice.payment_method)))
    return rows


def _draw_invoice_meta(pdf: "_GoldsmithPDF", invoice: Any) -> None:
    if _is_storno(invoice):
        original_date = _fmt_date(getattr(invoice, "cancels_invoice_date", None))
        text = f"Storno zur Rechnung {invoice.cancels_invoice_number}"
        if original_date:
            text += f" vom {original_date}"
        pdf.set_font(_FONT_B, "", 10)
        pdf.cell(0, 6, text, ln=True)
        reason = _safe_str(getattr(invoice, "storno_reason", None))
        if reason:
            pdf.set_font(_FONT, "", 9)
            _paragraph(pdf, f"Grund: {reason[:300]}")
        pdf.ln(2)
    for label, value in _invoice_meta_rows(invoice):
        pdf.set_font(_FONT, "", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(155, 4.5, label, align="R")
        pdf.set_text_color(*_DARK)
        pdf.set_font(_FONT_B, "", 9)
        pdf.cell(0, 4.5, value, align="R", ln=True)
    pdf.ln(5)


def _draw_line_items(pdf: "_GoldsmithPDF", line_items: list[Any]) -> None:
    """§14 Abs. 4 Nr. 5 UStG: quantity and kind of each delivery/service."""
    widths = (12, 78, 18, 36, 34)
    pdf.filled_header_row(
        [
            ("Pos.", widths[0], "C"),
            ("Beschreibung", widths[1], "L"),
            ("Menge", widths[2], "R"),
            ("Einzelpreis netto", widths[3], "R"),
            ("Gesamt netto", widths[4], "R"),
        ]
    )
    for i, item in enumerate(line_items):
        pdf.table_data_row(
            [
                (str(i + 1), widths[0], "C"),
                (_safe_str(item.description)[:65], widths[1], "L"),
                (_fmt_num(item.quantity), widths[2], "R"),
                (_fmt_eur(item.unit_price), widths[3], "R"),
                (_fmt_eur(item.total), widths[4], "R"),
            ],
            even=i % 2 == 0,
        )
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(4)


def _total_row(
    pdf: "_GoldsmithPDF", label: str, value: str, highlight: bool = False
) -> None:
    if highlight:
        pdf.set_fill_color(*_GOLD)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(_FONT_B, "", 11)
    else:
        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(*_GRAY)
        pdf.set_font(_FONT, "", 9)
    pdf.cell(140, 6, label, fill=highlight)
    pdf.cell(38, 6, value, align="R", fill=highlight, ln=True)
    pdf.set_text_color(*_DARK)
    pdf.set_fill_color(255, 255, 255)


def _draw_invoice_totals(
    pdf: "_GoldsmithPDF", invoice: Any, is_kleinunternehmer: bool, altgold_credit: float
) -> None:
    """§14 Abs. 4 Nr. 7/8 UStG: net per rate, rate, VAT amount, gross."""
    if is_kleinunternehmer:
        _total_row(pdf, "Gesamtbetrag:", _fmt_eur(invoice.total), highlight=True)
        pdf.set_font(_FONT, "", 9)
        _paragraph(pdf, KLEINUNTERNEHMER_NOTE)
    else:
        rate = _fmt_rate(invoice.tax_rate)
        _total_row(pdf, f"Nettobetrag {rate}:", _fmt_eur(invoice.subtotal))
        _total_row(pdf, f"Umsatzsteuer {rate}:", _fmt_eur(invoice.tax_amount))
        _total_row(
            pdf, "Gesamtbetrag (brutto):", _fmt_eur(invoice.total), highlight=True
        )
    if altgold_credit > 0:
        # Post-tax deduction (ADR 2026-09-25, BE-03): not part of the VAT base.
        amount_due = float(invoice.total) - altgold_credit
        _total_row(pdf, "abzüglich Gutschrift Altgold:", f"–{_fmt_eur(altgold_credit)}")
        _total_row(pdf, "Zahlbetrag:", _fmt_eur(amount_due))
    pdf.ln(4)


def _draw_invoice_notes(pdf: "_GoldsmithPDF", notes: str) -> None:
    pdf.set_fill_color(*_LIGHT_GOLD_BG)
    pdf.set_draw_color(*_GOLD)
    pdf.set_line_width(0.5)
    pdf.rect(10, pdf.get_y(), 2, 14, style="F")
    pdf.set_x(15)
    pdf.set_font(_FONT_B, "", 7.5)
    pdf.set_text_color(*_GOLD)
    pdf.cell(0, 5, "HINWEISE", ln=True)
    pdf.set_x(15)
    pdf.set_font(_FONT, "", 9)
    pdf.set_text_color(*_DARK)
    pdf.multi_cell(175, 4.5, notes[:400])
    pdf.ln(2)


def _draw_gemstones(pdf: "_GoldsmithPDF", gemstones: Optional[list[Any]]) -> None:
    """W2-06 (DOM-04): the stones of the piece, one German line each.

    Description only (type, count, ct, colour/clarity, shape, Fassungsart,
    Kundenstein); never the purchase cost, which is internal data.
    """
    if not gemstones:
        return
    from goldsmith_erp.models.gemstone import describe_gemstone  # noqa: PLC0415

    pdf.ln(2)
    pdf.section_title("Steine")
    pdf.set_font(_FONT, "", 9)
    pdf.set_text_color(*_DARK)
    for stone in gemstones:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            pdf.w - pdf.l_margin - pdf.r_margin,
            4.5,
            f"• {describe_gemstone(stone)}"[:300],
        )
    pdf.ln(2)


def _bank_line(seller: Mapping[str, Any]) -> str:
    parts = [
        _safe_str(seller.get("bank_name")),
        f"IBAN {seller['iban']}" if seller.get("iban") else "",
        f"BIC {seller['bic']}" if seller.get("bic") else "",
    ]
    text = ", ".join(part for part in parts if part)
    return f"Bankverbindung: {text}" if seller.get("iban") else ""


def _draw_payment_block(
    pdf: "_GoldsmithPDF",
    invoice: Any,
    seller: Mapping[str, Any],
    altgold_credit: float,
) -> None:
    pdf.set_font(_FONT, "", 9)
    pdf.set_text_color(*_GRAY)
    amount_due = float(invoice.total) - altgold_credit
    if _is_storno(invoice):
        _paragraph(
            pdf,
            f"Diese Stornorechnung hebt die Rechnung {invoice.cancels_invoice_number} "
            "auf. Bereits gezahlte Beträge werden erstattet.",
        )
    elif amount_due > 0:
        _paragraph(
            pdf,
            f"Bitte überweisen Sie den Betrag von {_fmt_eur(amount_due)} "
            f"bis zum {_fmt_date(invoice.due_date)}. "
            f"Verwendungszweck: {invoice.invoice_number}",
        )
    bank = _bank_line(seller)
    if bank:
        _paragraph(pdf, bank)
    footer = _safe_str(seller.get("invoice_footer"))
    if footer:
        pdf.ln(2)
        _paragraph(pdf, footer[:1000])
    pdf.set_text_color(*_DARK)


def _render_invoice_fpdf(
    invoice: Any,
    customer: Any,
    line_items: list[Any],
    workshop_name: str,
    altgold_credit: float = 0.0,
    seller: Optional[Mapping[str, Any]] = None,
    gemstones: Optional[list[Any]] = None,
) -> bytes:
    """Build a §14 Abs. 4 UStG complete invoice PDF with fpdf2 (W2-04)."""
    seller_data: Mapping[str, Any] = seller or {"name": workshop_name}
    kind = "Stornorechnung" if _is_storno(invoice) else "Rechnung"
    footer_text = f"{workshop_name}  |  {kind} {invoice.invoice_number}"
    pdf = _GoldsmithPDF(workshop_name=workshop_name, footer_text=footer_text)

    _draw_invoice_header(pdf, invoice, workshop_name)
    _draw_address_block(pdf, seller_data, customer, workshop_name)
    _draw_invoice_meta(pdf, invoice)
    _draw_line_items(pdf, line_items)
    _draw_invoice_totals(
        pdf,
        invoice,
        bool(seller_data.get("is_kleinunternehmer")),
        max(float(altgold_credit or 0.0), 0.0),
    )
    notes = _safe_str(getattr(invoice, "notes", None))
    if notes:
        _draw_invoice_notes(pdf, notes)
    _draw_gemstones(pdf, gemstones)
    _draw_payment_block(
        pdf, invoice, seller_data, max(float(altgold_credit or 0.0), 0.0)
    )
    return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────────────────────
# Scrap gold receipt renderer
# ─────────────────────────────────────────────────────────────────────────────


def _render_scrap_gold_fpdf(
    scrap_gold: Any,
    items: list[Any],
    customer: Any,
    workshop_name: str,
    signature_base64: Optional[str] = None,
) -> bytes:
    """Build a scrap gold Ankaufsbeleg PDF with fpdf2 and return raw bytes."""
    import base64
    import io

    receipt_nr = f"AG-{scrap_gold.id:05d}"
    footer_text = (
        f"{workshop_name}  |  Ankaufsbeleg {receipt_nr}  |  "
        f"{_fmt_date(scrap_gold.created_at)}"
    )
    pdf = _GoldsmithPDF(workshop_name=workshop_name, footer_text=footer_text)

    # ── Header ────────────────────────────────────────────────────────────────
    pdf.set_font(_FONT_B, "", 16)
    pdf.set_text_color(*_GOLD)
    pdf.cell(0, 9, workshop_name, align="C", ln=True)
    pdf.set_font(_FONT_B, "", 20)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 10, "ANKAUFSBELEG", align="C", ln=True)
    pdf.set_font(_FONT, "", 8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(
        0,
        5,
        f"Datum: {_fmt_date(scrap_gold.created_at)}     Beleg-Nr.: {receipt_nr}",
        align="C",
        ln=True,
    )
    pdf.set_text_color(*_DARK)
    pdf.gold_rule()
    pdf.ln(4)

    # ── Parties ───────────────────────────────────────────────────────────────
    # Light-gold background box spanning full width
    party_y = pdf.get_y()
    pdf.set_fill_color(*_LIGHT_GOLD_BG)
    pdf.rect(10, party_y, 190, 26, style="F")

    pdf.set_xy(13, party_y + 2)
    pdf.set_font(_FONT_B, "", 7)
    pdf.set_text_color(*_GOLD)
    pdf.cell(88, 4, "ANKÄUFER")
    pdf.set_x(103)
    pdf.cell(88, 4, "VERKÄUFER (KUNDE)", ln=True)

    pdf.set_xy(13, party_y + 7)
    pdf.set_font(_FONT_B, "", 10)
    pdf.set_text_color(*_DARK)
    pdf.cell(88, 5, workshop_name)
    customer_name = _safe_str(getattr(customer, "name", "Kunde"))
    pdf.set_x(103)
    pdf.cell(88, 5, customer_name, ln=True)

    pdf.set_font(_FONT, "", 8.5)
    pdf.set_text_color(*_GRAY)

    for attr in ("address", "city", "phone"):
        val = _safe_str(getattr(customer, attr, None))
        if val:
            pdf.set_x(103)
            pdf.cell(88, 4, val, ln=True)

    pdf.set_y(party_y + 28)
    pdf.set_text_color(*_DARK)
    pdf.ln(3)

    # ── Items table ───────────────────────────────────────────────────────────
    pdf.section_title("Positionen – Abgegebenes Altgold")

    col_desc = 75
    col_alloy = 30
    col_weight = 40
    col_fine = 43

    pdf.filled_header_row(
        [
            ("Beschreibung", col_desc, "L"),
            ("Legierung", col_alloy, "C"),
            ("Gewicht (g)", col_weight, "R"),
            ("Feingehalt (g)", col_fine, "R"),
        ]
    )

    for i, item in enumerate(items):
        even = i % 2 == 0
        pdf.table_data_row(
            [
                (_safe_str(item.description)[:45], col_desc, "L"),
                (_safe_str(item.alloy), col_alloy, "C"),
                (f"{item.weight_g:.3f}", col_weight, "R"),
                (f"{item.fine_content_g:.3f}", col_fine, "R"),
            ],
            even=even,
        )

    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(3)

    # ── Summary ───────────────────────────────────────────────────────────────
    label_w = 140
    value_w = 38

    def _sum_row(label: str, value: str, gold_bg: bool = False) -> None:
        if gold_bg:
            pdf.set_fill_color(*_GOLD)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(_FONT_B, "", 11)
        else:
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(*_GRAY)
            pdf.set_font(_FONT, "", 9)
        pdf.cell(label_w, 6, label, fill=gold_bg)
        pdf.cell(value_w, 6, value, align="R", fill=gold_bg, ln=True)
        pdf.set_text_color(*_DARK)
        pdf.set_fill_color(255, 255, 255)

    _sum_row(
        "Gesamt-Feingold:",
        f"{scrap_gold.total_fine_gold_g:.3f} g",
    )
    if getattr(scrap_gold, "gold_price_per_g", None):
        _sum_row(
            "Goldpreis/g:",
            _fmt_eur(scrap_gold.gold_price_per_g),
        )
    _sum_row("Gesamtwert:", _fmt_eur(scrap_gold.total_value_eur), gold_bg=True)
    pdf.ln(6)

    # ── Signature ─────────────────────────────────────────────────────────────
    pdf.section_title("Unterschrift")

    sig_y = pdf.get_y()
    col_w = 88
    line_h = 22

    # Customer signature (left box)
    if signature_base64:
        try:
            img_data = base64.b64decode(signature_base64)
            _embed_png_signature(pdf, img_data, (12, sig_y, col_w - 4, line_h - 2))
        except Exception:
            logger.warning("Could not embed signature image into PDF", exc_info=True)

    # Signature lines
    pdf.set_draw_color(80, 80, 80)
    pdf.set_line_width(0.4)
    pdf.line(10, sig_y + line_h, 10 + col_w, sig_y + line_h)
    pdf.line(10 + col_w + 10, sig_y + line_h, 200, sig_y + line_h)
    pdf.set_line_width(0.2)

    pdf.set_y(sig_y + line_h + 1)
    pdf.set_font(_FONT, "", 7.5)
    pdf.set_text_color(*_GRAY)
    pdf.cell(col_w + 10, 4, "Unterschrift Verkäufer / Kunde", align="C")
    pdf.cell(0, 4, "Unterschrift Goldschmiede / Ankäufer", align="C", ln=True)
    pdf.set_text_color(*_DARK)
    pdf.ln(5)

    # ── Legal text ────────────────────────────────────────────────────────────
    legal = (
        "Der Kunde bestätigt die Abgabe des oben genannten Altgolds und die Richtigkeit der "
        "angegebenen Gewichte und Legierungen. Der Kaufpreis wurde vollständig ausgezahlt. "
        "Der Kunde versichert, rechtmäßiger Eigentümer der übergebenen Gegenstände zu sein "
        f"und diese unbeschränkt veräußern zu dürfen. Aufbewahrungs- und Identifizierungspflichten "
        f"gemäß GwG wurden erfüllt. Dieser Beleg wird gemäß gesetzlicher Aufbewahrungspflicht "
        f"für 10 Jahre archiviert."
    )

    pdf.set_fill_color(245, 245, 245)
    legal_y = pdf.get_y()
    pdf.rect(10, legal_y, 190, 22, style="F")
    pdf.set_xy(13, legal_y + 2)
    pdf.set_font(_FONT_B, "", 7.5)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 4, "RECHTLICHER HINWEIS", ln=True)
    pdf.set_x(13)
    pdf.set_font(_FONT, "", 7.5)
    pdf.multi_cell(184, 3.8, legal)
    pdf.set_text_color(*_DARK)

    return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────


def _fmt_date(dt: Any) -> str:
    """Format a datetime as German dd.mm.YYYY."""
    if dt is None:
        return ""
    try:
        return dt.strftime("%d.%m.%Y")
    except AttributeError:
        return str(dt)


def _fmt_eur(value: Any) -> str:
    """Format a float as German currency string, e.g. '1.234,56 €'."""
    try:
        f = float(value)
        # German locale: thousands separator = '.', decimal = ','
        formatted = f"{f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{formatted} \u20ac"
    except (TypeError, ValueError):
        return "0,00 \u20ac"


def _fmt_num(value: Any) -> str:
    """Format a quantity float, stripping trailing zeros."""
    try:
        f = float(value)
        if f == int(f):
            return str(int(f))
        return f"{f:.2f}"
    except (TypeError, ValueError):
        return str(value)


def _safe_str(value: Any) -> str:
    """Return str(value) or empty string for None."""
    if value is None:
        return ""
    return str(value)


# ─────────────────────────────────────────────────────────────────────────────
# Quote renderer (Kostenvoranschlag)
# ─────────────────────────────────────────────────────────────────────────────


def _render_quote_fpdf(
    quote: Any,
    customer: Any,
    line_items: list[Any],
    workshop_name: str,
    gemstones: Optional[list[Any]] = None,
) -> bytes:
    """Build a Kostenvoranschlag PDF with fpdf2 and return raw bytes."""
    import base64

    footer_text = f"{workshop_name}  |  Kostenvoranschlag {quote.quote_number}"
    pdf = _GoldsmithPDF(workshop_name=workshop_name, footer_text=footer_text)

    # ── Page top: workshop name + KOSTENVORANSCHLAG title ─────────────────────
    pdf.set_font(_FONT_B, "", 18)
    pdf.set_text_color(*_GOLD)
    pdf.cell(110, 10, workshop_name)

    pdf.set_font(_FONT_B, "", 18)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 10, "KOSTENVORANSCHLAG", align="R", ln=True)

    pdf.set_font(_FONT, "", 8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(110, 5, "Goldschmiede & Atelier")
    pdf.set_font(_FONT_B, "", 10)
    pdf.set_text_color(*_GOLD)
    pdf.cell(0, 5, quote.quote_number, align="R", ln=True)
    pdf.set_text_color(*_DARK)

    pdf.gold_rule()
    pdf.ln(4)

    # ── Address columns ───────────────────────────────────────────────────────
    x_left = pdf.get_x()
    y_addr = pdf.get_y()

    # Left column: workshop (Aussteller)
    pdf.set_xy(x_left, y_addr)
    pdf.set_font(_FONT_B, "", 7)
    pdf.set_text_color(*_GRAY)
    pdf.cell(90, 4, "ANBIETER", ln=True)
    pdf.set_text_color(*_DARK)
    pdf.set_font(_FONT_B, "", 10)
    pdf.cell(90, 5, workshop_name, ln=True)
    pdf.set_font(_FONT, "", 9)

    # Right column: customer (Empfaenger)
    pdf.set_xy(x_left + 100, y_addr)
    pdf.set_font(_FONT_B, "", 7)
    pdf.set_text_color(*_GRAY)
    pdf.cell(90, 4, "AUFTRAGGEBER", ln=True)
    cust_y = pdf.get_y()
    pdf.set_xy(x_left + 100, cust_y)
    pdf.set_text_color(*_DARK)

    customer_name = _safe_str(getattr(customer, "name", "Kunde"))
    pdf.set_font(_FONT_B, "", 10)
    pdf.cell(90, 5, customer_name, ln=True)
    pdf.set_xy(x_left + 100, pdf.get_y())
    pdf.set_font(_FONT, "", 9)

    for attr in ("address", "city", "email", "phone"):
        val = _safe_str(getattr(customer, attr, None))
        if val:
            pdf.set_xy(x_left + 100, pdf.get_y())
            pdf.cell(90, 4.5, val, ln=True)

    pdf.set_y(max(pdf.get_y(), y_addr + 28))
    pdf.ln(4)

    # ── Quote meta (right-aligned) ────────────────────────────────────────────
    meta: list[tuple[str, str]] = [
        ("KV-Datum:", _fmt_date(quote.created_at)),
        ("Gueltig bis:", _fmt_date(quote.valid_until)),
    ]
    if getattr(quote, "order_id", None):
        meta.append(("Auftragsnummer:", str(quote.order_id)))

    for label, value in meta:
        pdf.set_font(_FONT, "", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(155, 4.5, label, align="R")
        pdf.set_text_color(*_DARK)
        pdf.set_font(_FONT_B, "", 9)
        pdf.cell(0, 4.5, value, align="R", ln=True)

    pdf.ln(5)

    # ── Line items table ──────────────────────────────────────────────────────
    col_pos = 12
    col_desc = 88
    col_qty = 22
    col_unit = 28
    col_total = 28

    pdf.filled_header_row(
        [
            ("Pos.", col_pos, "C"),
            ("Beschreibung", col_desc, "L"),
            ("Menge", col_qty, "R"),
            ("Einzelpreis", col_unit, "R"),
            ("Gesamtpreis", col_total, "R"),
        ]
    )

    for i, item in enumerate(line_items):
        even = i % 2 == 0
        pdf.table_data_row(
            [
                (str(i + 1), col_pos, "C"),
                (_safe_str(item.description)[:65], col_desc, "L"),
                (_fmt_num(item.quantity), col_qty, "R"),
                (_fmt_eur(item.unit_price), col_unit, "R"),
                (_fmt_eur(item.total), col_total, "R"),
            ],
            even=even,
        )

    # Divider below table
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(4)

    # ── Totals ────────────────────────────────────────────────────────────────
    label_w = 140
    value_w = 38

    def _total_row(
        label: str, value: str, bold: bool = False, gold_bg: bool = False
    ) -> None:
        if gold_bg:
            pdf.set_fill_color(*_GOLD)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(_FONT_B, "", 11)
        else:
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(*(_DARK if bold else _GRAY))
            pdf.set_font(_FONT_B if bold else _FONT, "", 9)
        pdf.cell(label_w, 6, label, fill=gold_bg)
        pdf.cell(value_w, 6, value, align="R", fill=gold_bg, ln=True)
        pdf.set_text_color(*_DARK)
        pdf.set_fill_color(255, 255, 255)

    _total_row("Zwischensumme (netto):", _fmt_eur(quote.subtotal))
    _total_row(f"MwSt {quote.tax_rate:.0f}%:", _fmt_eur(quote.tax_amount))
    _total_row("Gesamtbetrag:", _fmt_eur(quote.total), gold_bg=True)
    pdf.ln(4)

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = _safe_str(getattr(quote, "notes", None))
    if notes:
        pdf.set_fill_color(*_LIGHT_GOLD_BG)
        pdf.set_draw_color(*_GOLD)
        pdf.set_line_width(0.5)
        y_note = pdf.get_y()
        pdf.rect(10, y_note, 2, 14, style="F")
        pdf.set_x(15)
        pdf.set_font(_FONT_B, "", 7.5)
        pdf.set_text_color(*_GOLD)
        pdf.cell(0, 5, "HINWEISE", ln=True)
        pdf.set_x(15)
        pdf.set_font(_FONT, "", 9)
        pdf.set_text_color(*_DARK)
        pdf.multi_cell(175, 4.5, notes[:400])
        pdf.ln(2)

    _draw_gemstones(pdf, gemstones)

    # ── Signature line ────────────────────────────────────────────────────────
    pdf.ln(6)
    pdf.section_title("Unterschrift")

    sig_y = pdf.get_y()
    col_w = 88

    # If approved signature exists, embed it
    sig_data = _safe_str(getattr(quote, "customer_signature_data", None))
    if sig_data:
        try:
            img_data = base64.b64decode(sig_data)
            _embed_png_signature(pdf, img_data, (12, sig_y, col_w - 4, 18))
        except Exception:
            logger.warning("Could not embed quote signature into PDF", exc_info=True)

    pdf.set_draw_color(80, 80, 80)
    pdf.set_line_width(0.4)
    pdf.line(10, sig_y + 20, 10 + col_w, sig_y + 20)
    pdf.line(10 + col_w + 10, sig_y + 20, 200, sig_y + 20)
    pdf.set_line_width(0.2)
    pdf.set_y(sig_y + 22)
    pdf.set_font(_FONT, "", 7.5)
    pdf.set_text_color(*_GRAY)
    pdf.cell(col_w + 10, 4, "Unterschrift Auftraggeber / Kunde", align="C")
    pdf.cell(0, 4, "Unterschrift Goldschmiede / Auftragnehmer", align="C", ln=True)
    pdf.set_text_color(*_DARK)
    pdf.ln(6)

    # ── Legal disclaimer ──────────────────────────────────────────────────────
    valid_until_str = _fmt_date(getattr(quote, "valid_until", None))
    legal = (
        f"Dieser Kostenvoranschlag ist unverbindlich und gilt bis zum {valid_until_str}. "
        "Preisaenderungen durch Materialkostenschwankungen (Edelmetallpreise) vorbehalten. "
        "Mit der Unterschrift des Auftraggebers wird der Kostenvoranschlag zur verbindlichen "
        "Bestellung. Lieferbedingungen und Zahlungskonditionen gemaess unserer AGB. "
        "MwSt gemaess gesetzlichem Satz zum Zeitpunkt der Leistungserbringung."
    )

    pdf.set_fill_color(245, 245, 245)
    legal_y = pdf.get_y()
    pdf.rect(10, legal_y, 190, 24, style="F")
    pdf.set_xy(13, legal_y + 2)
    pdf.set_font(_FONT_B, "", 7.5)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 4, "RECHTLICHER HINWEIS", ln=True)
    pdf.set_x(13)
    pdf.set_font(_FONT, "", 7.5)
    pdf.multi_cell(184, 3.8, legal)
    pdf.set_text_color(*_DARK)

    return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────────────────────
# Valuation certificate renderer (Wertgutachten)
# ─────────────────────────────────────────────────────────────────────────────


def _render_valuation_certificate_fpdf(
    certificate: Any,
    customer: Any,
    workshop_name: str,
) -> bytes:
    """
    Build a bilingual insurance valuation certificate (Wertgutachten) PDF.

    Layout:
      - Bilingual header: WERTGUTACHTEN / INSURANCE VALUATION CERTIFICATE
      - Certificate metadata (number, date, valid until)
      - Item description (material + gemstones)
      - Appraised value (Gutachtenwert)
      - Goldsmith credentials + signature line
      - German legal disclaimer
    """
    cert_nr = _safe_str(getattr(certificate, "certificate_number", ""))
    footer_text = (
        f"{workshop_name}  |  Wertgutachten {cert_nr}  |  "
        f"{_fmt_date(getattr(certificate, 'valuation_date', None))}"
    )
    pdf = _GoldsmithPDF(workshop_name=workshop_name, footer_text=footer_text)

    # ── Bilingual header ──────────────────────────────────────────────────────
    pdf.set_font(_FONT_B, "", 16)
    pdf.set_text_color(*_GOLD)
    pdf.cell(0, 9, workshop_name, align="C", ln=True)

    pdf.set_font(_FONT_B, "", 18)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 8, "WERTGUTACHTEN", align="C", ln=True)

    pdf.set_font(_FONT, "", 10)
    pdf.set_text_color(*_GRAY)
    pdf.cell(0, 6, "INSURANCE VALUATION CERTIFICATE", align="C", ln=True)

    pdf.set_text_color(*_DARK)
    pdf.gold_rule()
    pdf.ln(4)

    # ── Certificate metadata ──────────────────────────────────────────────────
    meta_y = pdf.get_y()

    # Light-gold background
    pdf.set_fill_color(*_LIGHT_GOLD_BG)
    pdf.rect(10, meta_y, 190, 22, style="F")

    pdf.set_xy(13, meta_y + 2)
    pdf.set_font(_FONT_B, "", 7)
    pdf.set_text_color(*_GOLD)
    pdf.cell(60, 4, "GUTACHTEN-NR. / CERTIFICATE NO.")
    pdf.set_x(80)
    pdf.cell(60, 4, "DATUM / DATE")
    pdf.set_x(147)
    pdf.cell(0, 4, "GUELTIG BIS / VALID UNTIL", ln=True)

    pdf.set_xy(13, meta_y + 7)
    pdf.set_font(_FONT_B, "", 11)
    pdf.set_text_color(*_DARK)
    pdf.cell(60, 6, cert_nr)
    pdf.set_x(80)
    pdf.cell(60, 6, _fmt_date(getattr(certificate, "valuation_date", None)))
    pdf.set_x(147)
    pdf.cell(0, 6, _fmt_date(getattr(certificate, "valid_until", None)), ln=True)

    pdf.set_y(meta_y + 25)
    pdf.ln(3)

    # ── Customer ──────────────────────────────────────────────────────────────
    pdf.section_title("Eigentümer / Owner")

    customer_name = _safe_str(getattr(customer, "name", "Kunde"))
    pdf.set_font(_FONT_B, "", 10)
    pdf.cell(0, 5, customer_name, ln=True)
    pdf.set_font(_FONT, "", 9)
    pdf.set_text_color(*_GRAY)
    for attr in ("address", "city"):
        val = _safe_str(getattr(customer, attr, None))
        if val:
            pdf.cell(0, 4.5, val, ln=True)
    pdf.set_text_color(*_DARK)
    pdf.ln(3)

    # ── Item description ──────────────────────────────────────────────────────
    pdf.section_title("Beschreibung / Item Description")

    item_desc = _safe_str(getattr(certificate, "item_description", ""))
    pdf.set_font(_FONT, "", 10)
    pdf.multi_cell(0, 5, item_desc[:800])
    pdf.ln(3)

    # ── Material details ──────────────────────────────────────────────────────
    pdf.section_title("Materialangaben / Material Details")

    metal_type = _safe_str(getattr(certificate, "metal_type", None))
    metal_weight_g = getattr(certificate, "metal_weight_g", None)
    metal_purity = _safe_str(getattr(certificate, "metal_purity", None))

    if metal_type:
        pdf.kv_row("Metall / Metal:", metal_type, label_w=60)
    if metal_purity:
        pdf.kv_row("Feingehalt / Purity:", metal_purity, label_w=60)
    if metal_weight_g is not None:
        pdf.kv_row("Gewicht / Weight:", f"{metal_weight_g:.3f} g", label_w=60)

    pdf.ln(2)

    # ── Gemstones ─────────────────────────────────────────────────────────────
    gemstones_desc = _safe_str(getattr(certificate, "gemstones_description", None))
    if gemstones_desc:
        pdf.section_title("Edelsteine / Gemstones")
        pdf.set_font(_FONT, "", 9)
        pdf.multi_cell(0, 4.5, gemstones_desc[:800])
        pdf.ln(3)

    # ── Appraised value ───────────────────────────────────────────────────────
    pdf.section_title("Gutachtenwert / Appraised Value")

    appraised_value = getattr(certificate, "appraised_value", 0.0)
    label_w = 140
    value_w = 38

    pdf.set_fill_color(*_GOLD)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(_FONT_B, "", 12)
    pdf.cell(label_w, 8, "Versicherungswert / Replacement Value:", fill=True)
    pdf.cell(value_w, 8, _fmt_eur(appraised_value), align="R", fill=True, ln=True)
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(*_DARK)
    pdf.ln(3)

    pdf.set_font(_FONT, "", 8)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(
        0,
        4,
        "Der angegebene Wert entspricht dem Wiederbeschaffungswert zum Zeitpunkt der Bewertung. / "
        "The stated value represents the replacement cost at the time of valuation.",
    )
    pdf.set_text_color(*_DARK)
    pdf.ln(5)

    # ── Goldsmith credentials + signature ─────────────────────────────────────
    pdf.section_title("Gutachter / Appraiser")

    goldsmith_name = _safe_str(getattr(certificate, "goldsmith_name", ""))
    goldsmith_qual = _safe_str(getattr(certificate, "goldsmith_qualification", None))

    pdf.set_font(_FONT_B, "", 10)
    pdf.cell(0, 5, goldsmith_name, ln=True)
    if goldsmith_qual:
        pdf.set_font(_FONT, "", 9)
        pdf.set_text_color(*_GRAY)
        pdf.cell(0, 4.5, goldsmith_qual, ln=True)
        pdf.set_text_color(*_DARK)
    pdf.ln(3)

    pdf.set_font(_FONT, "", 8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(0, 4, workshop_name, ln=True)
    pdf.set_text_color(*_DARK)
    pdf.ln(8)

    # Signature line
    sig_y = pdf.get_y()
    col_w = 88
    pdf.set_draw_color(80, 80, 80)
    pdf.set_line_width(0.4)
    pdf.line(10, sig_y, 10 + col_w, sig_y)
    pdf.set_line_width(0.2)
    pdf.set_y(sig_y + 2)
    pdf.set_font(_FONT, "", 7.5)
    pdf.set_text_color(*_GRAY)
    pdf.cell(
        col_w + 10, 4, f"Ort, Datum / Place, Date: ______________________", align="L"
    )
    pdf.set_y(sig_y + 2)
    pdf.set_x(10 + col_w + 10)
    pdf.cell(0, 4, "Unterschrift + Stempel / Signature + Stamp", align="L", ln=True)
    pdf.set_text_color(*_DARK)
    pdf.ln(8)

    # ── Legal disclaimer ──────────────────────────────────────────────────────
    legal = (
        "Dieses Gutachten dient der Versicherungsbewertung und wurde nach bestem Wissen "
        "und Gewissen erstellt. Der Gutachter haftet nicht fuer Schaeden, die aus der "
        "Verwendung dieses Dokuments entstehen. Der Gutachtenwert stellt keinen Kaufpreis dar. "
        "Gueltigkeit: 2 Jahre ab Ausstellungsdatum. Dieses Dokument ist nur gueltig mit "
        "Originalunterschrift und Stempel des Gutachters. / "
        "This certificate is for insurance valuation purposes only. "
        "Valid for 2 years from the date of issue. "
        "Original signature and stamp required for validity."
    )
    pdf.set_fill_color(245, 245, 245)
    legal_y = pdf.get_y()
    pdf.rect(10, legal_y, 190, 26, style="F")
    pdf.set_xy(13, legal_y + 2)
    pdf.set_font(_FONT_B, "", 7.5)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 4, "RECHTLICHER HINWEIS / LEGAL NOTICE", ln=True)
    pdf.set_x(13)
    pdf.set_font(_FONT, "", 7)
    pdf.multi_cell(184, 3.5, legal)
    pdf.set_text_color(*_DARK)

    return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────────────────────
# Customer update renderer (Kundeninfo — PDF-only fallback delivery)
# ─────────────────────────────────────────────────────────────────────────────

_PHOTO_MAX_W_MM = 100.0
_PHOTO_MAX_H_MM = 70.0
_PHOTO_MARGIN_MM = 4.0
_UPDATE_BODY_MAX_CHARS = 4000
_UPDATE_TRUNCATION_MARKER = "[Text gekürzt]"


def _embed_photo_grid(pdf: "_GoldsmithPDF", photos: list[bytes]) -> None:
    """
    Place each of `photos` (JPEG bytes, e.g. from
    ``image_validation.create_email_variant``) into the PDF, one per row,
    scaled to fit within a fixed box while preserving aspect ratio. Uses the
    ``_embed_image_bytes`` NamedTemporaryFile pattern (fpdf2 needs a
    filesystem path). A photo that cannot be read/embedded is skipped with a
    logged warning rather than aborting the whole document — a bad photo
    must not block delivery of the rest of the update.

    Page breaks: ``pdf.image()`` bypasses fpdf2's auto-page-break (that
    mechanism only triggers on text cells), so each photo's height is
    checked against ``pdf.page_break_trigger`` up front and a fresh page is
    started when it would not fit — otherwise photos past the first ~3 would
    be drawn off the bottom edge of the page.
    """
    for photo_bytes in photos:
        try:
            with Image.open(io.BytesIO(photo_bytes)) as img:
                w_px, h_px = img.size
        except Exception:
            logger.warning(
                "Could not read photo dimensions for customer-update PDF embed",
                exc_info=True,
            )
            continue
        if w_px <= 0 or h_px <= 0:
            continue

        aspect = h_px / w_px
        w_mm = _PHOTO_MAX_W_MM
        h_mm = w_mm * aspect
        if h_mm > _PHOTO_MAX_H_MM:
            h_mm = _PHOTO_MAX_H_MM
            w_mm = h_mm / aspect

        if pdf.get_y() + h_mm > pdf.page_break_trigger:
            pdf.add_page()

        y = pdf.get_y()
        try:
            _embed_image_bytes(pdf, photo_bytes, (10, y, w_mm, h_mm), suffix=".jpg")
        except Exception:
            logger.warning(
                "Could not embed photo into customer-update PDF", exc_info=True
            )
            continue
        pdf.set_y(y + h_mm + _PHOTO_MARGIN_MM)


def _compose_update_pdf_lines(
    update: Any,
    order_ref: str,
    customer_name: str,
) -> list[tuple[str, str]]:
    """
    Compose the ordered visible text content of a customer-update PDF.

    Pure function (no FPDF dependency) so the document's textual content is
    directly unit-testable — fpdf2's embedded-TTF page streams are
    glyph-index encoded and not text-searchable in the output bytes, so
    without this seam a regression that dropped a draw call (e.g. the body
    ``multi_cell``) would be invisible to byte-level assertions.
    ``_render_customer_update_fpdf`` consumes this list verbatim; it draws
    nothing text-wise that is not produced here (except the workshop name,
    which it receives separately).

    Returns a list of ``(kind, text)`` tuples in draw order. Kinds:
    ``title`` / ``kv`` (label and value separated by a tab) / ``section`` /
    ``body`` / ``footer``.

    Body handling: truncated to ``_UPDATE_BODY_MAX_CHARS`` with a visible
    German marker line (``_UPDATE_TRUNCATION_MARKER``) appended, and an INFO
    log carrying the update id — never silent (CLAUDE.md: fail loudly).
    """
    subject = _safe_str(getattr(update, "subject", ""))
    body = _safe_str(getattr(update, "body", ""))

    if len(body) > _UPDATE_BODY_MAX_CHARS:
        logger.info(
            "Customer update body truncated for PDF render",
            extra={
                "update_id": getattr(update, "id", None),
                "body_length": len(body),
                "max_chars": _UPDATE_BODY_MAX_CHARS,
            },
        )
        body = f"{body[:_UPDATE_BODY_MAX_CHARS]}\n\n{_UPDATE_TRUNCATION_MARKER}"

    return [
        ("title", "KUNDENINFORMATION"),
        ("kv", f"Auftrag:\t{order_ref}"),
        ("kv", f"Kunde:\t{customer_name}"),
        ("section", subject or "Update"),
        ("body", body),
        (
            "footer",
            f"Referenz: {order_ref}  |  "
            "Ihre Daten werden ausschliesslich zur Bearbeitung dieses "
            "Auftrags verwendet.",
        ),
    ]


def _render_customer_update_fpdf(
    update: Any,
    order_ref: str,
    customer_name: str,
    photos: list[bytes],
    workshop_name: str,
) -> bytes:
    """
    Build a Kundeninfo PDF (progress / cost-change / ready-for-pickup / custom
    update) — the PDF-only fallback delivery path used when SMTP is unset or
    the goldsmith prefers to hand/print/send it herself (spec:
    ``delivery_method=pdf_manual``). Mirrors the email template's content
    (subject/body/order reference/footer) so both delivery paths carry
    identical information. All visible text content comes from
    ``_compose_update_pdf_lines`` (the unit-testable seam) — this function
    only owns layout, styling, and photo embedding.
    """
    subject = _safe_str(getattr(update, "subject", ""))
    lines = _compose_update_pdf_lines(update, order_ref, customer_name)

    footer_text = f"{workshop_name}  |  {order_ref}"
    pdf = _GoldsmithPDF(workshop_name=workshop_name, footer_text=footer_text)
    # Document metadata (/Info dict) — stored as a literal PDF string, unlike
    # the embedded-Unicode-TTF page content (glyph-index encoded, not
    # ASCII-searchable). This is the reliable way to assert "the reference
    # string is present in the output" without a PDF text-extraction
    # dependency (none is currently installed in this project).
    pdf.set_title(f"Kundeninformation {order_ref}")
    if subject:
        pdf.set_subject(subject)

    # ── Workshop name (header) ────────────────────────────────────────────────
    pdf.set_font(_FONT_B, "", 16)
    pdf.set_text_color(*_GOLD)
    pdf.cell(0, 9, workshop_name, ln=True)

    # ── Composed text content, in order ───────────────────────────────────────
    photos_drawn = False
    for kind, text in lines:
        if kind == "title":
            pdf.set_font(_FONT_B, "", 18)
            pdf.set_text_color(60, 60, 60)
            pdf.cell(0, 10, text, ln=True)
            pdf.set_text_color(*_DARK)
            pdf.gold_rule()
            pdf.ln(4)
        elif kind == "kv":
            label, _, value = text.partition("\t")
            pdf.kv_row(label, value, label_w=40)
        elif kind == "section":
            pdf.ln(3)
            pdf.section_title(text)
        elif kind == "body":
            pdf.set_font(_FONT, "", 10)
            pdf.multi_cell(0, 5, text)
            pdf.ln(4)
        elif kind == "footer":
            # Photos sit between body and footer note.
            if photos:
                pdf.section_title(f"Fotos ({len(photos)})")
                _embed_photo_grid(pdf, photos)
                pdf.ln(2)
                photos_drawn = True
            pdf.set_font(_FONT, "", 8)
            pdf.set_text_color(*_GRAY)
            pdf.multi_cell(0, 4, text)
            pdf.set_text_color(*_DARK)

    # Defensive: if the composed lines ever lose their footer entry, the
    # photos must still be drawn rather than silently dropped.
    if photos and not photos_drawn:
        pdf.section_title(f"Fotos ({len(photos)})")
        _embed_photo_grid(pdf, photos)

    return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────────────────────
# Public service class
# ─────────────────────────────────────────────────────────────────────────────


class PDFService:
    """
    Service for generating PDFs for invoices and scrap gold receipts.

    All methods are static and return raw bytes. The caller is responsible
    for streaming the response to the client (e.g. via FastAPI StreamingResponse).

    Template files (Jinja2 HTML) live in:
      src/goldsmith_erp/templates/

    The HTML templates are kept in sync with the fpdf2 layout so they can
    be used for preview rendering (e.g. in a future WeasyPrint upgrade).
    """

    @staticmethod
    def render_invoice_pdf(
        invoice: Any,
        customer: Any,
        line_items: list[Any],
        workshop_name: str,
        altgold_credit: float = 0.0,
        seller: Optional[Mapping[str, Any]] = None,
        gemstones: Optional[list[Any]] = None,
    ) -> bytes:
        """
        Render a German Rechnung (or Stornorechnung) as PDF.

        W2-06: ``gemstones`` (optional) prints a "Steine" block with the
        description of every stone (no purchase cost).

        W2-04: ``seller`` is the Werkstatt-Stammdaten block from the invoice
        snapshot; with it the PDF carries every §14 Abs. 4 UStG element
        (seller address + Steuernummer/USt-IdNr., Leistungsdatum, net per
        rate, VAT, gross, or the §19 UStG note for a Kleinunternehmer).

        Args:
            invoice:        InvoiceResponse-like object (invoice_number, issue_date,
                            due_date, subtotal, tax_rate, tax_amount, total, notes,
                            payment_method, order_id).
            customer:       Customer object with name, address, city, email, phone attrs.
            line_items:     List of line item objects with description, quantity,
                            unit_price, total attrs.
            workshop_name:  Business name from settings (e.g. "Goldschmiede Müller").
            altgold_credit: Optional scrap gold credit to subtract (Gutschrift Altgold).

        Returns:
            Raw PDF bytes. Caller streams via StreamingResponse.
        """
        logger.info(
            "Rendering invoice PDF",
            extra={"invoice_number": invoice.invoice_number},
        )
        return _render_invoice_fpdf(
            invoice=invoice,
            customer=customer,
            line_items=line_items,
            workshop_name=workshop_name,
            altgold_credit=altgold_credit,
            seller=seller,
            gemstones=gemstones,
        )

    @staticmethod
    def render_scrap_gold_receipt(
        scrap_gold: Any,
        items: list[Any],
        customer: Any,
        workshop_name: str,
        signature_base64: Optional[str] = None,
    ) -> bytes:
        """
        Render a scrap gold Ankaufsbeleg as PDF.

        Args:
            scrap_gold:       ScrapGoldRead-like object (id, created_at,
                              total_fine_gold_g, total_value_eur, gold_price_per_g).
            items:            List of scrap gold item objects with description, alloy,
                              weight_g, fine_content_g attrs.
            customer:         Customer object with name, address, city, phone attrs.
            workshop_name:    Business name from settings.
            signature_base64: Optional base64-encoded PNG of the customer's signature.

        Returns:
            Raw PDF bytes. Caller streams via StreamingResponse.
        """
        logger.info(
            "Rendering scrap gold receipt PDF",
            extra={"scrap_gold_id": scrap_gold.id},
        )
        return _render_scrap_gold_fpdf(
            scrap_gold=scrap_gold,
            items=items,
            customer=customer,
            workshop_name=workshop_name,
            signature_base64=signature_base64,
        )

    @staticmethod
    def render_quote_pdf(
        quote: Any,
        customer: Any,
        line_items: list[Any],
        workshop_name: str,
        gemstones: Optional[list[Any]] = None,
    ) -> bytes:
        """
        Render a German Kostenvoranschlag as PDF.

        W2-06: ``gemstones`` (optional) prints a "Steine" block.

        Args:
            quote:         QuoteResponse-like object (quote_number, created_at,
                           valid_until, subtotal, tax_rate, tax_amount, total,
                           notes, order_id, customer_signature_data).
            customer:      Customer object with name, address, city, email, phone attrs.
            line_items:    List of line item objects with description, quantity,
                           unit_price, total attrs.
            workshop_name: Business name from settings.

        Returns:
            Raw PDF bytes. Caller streams via StreamingResponse.
        """
        logger.info(
            "Rendering quote PDF",
            extra={"quote_number": quote.quote_number},
        )
        return _render_quote_fpdf(
            quote=quote,
            customer=customer,
            line_items=line_items,
            workshop_name=workshop_name,
            gemstones=gemstones,
        )

    @staticmethod
    def render_valuation_certificate_pdf(
        certificate: Any,
        customer: Any,
        workshop_name: str,
    ) -> bytes:
        """
        Render a bilingual insurance valuation certificate (Wertgutachten) as PDF.

        Args:
            certificate:   ValuationCertificate ORM object or Pydantic response.
                           Required attrs: certificate_number, valuation_date,
                           valid_until, item_description, metal_type, metal_weight_g,
                           metal_purity, gemstones_description, appraised_value,
                           goldsmith_name, goldsmith_qualification.
            customer:      Customer object with name, address, city attrs.
            workshop_name: Business name from settings.

        Returns:
            Raw PDF bytes. Caller streams via StreamingResponse.
        """
        logger.info(
            "Rendering valuation certificate PDF",
            # Do not log appraised_value — it is financial data
            extra={"certificate_number": certificate.certificate_number},
        )
        return _render_valuation_certificate_fpdf(
            certificate=certificate,
            customer=customer,
            workshop_name=workshop_name,
        )

    @staticmethod
    def render_ankaufsbuch_pdf(
        rows: list[Any], date_from: Any, date_to: Any, workshop_name: str
    ) -> bytes:
        """W2-16: Ankaufsbuch Altgold for a period (see services/pdf_reports.py)."""
        from goldsmith_erp.services.pdf_reports import (  # noqa: PLC0415
            render_ankaufsbuch_pdf,
        )

        logger.info("Rendering Ankaufsbuch PDF", extra={"row_count": len(rows)})
        return render_ankaufsbuch_pdf(rows, date_from, date_to, workshop_name)

    @staticmethod
    def render_handover_pdf(data: Any, workshop_name: str) -> bytes:
        """W2-11: Abholprotokoll for a delivered order (services/pdf_reports.py)."""
        from goldsmith_erp.services.pdf_reports import (  # noqa: PLC0415
            render_handover_pdf,
        )

        logger.info("Rendering handover PDF", extra={"order_id": data.order_id})
        return render_handover_pdf(data, workshop_name)

    @staticmethod
    def render_customer_update_pdf(
        update: Any,
        order_ref: str,
        customer_name: str,
        photos: list[bytes],
        workshop_name: str,
    ) -> bytes:
        """
        Render a Kundeninfo update as PDF — the ``delivery_method=pdf_manual``
        fallback path used when SMTP is unset or the goldsmith sends it
        herself.

        Args:
            update:        CustomerUpdate ORM object or Pydantic response.
                           Required attrs: subject, body.
            order_ref:     Human-readable order/repair reference string
                           (e.g. "Auftrag #1042").
            customer_name: Customer display name.
            photos:        List of JPEG bytes — the explicitly-selected,
                           EXIF-stripped email-variant photos (see
                           ``image_validation.create_email_variant``), NOT
                           all order photos (design-IP rule).
            workshop_name: Business name from settings.

        Returns:
            Raw PDF bytes. Caller streams via StreamingResponse.
        """
        # order_ref is a human-readable string that may carry the order's
        # free-text title (Order.title, business-confidential per
        # CLAUDE.md) — never log it. Numeric ids only (matches branch
        # convention, e.g. customer_update_service._log_financial_access).
        logger.info(
            "Rendering customer update PDF",
            extra={
                "update_id": getattr(update, "id", None),
                "order_id": getattr(update, "order_id", None),
                "repair_job_id": getattr(update, "repair_job_id", None),
                "photo_count": len(photos),
            },
        )
        return _render_customer_update_fpdf(
            update=update,
            order_ref=order_ref,
            customer_name=customer_name,
            photos=photos,
            workshop_name=workshop_name,
        )
