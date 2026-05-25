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

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from fpdf import FPDF
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)


def _embed_png_signature(
    pdf: FPDF, img_data: bytes, rect: tuple[float, float, float, float]
) -> None:
    """Embed a PNG signature into the PDF via a secure temp file.

    fpdf2 needs a filesystem path, so the bytes are written to a
    NamedTemporaryFile (secure mkstemp-based API). The temp file is always
    removed afterwards, even if image embedding raises. ``rect`` is the
    placement box as ``(x, y, width, height)``.
    """
    x, y, w, h = rect
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(img_data)
            tmp_path = tmp.name
        pdf.image(tmp_path, x=x, y=y, w=w, h=h)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

# Path to Jinja2 templates directory
_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Path to bundled TTF fonts (DejaVu — public domain, full Unicode support)
_FONTS_DIR = Path(__file__).parent.parent / "fonts"
_FONT_REGULAR = str(_FONTS_DIR / "DejaVuSans.ttf")
_FONT_BOLD = str(_FONTS_DIR / "DejaVuSans-Bold.ttf")

# Font family names used throughout the service
_FONT = "DejaVu"        # regular weight
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

_GOLD = (139, 105, 20)       # RGB for #8B6914
_DARK = (34, 34, 34)         # Near-black
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
        self.set_font(_FONT, "",7)
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
        self.set_font(_FONT, "",9)
        self.set_text_color(*_GRAY)
        self.cell(label_w, 5, label)
        self.set_text_color(*_DARK)
        self.set_font(_FONT_B, "", 9)
        self.cell(0, 5, value, ln=True)
        self.set_font(_FONT, "",9)

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
        self.set_font(_FONT, "",9.5)
        row_h = 6
        for text, w, align in cols:
            self.cell(w, row_h, text, border=0, align=align, fill=True)
        self.ln(row_h)
        self.set_fill_color(255, 255, 255)


# ─────────────────────────────────────────────────────────────────────────────
# Invoice renderer
# ─────────────────────────────────────────────────────────────────────────────

def _render_invoice_fpdf(
    invoice: Any,
    customer: Any,
    line_items: list[Any],
    workshop_name: str,
    altgold_credit: float = 0.0,
) -> bytes:
    """Build an invoice PDF with fpdf2 and return raw bytes."""

    footer_text = (
        f"{workshop_name}  |  Rechnung {invoice.invoice_number}"
    )
    pdf = _GoldsmithPDF(workshop_name=workshop_name, footer_text=footer_text)

    # ── Page top: workshop name + RECHNUNG title ──────────────────────────────
    pdf.set_font(_FONT_B, "", 18)
    pdf.set_text_color(*_GOLD)
    pdf.cell(110, 10, workshop_name)

    pdf.set_font(_FONT_B, "", 22)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 10, "RECHNUNG", align="R", ln=True)

    pdf.set_font(_FONT, "",8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(110, 5, "Goldschmiede & Atelier")
    pdf.set_font(_FONT_B, "", 10)
    pdf.set_text_color(*_GOLD)
    pdf.cell(0, 5, invoice.invoice_number, align="R", ln=True)
    pdf.set_text_color(*_DARK)

    pdf.gold_rule()
    pdf.ln(4)

    # ── Address columns ───────────────────────────────────────────────────────
    x_left = pdf.get_x()
    y_addr = pdf.get_y()

    # Left column: workshop (Rechnungssteller)
    pdf.set_xy(x_left, y_addr)
    pdf.set_font(_FONT_B, "", 7)
    pdf.set_text_color(*_GRAY)
    pdf.cell(90, 4, "RECHNUNGSSTELLER", ln=True)
    pdf.set_text_color(*_DARK)
    pdf.set_font(_FONT_B, "", 10)
    pdf.cell(90, 5, workshop_name, ln=True)
    pdf.set_font(_FONT, "",9)

    # Right column: customer (Rechnungsempfänger)
    pdf.set_xy(x_left + 100, y_addr)
    pdf.set_font(_FONT_B, "", 7)
    pdf.set_text_color(*_GRAY)
    pdf.cell(90, 4, "RECHNUNGSEMPFÄNGER", ln=True)
    cust_y = pdf.get_y()
    pdf.set_xy(x_left + 100, cust_y)
    pdf.set_text_color(*_DARK)

    customer_name = _safe_str(getattr(customer, "name", "Kunde"))
    pdf.set_font(_FONT_B, "", 10)
    pdf.cell(90, 5, customer_name, ln=True)
    pdf.set_xy(x_left + 100, pdf.get_y())
    pdf.set_font(_FONT, "",9)

    for attr in ("address", "city", "email", "phone"):
        val = _safe_str(getattr(customer, attr, None))
        if val:
            pdf.set_xy(x_left + 100, pdf.get_y())
            pdf.cell(90, 4.5, val, ln=True)

    # Move below address block
    pdf.set_y(max(pdf.get_y(), y_addr + 28))
    pdf.ln(4)

    # ── Invoice meta (right-aligned table) ───────────────────────────────────
    meta: list[tuple[str, str]] = [
        ("Rechnungsdatum:", _fmt_date(invoice.issue_date)),
        ("Fälligkeitsdatum:", _fmt_date(invoice.due_date)),
        ("Auftragsnummer:", str(invoice.order_id)),
    ]
    if getattr(invoice, "payment_method", None):
        meta.append(("Zahlungsart:", str(invoice.payment_method)))

    for label, value in meta:
        pdf.set_font(_FONT, "",9)
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

    pdf.filled_header_row([
        ("Pos.", col_pos, "C"),
        ("Beschreibung", col_desc, "L"),
        ("Menge", col_qty, "R"),
        ("Einzelpreis", col_unit, "R"),
        ("Gesamtpreis", col_total, "R"),
    ])

    for i, item in enumerate(line_items):
        even = (i % 2 == 0)
        pdf.table_data_row([
            (str(i + 1), col_pos, "C"),
            (_safe_str(item.description)[:65], col_desc, "L"),
            (_fmt_num(item.quantity), col_qty, "R"),
            (_fmt_eur(item.unit_price), col_unit, "R"),
            (_fmt_eur(item.total), col_total, "R"),
        ], even=even)

    # Divider below table
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(4)

    # ── Totals (right-aligned) ────────────────────────────────────────────────
    label_w = 140
    value_w = 38

    def _total_row(label: str, value: str, bold: bool = False, gold_bg: bool = False) -> None:
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

    _total_row("Zwischensumme (netto):", _fmt_eur(invoice.subtotal))

    if altgold_credit > 0:
        pdf.set_text_color(*_GOLD)
        pdf.set_font(_FONT, "", 9)
        pdf.cell(label_w, 5, "Gutschrift Altgold:")
        pdf.cell(value_w, 5, f"–{_fmt_eur(altgold_credit)}", align="R", ln=True)
        pdf.set_text_color(*_DARK)

    _total_row(
        f"MwSt {invoice.tax_rate:.0f}%:",
        _fmt_eur(invoice.tax_amount),
    )
    _total_row("Gesamtbetrag:", _fmt_eur(invoice.total), gold_bg=True)
    pdf.ln(4)

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes = _safe_str(getattr(invoice, "notes", None))
    if notes:
        pdf.set_fill_color(*_LIGHT_GOLD_BG)
        pdf.set_draw_color(*_GOLD)
        pdf.set_line_width(0.5)
        y_note = pdf.get_y()
        # Left gold border bar
        pdf.rect(10, y_note, 2, 14, style="F")
        pdf.set_x(15)
        pdf.set_font(_FONT_B, "", 7.5)
        pdf.set_text_color(*_GOLD)
        pdf.cell(0, 5, "HINWEISE", ln=True)
        pdf.set_x(15)
        pdf.set_font(_FONT, "",9)
        pdf.set_text_color(*_DARK)
        pdf.multi_cell(175, 4.5, notes[:400])
        pdf.ln(2)

    # ── Payment instruction ───────────────────────────────────────────────────
    pdf.set_font(_FONT, "",9)
    pdf.set_text_color(*_GRAY)
    payment_text = (
        f"Bitte überweisen Sie den Gesamtbetrag von {_fmt_eur(invoice.total)} "
        f"bis zum {_fmt_date(invoice.due_date)}. "
        f"Verwendungszweck: {invoice.invoice_number}"
    )
    pdf.multi_cell(0, 4.5, payment_text)
    pdf.set_text_color(*_DARK)

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
    pdf.set_font(_FONT, "",8)
    pdf.set_text_color(*_GRAY)
    pdf.cell(0, 5, f"Datum: {_fmt_date(scrap_gold.created_at)}     Beleg-Nr.: {receipt_nr}", align="C", ln=True)
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

    pdf.set_font(_FONT, "",8.5)
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

    pdf.filled_header_row([
        ("Beschreibung", col_desc, "L"),
        ("Legierung", col_alloy, "C"),
        ("Gewicht (g)", col_weight, "R"),
        ("Feingehalt (g)", col_fine, "R"),
    ])

    for i, item in enumerate(items):
        even = (i % 2 == 0)
        pdf.table_data_row([
            (_safe_str(item.description)[:45], col_desc, "L"),
            (_safe_str(item.alloy), col_alloy, "C"),
            (f"{item.weight_g:.3f}", col_weight, "R"),
            (f"{item.fine_content_g:.3f}", col_fine, "R"),
        ], even=even)

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
            pdf.set_font(_FONT, "",9)
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
    pdf.set_font(_FONT, "",7.5)
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
    pdf.set_font(_FONT, "",7.5)
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
) -> bytes:
    """Build a Kostenvoranschlag PDF with fpdf2 and return raw bytes."""
    import base64

    footer_text = (
        f"{workshop_name}  |  Kostenvoranschlag {quote.quote_number}"
    )
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

    pdf.filled_header_row([
        ("Pos.", col_pos, "C"),
        ("Beschreibung", col_desc, "L"),
        ("Menge", col_qty, "R"),
        ("Einzelpreis", col_unit, "R"),
        ("Gesamtpreis", col_total, "R"),
    ])

    for i, item in enumerate(line_items):
        even = (i % 2 == 0)
        pdf.table_data_row([
            (str(i + 1), col_pos, "C"),
            (_safe_str(item.description)[:65], col_desc, "L"),
            (_fmt_num(item.quantity), col_qty, "R"),
            (_fmt_eur(item.unit_price), col_unit, "R"),
            (_fmt_eur(item.total), col_total, "R"),
        ], even=even)

    # Divider below table
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(4)

    # ── Totals ────────────────────────────────────────────────────────────────
    label_w = 140
    value_w = 38

    def _total_row(label: str, value: str, bold: bool = False, gold_bg: bool = False) -> None:
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
    pdf.cell(col_w + 10, 4, f"Ort, Datum / Place, Date: ______________________", align="L")
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
    ) -> bytes:
        """
        Render a German Rechnung as PDF.

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
    ) -> bytes:
        """
        Render a German Kostenvoranschlag as PDF.

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
