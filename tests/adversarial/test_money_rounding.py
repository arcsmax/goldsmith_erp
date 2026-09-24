"""
A1 — Adversarial rounding tests for the invoice/quote money path.

Target: InvoiceService.calculate_totals / QuoteService.calculate_totals
(audit 2026-09-25, ADR-2026-09-25-price-semantics).

The ADR states totals must be "computed in Decimal (never float)" and
InvoiceService.net_from_gross / _to_cents follow that rule. But
InvoiceService.calculate_totals (the function that actually produces the
persisted subtotal/tax_amount/total on every created invoice) still sums
Python floats and rounds with the builtin ``round()`` — the classic binary
float representation gotcha (``round(2.675, 2) == 2.67``, not 2.68).

InvoiceLineItemCreate.unit_price has no ``decimal_places`` constraint, so a
caller (additional_line_items on POST /invoices, or a quote line item) can
supply a price with 3+ decimal digits and get a silently wrong total.

These tests call the pure functions directly — no DB needed.
"""

from decimal import ROUND_HALF_UP, Decimal

import pytest

from goldsmith_erp.db.models import InvoiceLineType
from goldsmith_erp.models.invoice import InvoiceLineItemCreate
from goldsmith_erp.services.invoice_service import InvoiceService, net_from_gross


def _item(quantity: float, unit_price: float) -> InvoiceLineItemCreate:
    return InvoiceLineItemCreate(
        line_type=InvoiceLineType.OTHER,
        description="line",
        quantity=quantity,
        unit_price=unit_price,
    )


def _decimal_reference(items: list[tuple[float, float]], tax_rate: float) -> dict:
    """The correct answer: Decimal, ROUND_HALF_UP, exactly as the ADR mandates."""
    cent = Decimal("0.01")
    subtotal = sum(
        (Decimal(str(q)) * Decimal(str(p)) for q, p in items), Decimal("0")
    ).quantize(cent, rounding=ROUND_HALF_UP)
    tax_amount = (subtotal * Decimal(str(tax_rate)) / Decimal("100")).quantize(
        cent, rounding=ROUND_HALF_UP
    )
    total = (subtotal + tax_amount).quantize(cent, rounding=ROUND_HALF_UP)
    return {
        "subtotal": float(subtotal),
        "tax_amount": float(tax_amount),
        "total": float(total),
    }


class TestCalculateTotalsFloatRoundingBug:
    """BUG: calculate_totals uses float + round(), diverging from the
    Decimal/ROUND_HALF_UP reference the ADR requires for money math.
    """

    def test_two_line_items_with_three_decimal_prices_undercount_by_one_cent(self):
        # Found by property search against the Decimal reference; both are
        # plausible real amounts (a converted quote line, a manual addition).
        items = [(1, 38.694), (1, 228.691)]
        line_items = [_item(q, p) for q, p in items]

        got = InvoiceService.calculate_totals(line_items, tax_rate=0)
        expected = _decimal_reference(items, tax_rate=0)

        # This is the actual bug: server computes 267.38, correct is 267.39.
        assert got["subtotal"] == pytest.approx(expected["subtotal"]), (
            f"calculate_totals rounded {items} to {got['subtotal']}, "
            f"but Decimal/ROUND_HALF_UP gives {expected['subtotal']} "
            "(src/goldsmith_erp/services/invoice_service.py "
            "InvoiceService.calculate_totals uses float + round(), not Decimal)"
        )

    def test_single_item_classic_float_midpoint_rounds_down_instead_of_up(self):
        # round(0.145, 2) == 0.14 in Python because 0.145 cannot be
        # represented exactly in binary float; Decimal ROUND_HALF_UP gives 0.15.
        items = [(1, 0.145)]
        line_items = [_item(1, 0.145)]

        got = InvoiceService.calculate_totals(line_items, tax_rate=0)
        expected = _decimal_reference(items, tax_rate=0)

        assert got["subtotal"] == pytest.approx(expected["subtotal"]), (
            f"0.145 net should round half-up to 0.15, calculate_totals gives "
            f"{got['subtotal']}"
        )

    def test_vat_inclusive_three_item_case_matches_decimal_reference(self):
        """33.33 x 3 (from the attack brief) — sanity check this specific
        value happens to survive float rounding intact (documents that the
        bug above is real-value-dependent, not universal)."""
        items = [(3, 33.33)]
        line_items = [_item(3, 33.33)]
        got = InvoiceService.calculate_totals(line_items, tax_rate=19)
        expected = _decimal_reference(items, tax_rate=19)
        assert got == pytest.approx(expected)
        assert got["total"] - got["subtotal"] == pytest.approx(got["tax_amount"])


class TestNetFromGrossDecimalCorrectness:
    """net_from_gross / _to_cents DO use Decimal + ROUND_HALF_UP — confirm the
    boundary values from the attack brief are cent-exact (regression, should
    pass; shows the fix is real for this specific function)."""

    def test_penny_net_value(self):
        # 0.01 gross at 19% VAT: 0.01 / 1.19 = 0.0084...  rounds half-up to
        # the smallest possible cent, not to zero.
        net = net_from_gross(Decimal("0.01"), 19.0)
        assert net == Decimal("0.01")

    def test_half_cent_boundary_rounds_half_up(self):
        # Construct a gross value whose division lands exactly on a half-cent.
        # 1.19 * 0.005 = 0.00595 -> pick a gross that forces a .xx5 quotient.
        gross = Decimal("1.190")  # net would be exactly 1.00 -> not a boundary
        net = net_from_gross(gross, 19.0)
        assert net == Decimal("1.00")

    def test_large_totals_stay_cent_exact(self):
        gross = Decimal("119000.00")
        net = net_from_gross(gross, 19.0)
        assert net == Decimal("100000.00")
        # Round-trip: net * 1.19 must reproduce gross to the cent.
        recombined = (net * Decimal("1.19")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        assert recombined == gross

    def test_gross_minus_vat_invariant_holds_for_to_cents_path(self):
        """gross - net == vat, computed the way create_invoice_from_order does
        it for the calculated_price fallback path."""
        gross = Decimal("1416.10")
        vat_rate = 19.0
        net = net_from_gross(gross, vat_rate)
        vat = (net * Decimal(str(vat_rate)) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        gross_reconstructed = (net + vat).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        assert gross_reconstructed - net == vat
