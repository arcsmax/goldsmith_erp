# ADR 2026-09-25: Exact money (NUMERIC/Decimal) and timezone-aware datetimes

Status: accepted (fix wave 3). Findings: BE-14, BE-15
(docs/review/2026-09-25/03-backend-correctness.md, section C). Builds on
ADR-2026-09-25-price-semantics.md.

## Context

Every money column was `Float` and the arithmetic used Python `round()`
(banker's rounding on binary floats), so printed invoices could be off by a
cent and `_round_price(244.50)` returned 243.99. All but three datetime
columns were `TIMESTAMP WITHOUT TIME ZONE`, the code compared against the
naive and deprecated `datetime.utcnow()`, and aware browser input had to be
stripped at every schema (`UtcNaiveDatetime`, wave 1).

## Decision 1: money is NUMERIC in the DB and Decimal in Python (BE-14)

Migration `20260925_be14_numeric` converts 58 Float columns in place
(`USING round(col::numeric, scale)`):

| Kind | Type | Columns |
|---|---|---|
| Money (EUR) | `NUMERIC(12, 2)` | prices, costs, hourly rates, labor cost, invoice/quote subtotal/tax/total, line unit price/total, scrap-gold value, repair estimates, consultation budget, cost-change amounts, estimate totals |
| Weight / quantity | `NUMERIC(12, 3)` | all `*_weight_g`, `stock`, `min_stock`, gemstone carat, invoice/quote line quantity |
| Price per gram | `NUMERIC(12, 4)` | metal purchase, material usage, scrap gold, metal price history |
| Percentage | `NUMERIC(5, 2)` | VAT/tax rates, profit margin, scrap percentage |

Deliberately left `Float`: body measurements (ring size, chain and bracelet
length, customer measurements), hours (`labor_hours`, `actual_hours`,
estimate hours), activity duration, fine-content ratio. They are
measurements or ratios, not money, and no document prints them as money.

Rules:

- A setter listener in `db/models.py` converts every assignment to a Numeric
  column to `Decimal` (floats via `str`, so 0.1 stays 0.1) quantized to the
  column scale with `ROUND_HALF_UP`. SQLite and PostgreSQL therefore hold
  the same value, and a service that still assigns a float can't leave a
  float on the instance. Non-finite values raise.
- Services compute in `Decimal` (`models/_common.py`: `dec`, `money`).
  `money()` is the one cent rounding (`ROUND_HALF_UP`).
- `_round_price` is an explicit rule: cents below .50 give x.00, .50 and up
  give x.99.
- `calculate_totals` (invoice and quote now share the algorithm) keeps its
  float dict return value: it is the documented contract of the 1,200-case
  rounding sweep. The values are cent-exact and the ORM listener turns them
  back into `Decimal`.
- The metal spot-price tiers (API, Redis cache, DB history, fallback) keep a
  float contract for market data; the NUMERIC history row is converted at
  that boundary and every consumer that derives money from it uses Decimal.

### Wire contract

Pydantic money fields use `Money` / `Weight` / `Percent`
(`Annotated[Decimal, ...]`): input accepts numbers and numeric strings as
before, Python mode keeps `Decimal`, JSON output is a number, and the JSON
schema is rendered exactly like the old `float` field (same
`minimum`/`maximum` literals, same in validation and serialization mode, so
FastAPI does not split models into `-Input`/`-Output`). `make types`
produces no diff. Fields with a numeric default carry `validate_default=True`
so the default is a Decimal too.

Code that puts a model into a JSON column must use `model_dump(mode="json")`
(the cost-change `line_items` do).

## Decision 2: timezone-aware UTC datetimes (BE-15)

This supersedes decision 4 of ADR-2026-09-25-price-semantics (naive UTC).

- Migration `20260925_be15_tz` converts 110 naive columns to
  `TIMESTAMP WITH TIME ZONE` (`USING col AT TIME ZONE 'UTC'`, the stored
  values were UTC; the downgrade uses the same expression and is lossless).
  Three columns were already aware. `scan_logs.scanned_at` stays
  `TIMESTAMP WITHOUT TIME ZONE`: it is the RANGE partition key and
  PostgreSQL cannot change its type; `UtcDateTimeNaiveStorage` stores naive
  UTC there and returns aware UTC.
- Every datetime column uses `db/types.py::UtcDateTime` (DDL
  `DateTime(timezone=True)`): binds naive values as UTC, converts aware
  values to UTC, and always returns aware UTC. SQLite has no time zone
  type; it stores the naive UTC string and the type re-attaches UTC on read,
  so tests see the same aware values as PostgreSQL. A setter listener also
  normalises assignments, so a naive value never sits on an instance.
- `datetime.utcnow()` is gone from `src/` (164 call sites):
  `datetime.now(timezone.utc)`, or `core/timeutil.py::utcnow()` for column
  defaults. Naive datetimes built in code (`datetime(...)`,
  `datetime.combine`, `fromisoformat`) are made aware where they are
  compared.
- Schemas use `models/_common.py::UtcDatetime` (replaces
  `UtcNaiveDatetime`): aware input is converted to UTC, naive input is read
  as UTC for one release. Services that take datetimes from callers
  (time tracking stop/resume) apply the same rule with `ensure_utc`.
- People see Europe/Berlin: PDFs (`pdf_service._fmt_date`, the `local_date`
  Jinja filter in the invoice and Ankaufsbeleg templates), the Ankaufsbuch,
  labels, quote e-mails and the DATEV/Lexoffice dates go through
  `core/timeutil.py::format_local`. An invoice issued at 23:30 UTC on
  31 December prints 01.01. of the new year.

### Wire contract

The OpenAPI schema is unchanged (`string`, `format: date-time`). The JSON
*values* now carry the offset (`2026-09-25T08:00:00Z` instead of
`2026-09-25T08:00:00`). JavaScript's `Date` parsed the old naive strings as
browser-local time, so the frontend displayed UTC as local time; the offset
fixes that without a code change.

## Consequences

- Downgrading `20260925_be14_numeric` casts back to `double precision`;
  lossless for every value the upgrade produced.
- Tests compare money with `Decimal("…")` or `float(x) == approx(…)`;
  `pytest.approx` does not accept a Decimal against a float expectation.
- Tests still pass naive `datetime.utcnow()` values in many places; that
  works for one release (read as UTC). Remove the naive grace and the test
  usages in the next wave.
- Follow-ups: sum *rounded* line totals on invoices (BE-14 fix text; it
  changes the documented sweep reference, so it needs a product decision),
  and `price_net` + `vat_rate` columns (price-semantics ADR).
