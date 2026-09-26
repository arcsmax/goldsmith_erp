# ADR 2026-09-25: Price semantics on the order-to-invoice money path

Status: accepted (fix wave 1). Findings: BE-01, BE-02, BE-03, BE-04, BE-05, BE-17
(docs/review/2026-09-25/03-backend-correctness.md).

## Context

`Order.price` had no defined meaning. Quote conversion wrote the quote's gross
total into it, and invoice creation treated it as net, so VAT was charged twice
(1,190.00 became 1,416.10). When an order had a cost breakdown, the invoice billed
purchase cost and dropped the margin. The Altgold credit was a negative line that
crashed validation and, if allowed, would have shrunk the VAT base. Aware
datetimes from the browser crashed `InvoiceCreate`, and `PUT /invoices/{id}` could
set any status.

## Decisions

1. **`Order.price` and every order/quote line amount are NET (excluding VAT).**
   Quote conversion writes `quote.subtotal` (net) to `Order.price`. If only a gross
   figure exists (`Order.calculated_price`, which `CostCalculationService` stores
   gross), net is derived as `gross / (1 + vat_rate/100)` with `Decimal` and
   `ROUND_HALF_UP` to cents (`invoice_service.net_from_gross`), never float.
2. **Invoices bill the agreed price, never purchase cost.** Order of precedence:
   (a) line items of the CONVERTED quote linked to the order, (b) `Order.price`
   (net), (c) `Order.calculated_price` converted to net. If none exists, invoice
   creation fails with 422 instead of billing cost or 0.00. The cost breakdown
   stays internal (Soll/Ist).
3. **The Altgold credit is a post-tax deduction.** VAT is computed on the full sale
   price. The invoice reports net, VAT, gross (`total`), `scrap_gold_credit` and
   `amount_due = total - credit` (negative means a payout to the customer; it is
   not floored, so nothing is hidden). No negative line item is written.
   **The Steuerberater must confirm this treatment** (trade-in as a separate
   purchase / Tausch mit Baraufgabe) before production use.
4. **API datetimes are normalised at the schema boundary.** The existing codebase
   convention is naive UTC (`models/repair.py::_strip_tzinfo`; all columns are
   `TIMESTAMP WITHOUT TIME ZONE` and asyncpg refuses aware values there). So aware
   input is converted to UTC and stored naive; naive input is read as UTC. The
   shared type is `models/_common.py::UtcNaiveDatetime`. This deviates from the
   brief's "timezone-aware UTC" wording on purpose: switching to aware values needs
   a column migration (`db/models.py`, out of scope for this wave).
5. **`status` is removed from `InvoiceUpdate`** (extra fields are forbidden, so a
   stray `status` gets a loud 422, not a silent no-op). Transitions go through
   `POST /send` (DRAFT to SENT, INVOICE_EDIT), `POST /mark-paid` (INVOICE_EDIT) and
   `POST /cancel` (INVOICE_DELETE). PUT on a PAID or CANCELLED invoice returns 409.
6. **Quote conversion (BE-17):** a quote built from an existing order confirms that
   order (price set to the quote's net, status raised to CONFIRMED only if it was
   DRAFT/NEW) instead of creating a duplicate. Expired quotes (`valid_until` in the
   past) cannot be converted. A quote cannot reference another customer's order.

## Alternative considered

Rename `Order.price` to gross (`price_gross`) and divide by (1 + rate) in the
invoice fallback. That matches consumer-facing PAngV price display, but it needs a
column rename plus migration, and every net-based quote/invoice line would still
have to convert. A follow-up could add explicit `price_net` + `vat_rate` columns.

## Consequences and open items

- `CostCalculationService.update_order_calculated_price` still writes the GROSS
  `final_price` into `Order.price` when it is empty (`cost_calculation_service.py`
  ~line 433). Under this ADR that must write the net `subtotal_with_margin`.
  Until that's fixed, such orders are billed with VAT on top of a gross figure.
- `comparison_service` compares `calculated_price` (gross) with `price` (net).
- Existing rows may hold gross values in `Order.price` (converted quotes). They
  need a one-off data review before go-live.
- The invoice PDF (`pdf_service.py`) and the frontend don't yet show
  `scrap_gold_credit`/`amount_due`. The frontend cancel button still uses
  PUT `{status}` and must switch to `POST /cancel`.
