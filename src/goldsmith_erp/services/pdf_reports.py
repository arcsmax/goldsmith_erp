"""PDF renderers for the Ankaufsbuch (W2-16) and the Abholprotokoll (W2-11).

Kept out of ``pdf_service.py`` (already the largest service module); the
layout helpers (``_GoldsmithPDF``, fonts, colours) are shared from there and
``PDFService`` exposes both renderers as static methods.

Visible text goes through small pure "compose" functions so tests can check
the content without a PDF text extractor (fpdf2 page text is glyph-encoded).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Sequence, Tuple

from goldsmith_erp.services.ankaufsbuch_service import (
    LEGAL_NOTE,
    AnkaufsbuchRow,
    format_de_datetime,
    format_de_number,
)
from goldsmith_erp.services.pdf_service import (
    _DARK,
    _FONT,
    _FONT_B,
    _GOLD,
    _GRAY,
    _embed_photo_grid,
    _GoldsmithPDF,
)

Section = Tuple[str, List[str]]

# ─────────────────────────────────────────────────────────────────────────────
# Shared drawing
# ─────────────────────────────────────────────────────────────────────────────


def _text_width(pdf: _GoldsmithPDF) -> float:
    return float(pdf.w - pdf.l_margin - pdf.r_margin)


def _title(pdf: _GoldsmithPDF, workshop_name: str, title: str, subtitle: str) -> None:
    pdf.set_font(_FONT_B, "", 16)
    pdf.set_text_color(*_GOLD)
    pdf.cell(0, 9, workshop_name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT_B, "", 13)
    pdf.set_text_color(*_DARK)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT, "", 9)
    pdf.set_text_color(*_GRAY)
    pdf.cell(0, 5, subtitle, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_DARK)
    pdf.gold_rule()
    pdf.ln(4)


def _draw_sections(pdf: _GoldsmithPDF, sections: Sequence[Section]) -> None:
    for heading, lines in sections:
        if not lines:
            continue
        pdf.section_title(heading)
        pdf.set_font(_FONT, "", 9.5)
        for line in lines:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(_text_width(pdf), 5, line[:1500])
        pdf.ln(3)


def _signature_lines(pdf: _GoldsmithPDF, left: str, right: str) -> None:
    pdf.ln(12)
    y = pdf.get_y()
    col_w = 85.0
    pdf.set_draw_color(80, 80, 80)
    pdf.set_line_width(0.4)
    pdf.line(10, y, 10 + col_w, y)
    pdf.line(115, y, 200, y)
    pdf.set_line_width(0.2)
    pdf.set_y(y + 1)
    pdf.set_font(_FONT, "", 7.5)
    pdf.set_text_color(*_GRAY)
    pdf.cell(105, 4, left)
    pdf.cell(0, 4, right, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_DARK)


# ─────────────────────────────────────────────────────────────────────────────
# Ankaufsbuch (W2-16)
# ─────────────────────────────────────────────────────────────────────────────


def compose_ankaufsbuch_sections(rows: Sequence[AnkaufsbuchRow]) -> List[Section]:
    """One section per purchase: heading "AG-00001 · Datum · Betrag"."""
    if not rows:
        return [
            ("Keine Ankäufe", ["Im gewählten Zeitraum wurde kein Altgold angekauft."])
        ]
    sections: List[Section] = []
    for row in rows:
        heading = (
            f"{row.receipt_number} · {format_de_datetime(row.signed_at)} · "
            f"{format_de_number(row.total_eur)} €"
        )
        id_line = " · ".join(
            part for part in (row.id_document, row.id_number, row.id_authority) if part
        )
        sections.append(
            (
                heading,
                [
                    f"Verkäufer: {row.seller or '—'}",
                    f"Anschrift: {row.address or '—'}",
                    f"Ausweis: {id_line or 'nicht erfasst'}",
                    f"Geprüft von: {row.checked_by or '—'}",
                    f"Positionen: {row.items or '—'}",
                    (
                        f"Feingewicht: {format_de_number(row.fine_gold_g, 3)} g · Kurs: "
                        f"{format_de_number(row.price_per_g)} €/g · Status: {row.status}"
                    ),
                ],
            )
        )
    return sections


def render_ankaufsbuch_pdf(
    rows: Sequence[AnkaufsbuchRow],
    date_from: date,
    date_to: date,
    workshop_name: str,
) -> bytes:
    pdf = _GoldsmithPDF(
        workshop_name=workshop_name,
        footer_text=f"{workshop_name}  |  Ankaufsbuch Altgold",
    )
    pdf.set_title(f"Ankaufsbuch {date_from:%d.%m.%Y}-{date_to:%d.%m.%Y}")
    _title(
        pdf,
        workshop_name,
        "Ankaufsbuch Altgold",
        f"Zeitraum {date_from:%d.%m.%Y} bis {date_to:%d.%m.%Y} · {len(rows)} Ankäufe",
    )
    pdf.set_font(_FONT, "", 8)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(_text_width(pdf), 4, LEGAL_NOTE)
    pdf.set_text_color(*_DARK)
    pdf.ln(3)
    _draw_sections(pdf, compose_ankaufsbuch_sections(rows))
    return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────────────────────
# Abholprotokoll / handover report (W2-11)
# ─────────────────────────────────────────────────────────────────────────────

WARRANTY_TEXT = (
    "Es gelten die gesetzlichen Gewährleistungsrechte. Bitte bewahren Sie "
    "dieses Protokoll zusammen mit der Rechnung auf."
)

_CARE_BY_METAL: Tuple[Tuple[str, str], ...] = (
    (
        "silver",
        "Silber läuft an der Luft an: trocken und luftdicht aufbewahren, "
        "mit einem Silberputztuch reinigen, nicht mit Chlor- oder Schwimmbadwasser "
        "in Berührung bringen.",
    ),
    (
        "white_gold",
        "Weißgold ist oft rhodiniert; die Rhodinierung nutzt sich mit der Zeit ab "
        "und kann in der Werkstatt erneuert werden.",
    ),
    (
        "platinum",
        "Platin ist sehr beständig; feine Kratzer bilden eine natürliche Patina und "
        "lassen sich bei Bedarf in der Werkstatt aufpolieren.",
    ),
    (
        "palladium",
        "Palladium ist leicht und anlaufbeständig; mit warmem Seifenwasser und "
        "einem weichen Tuch reinigen.",
    ),
    (
        "gold",
        "Gold mit warmem Wasser, etwas milder Seife und einer weichen Bürste "
        "reinigen; Kontakt mit Chlor und Haushaltsreinigern vermeiden.",
    ),
)

_CARE_STONES = (
    "Gefasste Steine regelmäßig auf festen Sitz prüfen lassen (etwa einmal im "
    "Jahr). Schmuck bei grober Arbeit und beim Sport ablegen."
)
_CARE_SOFT_STONES = (
    "Perlen, Opale, Smaragde und Türkise sind empfindlich: kein Ultraschall, kein "
    "Dampf, keine Parfüms oder Kosmetik direkt auf den Stein."
)
_SOFT_STONE_WORDS = (
    "perle",
    "opal",
    "smaragd",
    "türkis",
    "tuerkis",
    "koralle",
    "bernstein",
)


@dataclass(frozen=True)
class HandoverData:
    """Everything the Abholprotokoll prints (built by the orders router)."""

    order_id: int
    title: str
    customer_name: str
    handed_over_at: datetime
    metal_label: Optional[str]
    alloy: Optional[str]
    weight_g: Optional[float]
    ring_size_mm: Optional[float]
    surface_finish: Optional[str]
    gemstone_lines: List[str] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    metal_type: Optional[str] = None
    stone_types: List[str] = field(default_factory=list)
    photos: List[bytes] = field(default_factory=list)
    footer_note: Optional[str] = None
    # W7 followup: workshop-editable "Pflegehinweise" default text
    # (WorkshopSettings.care_text). None/empty falls back to care_texts().
    care_text: Optional[str] = None


def care_texts(metal_type: Optional[str], stone_types: Sequence[str]) -> List[str]:
    """Care advice for the metal and the stones of the piece."""
    texts: List[str] = []
    code = (metal_type or "").lower()
    for prefix, text in _CARE_BY_METAL:
        if code.startswith(prefix) or (prefix == "gold" and "gold" in code):
            texts.append(text)
            break
    if stone_types:
        texts.append(_CARE_STONES)
        lowered = " ".join(stone_types).lower()
        if any(word in lowered for word in _SOFT_STONE_WORDS):
            texts.append(_CARE_SOFT_STONES)
    return texts


def compose_handover_sections(data: HandoverData) -> List[Section]:
    piece: List[str] = [f"Auftrag #{data.order_id}: {data.title}"]
    if data.metal_label or data.alloy:
        piece.append(
            "Metall: " + " · ".join(p for p in (data.metal_label, data.alloy) if p)
        )
    if data.weight_g:
        piece.append(f"Gewicht: {format_de_number(data.weight_g)} g")
    if data.ring_size_mm:
        piece.append(f"Ringmaß: {format_de_number(data.ring_size_mm, 1)} mm")
    if data.surface_finish:
        piece.append(f"Oberfläche: {data.surface_finish}")
    return [
        (
            "Übergabe",
            [
                f"Kunde: {data.customer_name or '—'}",
                f"Datum: {format_de_datetime(data.handed_over_at)}",
            ],
        ),
        ("Schmuckstück", piece),
        ("Steine", list(data.gemstone_lines)),
        ("Material", list(data.materials)),
        (
            "Pflegehinweise",
            (
                [data.care_text]
                if data.care_text
                else care_texts(data.metal_type, data.stone_types)
            ),
        ),
        ("Gewährleistung", [WARRANTY_TEXT]),
    ]


def render_handover_pdf(data: HandoverData, workshop_name: str) -> bytes:
    pdf = _GoldsmithPDF(
        workshop_name=workshop_name,
        footer_text=data.footer_note or f"{workshop_name}  |  Abholprotokoll",
    )
    pdf.set_title(f"Abholprotokoll Auftrag #{data.order_id}")
    _title(
        pdf,
        workshop_name,
        "Abholprotokoll",
        f"Auftrag #{data.order_id} · {format_de_datetime(data.handed_over_at)}",
    )
    if data.photos:
        _embed_photo_grid(pdf, data.photos[:1])
    _draw_sections(pdf, compose_handover_sections(data))
    pdf.set_font(_FONT, "", 9)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(
        _text_width(pdf),
        5,
        "Das Schmuckstück wurde in einwandfreiem Zustand übergeben und geprüft.",
    )
    _signature_lines(pdf, "Datum, Unterschrift Kunde", "Unterschrift Werkstatt")
    return bytes(pdf.output())


__all__: List[str] = [
    "HandoverData",
    "care_texts",
    "compose_ankaufsbuch_sections",
    "compose_handover_sections",
    "render_ankaufsbuch_pdf",
    "render_handover_pdf",
]
