"""W2-16 (DOM-21): Ankaufsbuch rows, CSV and PDF content (no DB)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from goldsmith_erp.services.ankaufsbuch_service import (
    LEGAL_NOTE,
    AnkaufsbuchRow,
    to_csv,
)
from goldsmith_erp.services.pdf_reports import (
    compose_ankaufsbuch_sections,
    render_ankaufsbuch_pdf,
)


def _row(**overrides) -> AnkaufsbuchRow:
    values = dict(
        receipt_number="AG-00007",
        # 09:05 UTC is 11:05 in Berlin (CEST); the book prints local time.
        signed_at=datetime(2026, 9, 10, 9, 5, tzinfo=timezone.utc),
        seller="Maria Mustermann",
        address="Hauptstr. 1, 80331 München",
        id_document="Personalausweis",
        id_number="L01X00T47",
        id_authority="Stadt München",
        checked_by="Anne Goldschmied",
        items="Alter Ehering (585, 10,00 g, fein 5,850 g)",
        fine_gold_g=5.85,
        price_per_g=60.0,
        total_eur=2351.0,
        status="unterschrieben",
    )
    values.update(overrides)
    return AnkaufsbuchRow(**values)


def test_csv_has_legal_note_german_numbers_and_neutralised_formulas():
    csv_bytes = to_csv(
        [_row(seller="=HYPERLINK(evil)")], date(2026, 9, 1), date(2026, 9, 30)
    )
    assert csv_bytes.startswith("﻿".encode("utf-8"))
    text = csv_bytes.decode("utf-8-sig")
    assert LEGAL_NOTE in text
    assert "2.351,00" in text
    assert "10.09.2026 11:05" in text
    assert "'=HYPERLINK(evil)" in text


def test_pdf_sections_carry_seller_id_and_items():
    sections = compose_ankaufsbuch_sections([_row()])
    heading, lines = sections[0]
    assert heading == "AG-00007 · 10.09.2026 11:05 · 2.351,00 €"
    joined = "\n".join(lines)
    assert "Personalausweis · L01X00T47 · Stadt München" in joined
    assert "Alter Ehering" in joined
    assert "Geprüft von: Anne Goldschmied" in joined


def test_empty_period_renders_a_note_and_a_pdf():
    assert compose_ankaufsbuch_sections([])[0][0] == "Keine Ankäufe"
    pdf = render_ankaufsbuch_pdf([], date(2026, 9, 1), date(2026, 9, 30), "Werkstatt")
    assert pdf.startswith(b"%PDF")
