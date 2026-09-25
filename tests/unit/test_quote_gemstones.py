# tests/unit/test_quote_gemstones.py
"""W2-06-14-16-11 open item #1: the quote PDF's "Steine" block was never
fed — ``render_quote_pdf`` accepted ``gemstones=`` but no caller of
``quote_delivery.render_quote_pdf_bytes`` supplied it. This covers the
wiring (``load_order_gemstones`` + threading it through), not the PDF
drawing itself (see tests/unit/test_pdf_gemstones.py for that).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import Gemstone, Quote, QuoteStatus
from goldsmith_erp.services import quote_delivery
from goldsmith_erp.services.pdf_service import PDFService

pytestmark = pytest.mark.asyncio


async def _quote_for(db_session, order, customer) -> Quote:
    quote = Quote(
        quote_number="KV-2026-9001",
        order_id=order.id,
        customer_id=customer.id,
        created_by=1,
        status=QuoteStatus.DRAFT,
        valid_until=datetime.utcnow() + timedelta(days=14),
        subtotal=100.0,
        tax_rate=19.0,
        tax_amount=19.0,
        total=119.0,
    )
    db_session.add(quote)
    await db_session.commit()
    return (
        await db_session.execute(
            select(Quote)
            .options(selectinload(Quote.line_items))
            .where(Quote.id == quote.id)
        )
    ).scalar_one()


async def test_load_order_gemstones_returns_none_without_order(db_session) -> None:
    assert await quote_delivery.load_order_gemstones(db_session, None) is None


async def test_load_order_gemstones_returns_none_when_order_has_none(
    db_session, sample_order
) -> None:
    assert (
        await quote_delivery.load_order_gemstones(db_session, sample_order.id) is None
    )


async def test_load_order_gemstones_returns_the_stones(
    db_session, sample_order
) -> None:
    gem = Gemstone(order_id=sample_order.id, type="Rubin", cost=30.0, quantity=1)
    db_session.add(gem)
    await db_session.commit()

    stones = await quote_delivery.load_order_gemstones(db_session, sample_order.id)

    assert stones is not None
    assert [s.type for s in stones] == ["Rubin"]


async def test_render_quote_pdf_bytes_threads_gemstones_through(
    db_session, sample_order, sample_customer, monkeypatch
) -> None:
    quote = await _quote_for(db_session, sample_order, sample_customer)
    gem = Gemstone(order_id=sample_order.id, type="Smaragd", cost=15.0, quantity=1)
    db_session.add(gem)
    await db_session.commit()
    stones = await quote_delivery.load_order_gemstones(db_session, quote.order_id)

    captured: dict = {}
    original = PDFService.render_quote_pdf

    def spy(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(PDFService, "render_quote_pdf", staticmethod(spy))

    quote_delivery.render_quote_pdf_bytes(quote, sample_customer, gemstones=stones)

    assert captured["gemstones"] is not None
    assert captured["gemstones"][0].type == "Smaragd"
