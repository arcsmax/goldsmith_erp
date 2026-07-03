# tests/unit/test_quote_line_items.py
"""
Unit tests for QuoteService line-item CRUD + total recompute
(editable-quotes plan, Task 1).

Covers:
- add_line_item / update_line_item / delete_line_item: totals recomputed
  from ALL current line items via QuoteService.calculate_totals (never
  hand-rolled) after every mutation.
- Editing is gated to quote.status == DRAFT: QuoteNotEditableError (a
  ValueError subclass, mirrors InvalidCostChangeStateError -> 409) on a
  SENT quote for all three operations.
- Unknown quote_id / item_id: QuoteNotFoundError / QuoteLineItemNotFoundError
  (both ValueError subclasses, mirrors *NotFoundError -> 404) for all three
  operations.
- The update_quote tax_rate recompute bug fix: changing tax_rate on a DRAFT
  quote now recomputes subtotal/tax_amount/total from existing line items;
  the same change on a non-DRAFT quote leaves totals untouched (recompute
  gated on the pre-update status, matching the line-item edit gate).
"""
import pytest

from goldsmith_erp.db.models import Customer, QuoteLineType, User
from goldsmith_erp.models.quote import QuoteCreate, QuoteLineItemCreate, QuoteUpdate
from goldsmith_erp.services.quote_service import (
    QuoteLineItemNotFoundError,
    QuoteNotEditableError,
    QuoteNotFoundError,
    QuoteService,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_draft_quote(
    db_session,
    customer: Customer,
    user: User,
    line_items: list[QuoteLineItemCreate],
    tax_rate: float = 19.0,
):
    """Create a DRAFT quote with the given line items via the real service —
    exercises the same path production code uses instead of hand-inserting
    ORM rows."""
    quote = await QuoteService.create_quote(
        db_session,
        QuoteCreate(
            customer_id=customer.id,
            tax_rate=tax_rate,
            additional_line_items=line_items,
        ),
        user,
    )
    return quote


def _line_item(
    quantity: float, unit_price: float, description: str = "Position"
) -> QuoteLineItemCreate:
    return QuoteLineItemCreate(
        line_type=QuoteLineType.LABOR,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
    )


# ---------------------------------------------------------------------------
# add_line_item
# ---------------------------------------------------------------------------


class TestAddLineItem:
    async def test_add_line_item_recomputes_totals(
        self, db_session, sample_customer, sample_user
    ):
        quote = await _create_draft_quote(
            db_session,
            sample_customer,
            sample_user,
            [_line_item(2.0, 50.0)],  # subtotal 100, tax 19, total 119
        )
        assert quote.subtotal == pytest.approx(100.0)

        updated = await QuoteService.add_line_item(
            db_session,
            quote.id,
            _line_item(1.0, 200.0, "Gold"),
            sample_user,
        )

        assert len(updated.line_items) == 2
        assert updated.subtotal == pytest.approx(300.0)  # 100 + 200
        assert updated.tax_amount == pytest.approx(57.0)  # 300 * 0.19
        assert updated.total == pytest.approx(357.0)
        new_item = next(li for li in updated.line_items if li.description == "Gold")
        assert new_item.total == pytest.approx(200.0)

    async def test_add_line_item_on_non_draft_quote_raises_conflict(
        self, db_session, sample_customer, sample_user
    ):
        quote = await _create_draft_quote(
            db_session, sample_customer, sample_user, [_line_item(1.0, 10.0)]
        )
        await QuoteService.send_quote(db_session, quote.id, sample_user)

        with pytest.raises(QuoteNotEditableError, match="Nur Entwürfe"):
            await QuoteService.add_line_item(
                db_session, quote.id, _line_item(1.0, 5.0), sample_user
            )

    async def test_add_line_item_unknown_quote_raises_not_found(
        self, db_session, sample_user
    ):
        with pytest.raises(QuoteNotFoundError):
            await QuoteService.add_line_item(
                db_session, 999_999, _line_item(1.0, 5.0), sample_user
            )


# ---------------------------------------------------------------------------
# update_line_item
# ---------------------------------------------------------------------------


class TestUpdateLineItem:
    async def test_update_line_item_recomputes_totals(
        self, db_session, sample_customer, sample_user
    ):
        quote = await _create_draft_quote(
            db_session,
            sample_customer,
            sample_user,
            [_line_item(2.0, 50.0)],  # subtotal 100
        )
        item_id = quote.line_items[0].id

        updated = await QuoteService.update_line_item(
            db_session,
            quote.id,
            item_id,
            _line_item(3.0, 60.0, "Angepasste Arbeit"),
            sample_user,
        )

        assert len(updated.line_items) == 1
        assert updated.line_items[0].description == "Angepasste Arbeit"
        assert updated.line_items[0].total == pytest.approx(180.0)  # 3 * 60
        assert updated.subtotal == pytest.approx(180.0)
        assert updated.tax_amount == pytest.approx(34.2)  # 180 * 0.19
        assert updated.total == pytest.approx(214.2)

    async def test_update_line_item_on_non_draft_quote_raises_conflict(
        self, db_session, sample_customer, sample_user
    ):
        quote = await _create_draft_quote(
            db_session, sample_customer, sample_user, [_line_item(1.0, 10.0)]
        )
        item_id = quote.line_items[0].id
        await QuoteService.send_quote(db_session, quote.id, sample_user)

        with pytest.raises(QuoteNotEditableError):
            await QuoteService.update_line_item(
                db_session, quote.id, item_id, _line_item(2.0, 20.0), sample_user
            )

    async def test_update_line_item_unknown_quote_raises_not_found(
        self, db_session, sample_user
    ):
        with pytest.raises(QuoteNotFoundError):
            await QuoteService.update_line_item(
                db_session, 999_999, 1, _line_item(1.0, 5.0), sample_user
            )

    async def test_update_line_item_unknown_item_raises_not_found(
        self, db_session, sample_customer, sample_user
    ):
        quote = await _create_draft_quote(
            db_session, sample_customer, sample_user, [_line_item(1.0, 10.0)]
        )

        with pytest.raises(QuoteLineItemNotFoundError):
            await QuoteService.update_line_item(
                db_session, quote.id, 999_999, _line_item(1.0, 5.0), sample_user
            )


# ---------------------------------------------------------------------------
# delete_line_item
# ---------------------------------------------------------------------------


class TestDeleteLineItem:
    async def test_delete_line_item_recomputes_totals(
        self, db_session, sample_customer, sample_user
    ):
        quote = await _create_draft_quote(
            db_session,
            sample_customer,
            sample_user,
            [_line_item(2.0, 50.0, "Arbeit"), _line_item(1.0, 200.0, "Material")],
        )
        assert quote.subtotal == pytest.approx(300.0)
        material_item_id = next(
            li.id for li in quote.line_items if li.description == "Material"
        )

        updated = await QuoteService.delete_line_item(
            db_session, quote.id, material_item_id, sample_user
        )

        assert len(updated.line_items) == 1
        assert updated.line_items[0].description == "Arbeit"
        assert updated.subtotal == pytest.approx(100.0)
        assert updated.tax_amount == pytest.approx(19.0)
        assert updated.total == pytest.approx(119.0)

    async def test_delete_line_item_on_non_draft_quote_raises_conflict(
        self, db_session, sample_customer, sample_user
    ):
        quote = await _create_draft_quote(
            db_session, sample_customer, sample_user, [_line_item(1.0, 10.0)]
        )
        item_id = quote.line_items[0].id
        await QuoteService.send_quote(db_session, quote.id, sample_user)

        with pytest.raises(QuoteNotEditableError):
            await QuoteService.delete_line_item(
                db_session, quote.id, item_id, sample_user
            )

    async def test_delete_line_item_unknown_quote_raises_not_found(
        self, db_session, sample_user
    ):
        with pytest.raises(QuoteNotFoundError):
            await QuoteService.delete_line_item(db_session, 999_999, 1, sample_user)

    async def test_delete_line_item_unknown_item_raises_not_found(
        self, db_session, sample_customer, sample_user
    ):
        quote = await _create_draft_quote(
            db_session, sample_customer, sample_user, [_line_item(1.0, 10.0)]
        )

        with pytest.raises(QuoteLineItemNotFoundError):
            await QuoteService.delete_line_item(
                db_session, quote.id, 999_999, sample_user
            )


# ---------------------------------------------------------------------------
# update_quote — tax_rate recompute bug fix
# ---------------------------------------------------------------------------


class TestUpdateQuoteTaxRateRecompute:
    async def test_tax_rate_change_on_draft_recomputes_totals(
        self, db_session, sample_customer, sample_user
    ):
        quote = await _create_draft_quote(
            db_session,
            sample_customer,
            sample_user,
            [_line_item(2.0, 50.0)],  # subtotal 100, tax_rate 19 -> tax 19, total 119
            tax_rate=19.0,
        )
        assert quote.tax_amount == pytest.approx(19.0)

        updated = await QuoteService.update_quote(
            db_session, quote.id, QuoteUpdate(tax_rate=7.0), sample_user
        )

        assert updated is not None
        assert updated.subtotal == pytest.approx(100.0)  # unchanged
        assert updated.tax_rate == pytest.approx(7.0)
        assert updated.tax_amount == pytest.approx(7.0)  # 100 * 0.07
        assert updated.total == pytest.approx(107.0)

    async def test_tax_rate_change_on_non_draft_quote_does_not_recompute(
        self, db_session, sample_customer, sample_user
    ):
        """Documents the gate's exact boundary: the plan says 'only if
        DRAFT' — a SENT quote's tax_rate field still updates (update_quote's
        existing behavior for non-CONVERTED quotes) but totals are left as
        they were, since a legally-relevant sent quote's amounts must not
        silently change."""
        quote = await _create_draft_quote(
            db_session,
            sample_customer,
            sample_user,
            [_line_item(2.0, 50.0)],
            tax_rate=19.0,
        )
        await QuoteService.send_quote(db_session, quote.id, sample_user)

        updated = await QuoteService.update_quote(
            db_session, quote.id, QuoteUpdate(tax_rate=7.0), sample_user
        )

        assert updated is not None
        assert updated.tax_rate == pytest.approx(7.0)
        assert updated.tax_amount == pytest.approx(19.0)  # stale on purpose
        assert updated.total == pytest.approx(119.0)
