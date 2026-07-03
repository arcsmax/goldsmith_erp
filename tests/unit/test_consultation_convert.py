"""Unit tests for ConsultationService.convert_consultation (Task 9).

Covers: convert-to-order links photos + is idempotent (409-equivalent
AlreadyConvertedError on a second call), convert-to-quote, and the
not-found guard.
"""

import io

import pytest
from fastapi import UploadFile
from PIL import Image

from goldsmith_erp.db.models import (
    ConsultationPhotoKind,
    ConsultationStatus,
    QuoteLineType,
)
from goldsmith_erp.models.consultation import ConsultationCreate
from goldsmith_erp.services.consultation_photo_service import ConsultationPhotoService
from goldsmith_erp.services.consultation_service import (
    AlreadyConvertedError,
    ConsultationService,
)
from goldsmith_erp.services.quote_service import QuoteService


def _jpeg_upload(name: str = "sketch.jpg") -> UploadFile:
    """A minimal valid 4x4 white JPEG, Pillow-generated in-memory."""
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="JPEG")
    buf.seek(0)
    return UploadFile(filename=name, file=buf)


@pytest.mark.asyncio
async def test_convert_to_order_links_photos_and_is_idempotent(
    db_session, sample_customer, sample_user, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )

    consultation = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(
            customer_id=sample_customer.id,
            piece_type="ring",
            wishes="Verlobungsring Rotgold 585, schlicht, 2mm",
        ),
        conducted_by_user_id=sample_user.id,
    )
    await ConsultationPhotoService.upload_photo(
        db_session,
        consultation_id=consultation.id,
        file=_jpeg_upload(),
        user_id=sample_user.id,
        kind=ConsultationPhotoKind.SKETCH,
    )
    await db_session.flush()

    converted = await ConsultationService.convert_consultation(
        db_session, consultation.id, "order", current_user=sample_user
    )
    assert converted.status is ConsultationStatus.CONVERTED
    assert converted.converted_order_id is not None
    assert len(converted.photos) == 1
    assert converted.photos[0].order_id == converted.converted_order_id

    with pytest.raises(AlreadyConvertedError) as exc_info:
        await ConsultationService.convert_consultation(
            db_session, consultation.id, "order", current_user=sample_user
        )
    assert exc_info.value.order_id == converted.converted_order_id
    assert exc_info.value.quote_id is None


@pytest.mark.asyncio
async def test_convert_to_quote(db_session, sample_customer, sample_user):
    consultation = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id, wishes="Anhänger"),
        conducted_by_user_id=sample_user.id,
    )
    converted = await ConsultationService.convert_consultation(
        db_session, consultation.id, "quote", current_user=sample_user
    )
    assert converted.converted_quote_id is not None
    assert converted.converted_order_id is None
    assert converted.status is ConsultationStatus.CONVERTED

    with pytest.raises(AlreadyConvertedError) as exc_info:
        await ConsultationService.convert_consultation(
            db_session, consultation.id, "quote", current_user=sample_user
        )
    assert exc_info.value.quote_id == converted.converted_quote_id
    assert exc_info.value.order_id is None


@pytest.mark.asyncio
async def test_convert_unknown_consultation_raises(db_session, sample_user):
    with pytest.raises(ValueError, match="not found"):
        await ConsultationService.convert_consultation(
            db_session, 999999, "order", current_user=sample_user
        )


@pytest.mark.asyncio
async def test_convert_to_quote_with_budget_seeds_estimate_line_item(
    db_session, sample_customer, sample_user
):
    """Bug fix: converting used to produce a frozen 0 EUR quote shell,
    dropping budget_min/budget_max/piece_type entirely. Now a single OTHER
    line item is seeded from the budget so the quote starts with a real,
    editable estimate instead of nothing."""
    consultation = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(
            customer_id=sample_customer.id,
            piece_type="ring",
            wishes="Verlobungsring",
            budget_min=1500,
            budget_max=2500,
        ),
        conducted_by_user_id=sample_user.id,
    )
    converted = await ConsultationService.convert_consultation(
        db_session, consultation.id, "quote", current_user=sample_user
    )
    assert converted.converted_quote_id is not None

    quote = await QuoteService.get_quote(
        db_session, converted.converted_quote_id, current_user=sample_user
    )
    assert quote is not None
    assert len(quote.line_items) == 1
    line_item = quote.line_items[0]
    assert line_item.line_type is QuoteLineType.OTHER
    assert line_item.unit_price == 1500
    assert "ring" in line_item.description
    assert "1500" in line_item.description
    assert "2500" in line_item.description
    assert quote.subtotal == 1500


@pytest.mark.asyncio
async def test_convert_to_quote_without_budget_still_seeds_line_item(
    db_session, sample_customer, sample_user
):
    """No budget on the consultation still yields exactly one labeled line
    item (unit_price 0.0, total 0) rather than an empty quote — the
    goldsmith gets a line to edit instead of nothing at all."""
    consultation = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(
            customer_id=sample_customer.id,
            piece_type="pendant",
            wishes="Anhänger",
        ),
        conducted_by_user_id=sample_user.id,
    )
    converted = await ConsultationService.convert_consultation(
        db_session, consultation.id, "quote", current_user=sample_user
    )
    assert converted.converted_quote_id is not None

    quote = await QuoteService.get_quote(
        db_session, converted.converted_quote_id, current_user=sample_user
    )
    assert quote is not None
    assert len(quote.line_items) == 1
    line_item = quote.line_items[0]
    assert line_item.unit_price == 0.0
    assert "pendant" in line_item.description
    assert quote.subtotal == 0
    assert quote.total == 0


@pytest.mark.asyncio
async def test_convert_to_order_branch_unchanged(
    db_session, sample_customer, sample_user
):
    """Regression: the order branch does not build any line items and is
    unaffected by the quote branch's estimate-line-item seeding — orders
    keep their title/description-only shape."""
    consultation = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(
            customer_id=sample_customer.id,
            piece_type="ring",
            wishes="Verlobungsring",
            budget_min=1500,
            budget_max=2500,
        ),
        conducted_by_user_id=sample_user.id,
    )
    converted = await ConsultationService.convert_consultation(
        db_session, consultation.id, "order", current_user=sample_user
    )
    assert converted.converted_order_id is not None
    assert converted.converted_quote_id is None
    assert converted.status is ConsultationStatus.CONVERTED
