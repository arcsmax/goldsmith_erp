"""W2-06 (DOM-04): stones print on the quote and invoice PDF.

fpdf2 page text is glyph-encoded, so the drawn text is captured by wrapping
``cell``/``multi_cell`` of the PDF class (same idea as the /Info seam in
test_pdf_customer_update.py, without a PDF text-extraction dependency).
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import List

import pytest

import goldsmith_erp.services.pdf_service as pdf_module
from goldsmith_erp.models.gemstone import describe_gemstone
from goldsmith_erp.services.pdf_service import PDFService


@pytest.fixture
def drawn_text(monkeypatch) -> List[str]:
    captured: List[str] = []
    original_cell = pdf_module._GoldsmithPDF.cell
    original_multi = pdf_module._GoldsmithPDF.multi_cell

    def cell(self, *args, **kwargs):
        text = kwargs.get("text", kwargs.get("txt", args[2] if len(args) > 2 else ""))
        captured.append(str(text))
        return original_cell(self, *args, **kwargs)

    def multi_cell(self, *args, **kwargs):
        text = kwargs.get("text", kwargs.get("txt", args[2] if len(args) > 2 else ""))
        captured.append(str(text))
        return original_multi(self, *args, **kwargs)

    monkeypatch.setattr(pdf_module._GoldsmithPDF, "cell", cell)
    monkeypatch.setattr(pdf_module._GoldsmithPDF, "multi_cell", multi_cell)
    return captured


def _stones() -> list:
    return [
        SimpleNamespace(
            type="Diamant",
            quantity=3,
            carat=0.1,
            color="G",
            quality="VS1",
            shape="rund",
            cut=None,
            setting_type="prong",
            is_customer_stone=False,
            cost=120.0,
        ),
        SimpleNamespace(
            type="Saphir",
            quantity=1,
            carat=None,
            color=None,
            quality=None,
            shape=None,
            cut=None,
            setting_type="bezel",
            is_customer_stone=True,
            cost=0.0,
        ),
    ]


def test_describe_gemstone_is_german_and_has_no_cost():
    line = describe_gemstone(_stones()[0])
    assert line == "3 × Diamant 0,10 ct G/VS1, rund, Krappenfassung"
    assert "120" not in line
    assert describe_gemstone(_stones()[1]) == "1 × Saphir, Zargenfassung, Kundenstein"


def _quote() -> SimpleNamespace:
    return SimpleNamespace(
        quote_number="KV-2026-0001",
        created_at=datetime(2026, 9, 25),
        valid_until=datetime(2026, 10, 25),
        order_id=5,
        subtotal=100.0,
        tax_rate=19.0,
        tax_amount=19.0,
        total=119.0,
        notes=None,
        customer_signature_data=None,
    )


def test_quote_pdf_prints_the_stones(drawn_text):
    pdf = PDFService.render_quote_pdf(
        quote=_quote(),
        customer=SimpleNamespace(name="Erika Muster"),
        line_items=[],
        workshop_name="Goldschmiede Test",
        gemstones=_stones(),
    )
    assert pdf.startswith(b"%PDF")
    joined = "\n".join(drawn_text)
    assert "STEINE" in joined  # section_title upper-cases
    assert "3 × Diamant 0,10 ct G/VS1, rund, Krappenfassung" in joined
    assert "Kundenstein" in joined


def test_quote_pdf_without_stones_has_no_stone_block(drawn_text):
    PDFService.render_quote_pdf(
        quote=_quote(),
        customer=SimpleNamespace(name="Erika Muster"),
        line_items=[],
        workshop_name="Goldschmiede Test",
    )
    assert "STEINE" not in drawn_text


def test_invoice_pdf_prints_the_stones(drawn_text):
    invoice = SimpleNamespace(
        invoice_number="RE-2026-0001",
        order_id=5,
        issue_date=datetime(2026, 9, 25),
        due_date=datetime(2026, 10, 9),
        service_date=datetime(2026, 9, 24),
        notes=None,
        payment_method=None,
        cancels_invoice_number=None,
        cancels_invoice_date=None,
        storno_reason=None,
        subtotal=100.0,
        tax_rate=19.0,
        tax_amount=19.0,
        total=119.0,
        tax_breakdown=None,
        status="sent",
    )
    pdf = PDFService.render_invoice_pdf(
        invoice=invoice,
        customer=SimpleNamespace(name="Erika Muster"),
        line_items=[],
        workshop_name="Goldschmiede Test",
        gemstones=_stones(),
    )
    assert pdf.startswith(b"%PDF")
    assert any("Saphir, Zargenfassung, Kundenstein" in t for t in drawn_text)
