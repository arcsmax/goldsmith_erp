"""W2-11 (DOM-35): Abholprotokoll content (photo, metal, stones, care, signature)."""

from __future__ import annotations

import io
from datetime import datetime

from PIL import Image

from goldsmith_erp.services.pdf_reports import (
    WARRANTY_TEXT,
    HandoverData,
    care_texts,
    compose_handover_sections,
    render_handover_pdf,
)


def _data(**overrides) -> HandoverData:
    values = dict(
        order_id=42,
        title="Verlobungsring",
        customer_name="Maria Mustermann",
        handed_over_at=datetime(2026, 9, 25, 16, 30),
        metal_label="Weißgold",
        alloy="750",
        weight_g=4.2,
        ring_size_mm=54.0,
        surface_finish="Hochglanz",
        gemstone_lines=["1 × Diamant 0,30 ct G/VS1, rund, Krappenfassung"],
        materials=["Weißgold 750 Draht"],
        metal_type="white_gold_18k",
        stone_types=["Diamant"],
    )
    values.update(overrides)
    return HandoverData(**values)


def test_sections_list_piece_metal_stones_care_and_warranty():
    sections = dict(compose_handover_sections(_data()))
    assert sections["Übergabe"] == [
        "Kunde: Maria Mustermann",
        "Datum: 25.09.2026 16:30",
    ]
    piece = "\n".join(sections["Schmuckstück"])
    assert "Auftrag #42: Verlobungsring" in piece
    assert "Metall: Weißgold · 750" in piece
    assert "Gewicht: 4,20 g" in piece
    assert "Ringmaß: 54,0 mm" in piece
    assert sections["Steine"] == ["1 × Diamant 0,30 ct G/VS1, rund, Krappenfassung"]
    assert sections["Material"] == ["Weißgold 750 Draht"]
    care = " ".join(sections["Pflegehinweise"])
    assert "Rhodinierung" in care
    assert "festen Sitz" in care
    assert sections["Gewährleistung"] == [WARRANTY_TEXT]


def test_care_text_depends_on_metal_and_stone():
    assert "Silberputztuch" in " ".join(care_texts("silver_925", []))
    soft = " ".join(care_texts("gold_14k", ["Perle"]))
    assert "kein Ultraschall" in soft
    assert care_texts(None, []) == []


def test_render_embeds_the_photo_and_returns_a_pdf():
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), color=(120, 60, 10)).save(buf, format="JPEG")
    pdf = render_handover_pdf(_data(photos=[buf.getvalue()]), "Goldschmiede Test")
    assert pdf.startswith(b"%PDF")
    assert b"/Subtype /Image" in pdf
    assert b"Abholprotokoll Auftrag #42" in pdf  # /Info title


def test_render_without_photo_or_stones_still_works():
    pdf = render_handover_pdf(
        _data(gemstone_lines=[], stone_types=[], materials=[], photos=[]),
        "Goldschmiede Test",
    )
    assert pdf.startswith(b"%PDF")
    assert b"/Subtype /Image" not in pdf
