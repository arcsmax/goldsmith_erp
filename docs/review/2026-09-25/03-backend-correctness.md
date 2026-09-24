# Review 03: Backend Correctness, Data Model and Reliability

**Date:** 2026-09-24 | **HEAD:** `73fff19` (main) | **Reviewer:** backend review agent (read-only)

## Scope and method

- **Scope:** `src/goldsmith_erp/` (services, routers, `db/models.py`, core/pubsub/cache, `main.py`, system monitor), `alembic/versions/`, deployment commands in `podman-compose*.yml`. Security and GDPR belong to other agents and appear here only when they are also correctness bugs.
- **Method:**
  1. Re-verified the April reviews (`docs/review/2026-04-23/01`, `05`).
  2. Read the money path end to end: quote, order, cost calc, metal inventory, scrap gold, invoice, DATEV.
  3. Read the time-tracking and notification paths.
  4. Grepped for transaction, except, timezone and number-generation patterns.
  5. Checked the key claims empirically in the project venv (pydantic, rounding), outside the repo tree.
- **Files examined:** 160 backend `.py` files were in scope for the grep sweeps. About 45 were read in depth: all money services, `time_tracking_service`, `notification_service`, `system_monitor`, `pubsub`, `main`, `models.py`, the invoice/quote/time_entry schemas, 19 migrations, and 4 frontend call sites that feed backend inputs.

### Commands run (exit codes)

| Command | Exit | Result |
|---|---|---|
| `poetry run python -c "import fastapi, sqlalchemy"` (first attempt) | 1 | `ModuleNotFoundError`. The Poetry venv was empty at first; Poetry created `~/Library/Caches/pypoetry/virtualenvs/goldsmith-erp-DSjS342B-py3.11` (outside the repo). It was populated later, apparently by a parallel agent. |
| `cd src && poetry run pytest -q -x --co` (command as specified) | 0 | "collected 0 items". Running from `src/` misses `testpaths=["tests"]`. |
| `poetry run pytest -q --co` (repo root) | 0 | **1812 tests collected** in 0.74 s |
| `python -m pytest <repo>/tests -q -p no:cacheprovider -o addopts=""` (cwd = scratchpad, so SQLite test DBs don't land in the repo) | 0 (not captured by zsh; the summary shows 0 failures) | **1805 passed, 6 skipped, 1 xfailed, 63 warnings in 234.25 s** |
| `poetry run alembic heads` | 0 | single head `20260610_e1_gdpr_audit_nofk (head)` |
| `MIGRATION_DATABASE_URL=sqlite:///<scratch>/be03_drift.db alembic upgrade head` | failed | `ALTER TABLE customers ALTER COLUMN email_hash SET NOT NULL`: SQLite can't run migration `20260424_c1_pii_enc`. The chain is PostgreSQL-only. |
| `alembic check` | n/a | Not meaningful ("Target database is not up to date"); no PostgreSQL reachable (`docker ps` empty). **Drift check skipped.** |
| Empirical probes (venv python, scratchpad) | 0 | See BE-03, BE-04, BE-14: each claim was reproduced. |

`git status` was unchanged after all runs; only the pre-existing `frontend/.yarn/install-state.gz` is modified.

---

## A. Status of prior findings (2026-04-23)

| Prior finding | Status | Evidence now |
|---|---|---|
| Two parallel RBAC systems (`api/deps` vs `core/permissions`) | **FIXED** | `api/deps.py` has no `Permission` class. Routers use `core.permissions.require_permission_dep`, e.g. `metal_inventory.py:18`. |
| `AuditLoggingMiddleware` never registered | **FIXED** | `main.py:148-149` |
| `GET /time-tracking/user/{id}` missing decorator | **FIXED** | `time_tracking.py:121` |
| `/users/register` public | **FIXED** | `middleware/auth_required.py:35` |
| TimeTracking bare `db.commit()` with no rollback | **OPEN** | 10 bare commits in `time_tracking_service.py` (134, 181, 413, 450, 462, 486, 680, 697, 793, 886) |
| `create_notification` commits unconditionally and sends SMTP inline | **OPEN** | `notification_service.py:100`, `:107-113` |
| Blocking file I/O in async handlers | **OPEN** | `materials.py:370`, `scrap_gold.py:221`, `photo_service.py:135`, `consultation_photo_service.py:127` |
| `on_event("startup")`, no shutdown, task not cancelled | **OPEN** | `main.py:356-363` |
| One Redis subscription per WebSocket | **OPEN** | `main.py:310`, `:339` |
| metal_inventory broad `except Exception` leading to `detail=str(e)` | **OPEN** | `metal_inventory.py:94-96` |
| JWT extracted in 3+ places | **OPEN** | `auth_required.py:141`, `deps.py:20`, `auth.py:62`, `main.py:286` |
| system_monitor eagerly creates coroutines | **OPEN** | `system_monitor.py:316-321` |
| `sanitize_text` rejects "UPDATE ", "DELETE FROM", ... | **OPEN** | `models/order.py:59-72` (false 422s on legitimate text) |
| `publish_event` never raises, so fallback branches are dead | **OPEN** | `pubsub.py:42-59`; dead branches at `order_service.py:487-488` and in the time-tracking/metal `_safe_publish` |
| sync `sessionmaker` used for AsyncSession | **OPEN** | `db/session.py:3`, `:49` |
| `.dict()` (Pydantic v1 API) | **OPEN** | `order_service.py:190`, `:324` |
| Money as Float (P0) | **OPEN** | 70 `Float` columns; the only `Numeric` money column is `Activity.hourly_rate` (`models.py:678`) |
| Naive `DateTime` everywhere | **OPEN** | 3 `DateTime(timezone=True)` columns vs ~98 naive ones |
| `order_materials` FKs without `ondelete` | **OPEN** | `models.py:175-179` |
| No index on `orders.status` | **OPEN** | `models.py:461-463`; only `ix_orders_customer_deleted` (`models.py:3191`) |
| Unbounded `String` on Order/Material/User | **OPEN** | `models.py:458-459`, `643-647` |
| N+1 in notification scanners | **OPEN** | 4 per-(order × user) existence queries in `notification_service.py` |
| `alembic_backup/` stale dir | **OPEN** | `alembic_backup/env.py` still present |
| `db/seed_data.py` sync, unguarded | **OPEN** | file still present |
| `get_db` annotation wrong | **OPEN** | `db/session.py:58` |
| `v1_initial` uses `create_all` over the live ORM | **OPEN (mitigated)** | Later migrations use `*_if_not_exists` guards. Fresh-install schema still equals current ORM, not the migration history. |
| `list_orders_by_customer` unpaginated | **FIXED** | Removed; `get_orders(customer_id=, limit=)` (`order_service.py:132-159`) |
| Health endpoints leak exception text | **OPEN** (security agent) | `health.py:83`, `:99` |

**Net:** 5 fixed, 22 open. The April P0 on money-as-float is still open, and it is now the root cause of several of the findings below.

---

## B. Findings

### CRITICAL

#### BE-01: Converting a quote writes the GROSS total into `Order.price`, and the invoice then adds 19% VAT again
- **Evidence:**
  - `services/quote_service.py:918-926`
    ```python
    estimated_price = quote.total          # gross (subtotal + tax)
    new_order = OrderModel(title=order_title, description=quote.notes or "",
        price=estimated_price, status=OrderStatusEnum.CONFIRMED,
        customer_id=quote.customer_id)
    ```
  - `services/invoice_service.py:216-224`: when the order has no cost breakdown, `unit_price=round(order.price, 2)` becomes a **net** line. Then `calculate_totals` (`:129-131`) adds `tax_rate`.
  - `cost_calculation_service.py:135-141,433-434` confirms that `Order.price`/`calculated_price` are gross (VAT included).
- **Failure scenario:**
  1. Quote KV-2026-0001 is net 1,000.00 + VAT 190.00 = 1,190.00. It's approved and converted.
  2. The new order has no metal, labor or gemstone fields, so `order.price = 1190.00`.
  3. The order is completed and "Rechnung erstellen" runs.
  4. The invoice line is "Auftrag aus KV-..." at 1,190.00 net, VAT 226.10, **total 1,416.10**.
  5. The customer is overcharged 226.10 (19%). The same double VAT hits any order whose only price is the goldsmith-entered `price`.
- **Fix:**
  - Give `Order.price` an unambiguous meaning: store `price_net` and derive gross, or rename it to `price_gross` and divide by (1 + rate) in the fallback.
  - On convert, copy the quote line items to the order (or link invoice generation to the converted quote and bill *its* lines).
  - Add a regression test for quote → convert → complete → invoice.
- **Effort:** M | **Confidence:** high

#### BE-02: The invoice bills purchase cost and ignores the profit margin and the agreed price
- **Evidence:** `services/invoice_service.py:152-193`. The material line uses `material_cost_override or material_cost_calculated`, which is the inventory purchase cost set at `metal_inventory_service.py:564` and `cost_calculation_service.py:428`. The gemstone line uses `gemstone.cost`. The labor line uses `labor_hours × hourly_rate`. `profit_margin_percent` (default 40%, `models.py:501`) is never read, and neither is `order.price` once any breakdown field exists. `quote_service.py:223-307` copies the same logic.
- **Failure scenario:**
  1. The order has 500.00 material cost and 4 h × 75.
  2. `/calculate-cost` gives (800 × 1.40) × 1.19 = 1,332.80, rounded to **1,332.99** (`cost_calculation_service.py:123-141`). This is the price shown and agreed.
  3. The invoice comes out as 800.00 net + 152.00 VAT = **952.00**, so the shop loses 380.99 per order.
  4. The "labor" line uses the *estimated* `labor_hours` (no code path ever writes `labor_hours` from time entries), not the actual time worked.
- **Fix:**
  - Invoice lines should come from the agreed commercial document: the approved quote's lines, or `order.price` split into net/VAT, or cost × (1 + margin) per line.
  - Keep the cost breakdown for internal Soll/Ist, not for the customer bill.
  - Add a golden test: `invoice.total == order.price` (gross) when there's no quote.
- **Effort:** M | **Confidence:** high

### HIGH

#### BE-03: An Altgold (scrap gold) credit makes invoice creation crash, and the VAT treatment is probably wrong too
- **Evidence:**
  - `invoice_service.py:275-280` builds `InvoiceLineItemCreate(..., unit_price=round(-value_eur, 2))`.
  - `models/invoice.py:42-53` has `unit_price: float = Field(..., ge=0)` plus an explicit `if self.unit_price < 0: raise`.
  - Reproduced: `InvoiceLineItemCreate(unit_price=-250.0)` raises `ValidationError`. It's raised in the service, so it surfaces as a 500.
  - No test references `_build_scrap_gold_line_item`.
- **Failure scenario:** The customer trades in a ring. `ScrapGold` is SIGNED with `total_value_eur=702.00`. Clicking "Rechnung erstellen" returns HTTP 500, so an order with Altgold can never be invoiced. If someone "fixes" this by relaxing `ge=0`, the credit is netted *before* VAT (`calculate_totals` sums all lines, then applies the rate). That shrinks the VAT base by the credit. Under German practice (trade-in as a separate purchase / Tausch mit Baraufgabe), VAT is due on the full sale price, so VAT would be underpaid by 19% of the credit.
- **Fix:** Model the Altgold credit as a post-tax deduction: gross total − Ankauf = Zahlbetrag, with its own field and a separate Ankaufbeleg. Don't use a negative net line. Confirm the treatment with the Steuerberater. Add a test.
- **Effort:** M | **Confidence:** high (crash), medium (tax treatment)

#### BE-04: "Rechnung erstellen" from the Soll/Ist tab always returns 500 (timezone-aware due_date)
- **Evidence:**
  - `frontend/src/components/orders/SollIstTab.tsx:194-197` sends `due_date: due.toISOString()` (a `Z` suffix).
  - `models/invoice.py:106-111`:
    ```python
    def due_date_must_be_future(cls, v: datetime) -> datetime:
        if v <= datetime.utcnow():
    ```
  - Reproduced: this raises raw `TypeError: can't compare offset-naive and offset-aware datetimes`. Pydantic v2 doesn't wrap `TypeError`, so the result is a 500.
  - Tests only use naive dates (`tests/unit/test_invoice_service.py:41`).
- **Failure scenario:** The goldsmith opens a completed order, goes to Soll/Ist and clicks "Rechnung erstellen". The toast shows an error, and no invoice can be created from that entry point.
- **Fix:** One shared validator or annotated type (`UtcNaiveDatetime`) that normalizes aware values to naive UTC. `models/repair.py:20-31` already does this for repairs. Apply it to every datetime input schema (see BE-15).
- **Effort:** S | **Confidence:** high

#### BE-05: `PUT /invoices/{id}` can set any status, including cancelling a PAID invoice
- **Evidence:**
  - `models/invoice.py:122` has `status: Optional[InvoiceStatus]`.
  - `invoice_service.py:548-562` only blocks edits when the invoice is *already* CANCELLED, then runs `setattr(invoice, field, value)` for every field.
  - The router gates PUT with `INVOICE_EDIT` (`invoices.py:297-298`), while `/cancel` needs `INVOICE_DELETE` (`:348-349`).
- **Failure scenario:**
  1. Someone sends `PUT {"status":"cancelled"}` on invoice RE-2026-0042 (PAID). It succeeds, bypassing the "Bezahlte Rechnungen koennen nicht storniert werden" rule at `:656-663`.
  2. The duplicate check ignores CANCELLED (`:345`), so a second invoice for the same order can now be created. Double billing and a GoBD breach follow.
  3. `{"status":"paid"}` via PUT leaves `paid_date` NULL.
- **Fix:** Remove `status` from `InvoiceUpdate`, mirroring what `QuoteService.update_quote` already does at `quote_service.py:586-591`. Route transitions only through the mark-paid, cancel and send actions, with an explicit transition table.
- **Effort:** S | **Confidence:** high

#### BE-06: Order status is not a state machine and history is never recorded
- **Evidence:**
  - `order_service.py:330-399`: the only guards are the Punzierung check and CONFIRMED Pflichtfelder. `update(OrderModel).values(**update_data)` accepts any status.
  - `OrderStatusHistory` (`models.py:2938-2956`) is only referenced in the dead `db/repositories/order.py`, so it's never written.
  - New orders default to legacy `NEW` rather than `DRAFT` (`models.py:461-463`; `OrderCreate` has no status field).
  - `convert_quote` jumps straight to CONFIRMED without `validate_for_confirmation` (`quote_service.py:922-927`).
- **Failure scenario:**
  - A mis-tap moves DELIVERED to IN_PROGRESS. The order reappears in production lists, `completed_at` stays set, the invoice still exists, and the customer-portal progress bar goes backwards. Nobody can see who did it or when.
  - A converted quote creates a CONFIRMED order with no metal, alloy or deadline, which also skips the Punzierung guard because `alloy` is None.
- **Fix:**
  - Add an `ALLOWED_TRANSITIONS: dict[OrderStatusEnum, set[OrderStatusEnum]]` checked in `update_order`.
  - Write an `OrderStatusHistory` row in the same transaction.
  - Migrate `NEW` to `DRAFT`.
  - Run `validate_for_confirmation` in `convert_quote`, or create the order as DRAFT.
- **Effort:** M | **Confidence:** high

#### BE-07: Consuming metal a second time overwrites the order's material cost and weight
- **Evidence:** `metal_inventory_service.py:562-565`
  ```python
  if order:
      order.material_cost_calculated = allocation.total_cost
      order.actual_weight_g = usage_data.weight_used_g
  ```
- **Failure scenario:**
  1. Casting consumes 12 g of 750 (780.00), then sizing adds 1.5 g (97.50).
  2. The order now shows 97.50 material and 1.5 g actual weight, so the invoice material line (BE-02) says 97.50.
  3. `/calculate-cost` then *previews a fresh allocation* of `actual_weight_g × (1 + scrap%)` from the **remaining** stock (`cost_calculation_service.py:212-241`). That double-counts consumed metal, or returns 422 "Insufficient inventory" once the bar is used up.
- **Fix:** Derive material cost and weight as `SUM(material_usage.cost_at_time / weight_used_g) WHERE order_id=…` (or increment inside the locked transaction). Make cost calc use recorded usage when it exists and preview only for unconsumed estimates.
- **Effort:** S | **Confidence:** high

#### BE-08: AVERAGE costing takes the whole weight from the first batch
- **Evidence:** `metal_inventory_service.py:349-358` builds a single allocation `weight_allocated_g=required_weight_g` on `available_purchases[0]`. The lock re-check at `:498-504` then fails whenever that batch is smaller than the need.
- **Failure scenario:** Batch A has 10 g and batch B 100 g of GOLD_750. Consuming 50 g with AVERAGE gives 400 "Cannot consume 50g from purchase A: only 10.000g remaining (concurrent consume)", which is both wrong and a misleading message. When it does succeed, only batch A's `remaining_weight_g` drops, so per-batch stock and the FIFO/LIFO views drift from reality.
- **Fix:** For AVERAGE, spread the physical draw FIFO across batches while pricing at the weighted average. Add a multi-batch test.
- **Effort:** S | **Confidence:** high

#### BE-09: Reminder scanners re-fire every 5 minutes, and each firing emails the customer
- **Evidence:**
  - The dedup requires `Notification.is_read.is_(False)` (`notification_service.py:300-314`, `494-507`). It runs per staff user (`:299`, `:493`).
  - `PICKUP_READY` and `FITTING_REMINDER` are customer-email types (`:50-58`), and `create_notification` emails the customer on every row (`:107-113`).
  - The scan runs every 5 minutes (`system_monitor.py:42`), and prod runs `--workers 2` (`podman-compose.prod.yml:81`), with one monitor loop per worker (`main.py:356-360`).
  - `send_fitting_reminder` receives the internal staff message as `fitting_date` (`:678-682`).
- **Failure scenario:**
  1. There are 3 staff users, `EMAIL_NOTIFICATIONS_ENABLED=true`, and an order has been COMPLETED for 4 days.
  2. The customer gets 3 "abholbereit" emails per day (6 with two workers racing the dedup).
  3. Every time Anne marks hers read, another customer email goes out on the next tick.
  4. The fitting email shows "Ihr Termin: Anprobe fuer Auftrag #12 \"Verlobungsring…".
- **Fix:**
  - Dedup on (order, type, day) regardless of `is_read`.
  - Send customer email once per order event, driven by a `customer_notified_at` column, not per staff notification.
  - Run the monitor in exactly one process (a separate job, or a Redis/PG advisory lock).
  - Pass a real fitting date.
- **Effort:** M | **Confidence:** high

#### BE-10: The estimator prices labor from the sum of per-activity medians, not the median it shows
- **Evidence:**
  - `ml/labor_estimator.py:208-226` computes per-activity medians over *only* the orders that logged that activity ("no zero-filling").
  - `:255-258` computes `hours_p50 = median(total hours)`.
  - `services/estimator_service.py:174-178` sets `labor_cost_p50 = cost(suggested_activities)` and scales P20/P80 by `hours_x / hours_p50`.
- **Failure scenario:** 5 comparable rings each have Polieren 1.0 h, and one also has Gravur 2.0 h. The shown `hours_p50` is 1.0 h, but `suggested_activities` is {Polieren 1.0, Gravur 2.0}. So `labor_cost_p50` is 3 h × 75 = 225.00 instead of about 75.00, and the P80 cost is scaled up from the inflated base. That number flows into quote lines via EstimatorPanel.
- **Fix:** Price at `hours_p50 × blended rate`. Alternatively, zero-fill per-activity hours across the matched set and include only activities present in at least 50% of orders. Assert `Σ suggested ≈ hours_p50` in tests. (This may overlap with the "2 design decisions pending" noted in memory; it still needs resolving before quotes rely on it.)
- **Effort:** S | **Confidence:** high

#### BE-11: Scrap gold records can change after signing, and mixed metals are valued at the gold price
- **Evidence:**
  - `scrap_gold_service.py:75-113`: `add_item`/`remove_item` have no status guard; the router doesn't check either (`scrap_gold.py:119-135`).
  - `:116-132`: `calculate_and_update` sets `status = CALCULATED` unconditionally, even from SIGNED or CREDITED.
  - `:161-172`: `total_fine = sum(fine_content_g)` over gold, `ag*` and `pt950` items alike, multiplied by the single `gold_price_per_g`.
  - `ScrapGoldItemCreate.alloy` is an unvalidated `str` (`models/scrap_gold.py:25`). Unknown alloys get ratio 0.0 (`:29`), and PostgreSQL's enum then rejects the insert with a 500.
- **Failure scenario:**
  1. The customer signs for 20 g 585 (11.7 g fine × 60 = 702.00).
  2. Staff then add a 50 g ag925 chain. The total fine is 57.95 g × 60 = **3,477.00**, and the status drops back to CALCULATED while `signature_data` stays.
  3. The signed receipt PDF no longer matches the DB. If an invoice already credited 702, a regenerated invoice credits 3,477.
- **Fix:**
  - Lock items and price once SIGNED (409).
  - Keep per-metal totals with a per-metal price.
  - Validate `alloy` as `AlloyType`.
  - Never demote status in `calculate_and_update`.
  - Add a UNIQUE on `scrap_gold.order_id`, since the router's check-then-insert (`scrap_gold.py:108-111`) races.
- **Effort:** M | **Confidence:** high

#### BE-12: A double-tap on "Start" leaves the user with two running timers and a permanent 500
- **Evidence:**
  - `time_tracking_service.py:111-134` checks for a running entry, then inserts. There's no lock and no partial unique index: no `WHERE end_time IS NULL` index exists in the models or migrations.
  - `get_running_entry` uses `scalar_one_or_none()` (`:309-330`).
- **Failure scenario:** Two `POST /time-tracking/start` calls land within milliseconds (double-tap, or the bench tablet plus a phone). Both pass the check, so there are two open entries. From then on, `GET /running` and every `/start` raise `MultipleResultsFound`, a 500, until someone edits the DB. Time for both is counted twice in Soll/Ist.
- **Fix:** Add `CREATE UNIQUE INDEX uq_time_entries_one_running ON time_entries(user_id) WHERE end_time IS NULL` (plus the SQLite equivalent), map `IntegrityError` to 409, and use `.first()` defensively. Honour the `Idempotency-Key` the client already sends.
- **Effort:** S | **Confidence:** high

#### BE-13: DATEV/Lexoffice exports include DRAFT and CANCELLED invoices and book everything to the 19% account
- **Evidence:**
  - `api/routers/invoices.py:173-181` uses `list_invoices(..., limit=10_000, status=status_filter)`, where the filter is optional and defaults to all.
  - `accounting_export_service.py:187-197` writes every row as revenue `H` on `DATEV_REVENUE_ACCOUNT="8400"` (`:41`, SKR03 19% automatic account) regardless of `inv.tax_rate`.
  - `_DATEV_CREATED_DATE` is frozen at import time (`:50`).
- **Failure scenario:** The admin exports September without a filter. Two cancelled invoices (a PAID one cancelled via BE-05, or a normal storno) and a draft are booked as revenue, so the accountant files too much VAT. A 7%/0% invoice is booked on the 19% account.
- **Fix:** Export only SENT/PAID/OVERDUE by default, choose the account per `tax_rate`, export stornos as reversal bookings, and compute the created date per call.
- **Effort:** S | **Confidence:** high

#### BE-14: Float money and Python `round()` produce cent errors on legally binding documents
- **Evidence:**
  - Columns: `models.py:460-503` (Order), `1353-1356` (Invoice), `1408-1412` (lines), `1488-1491` (Quote); 70 `Float` columns in total.
  - `invoice_service.py:129-133` rounds the subtotal from *unrounded* line products, while each line is stored `round(q*p, 2)` (`:410`).
- **Failure scenario:**
  - Three lines at 1.005 each print as 1.00 + 1.00 + 1.00, but the invoice subtotal reads **3.01** (reproduced). The printed invoice doesn't add up.
  - `_round_price(244.50)` returns **243.99** because of banker's rounding (reproduced). `_round_price(243.49)` returns 243.00, silently discarding up to 0.49 per order.
- **Fix:** Use `Numeric(12,2)` columns and `Decimal` end to end with `quantize(Decimal("0.01"), ROUND_HALF_UP)`. Sum the *rounded* line totals. Replace `_round_price` with explicit, documented psychological-price rules. This is the April P0; it needs one migration.
- **Effort:** L | **Confidence:** high

### MEDIUM

#### BE-15: Timezone-aware inputs reach naive columns (asyncpg rejects them; SQLite tests pass)
- **Evidence:**
  - Only 3 `DateTime(timezone=True)` columns exist; about 98 are naive.
  - Only `models/repair.py:20-31` normalizes. Its comment says "asyncpg refuses to bind a tz-aware datetime there".
  - The frontend sends `Z` ISO strings for calendar events (`CalendarEventModal.tsx:63`) and consultation follow-ups (`SummaryStep.tsx:212`). They land in naive `CalendarEvent`/`Consultation.follow_up_at` (`models.py:2064`) with no normalizer.
- **Failure scenario:** On PostgreSQL, saving a consultation with a follow-up date, or a calendar event, can fail with `DataError ... can't subtract offset-naive and offset-aware datetimes`. It never shows up in CI because the tests use SQLite.
- **Fix:** Pick one convention: aware UTC columns, `DateTime(timezone=True)`, via migration. Add one normalizing annotated type for all input schemas and a PostgreSQL CI job.
- **Effort:** M | **Confidence:** medium (reasoned from the repair comment and asyncpg behaviour; not run against PostgreSQL)

#### BE-16: Sequential numbers (RE/KV/WG/REP) use unlocked MAX+1
- **Evidence:** `invoice_service.py:91-110`, `quote_service.py:144-162`, `valuation_service.py:32-56`, `repair_service.py:115-146` all use `SELECT max(number) LIKE 'RE-2026-%'`, then +1, with `datetime.utcnow().year`.
- **Failure scenario:**
  - Two invoices created at once get the same number, so the UNIQUE constraint (`models.py:1323`) raises IntegrityError, an unhandled 500. Nothing retries.
  - String MAX breaks at 10,000: "RE-2026-9999" > "RE-2026-10000", so MAX stays 9999 and every later create collides.
  - An invoice issued at 00:30 on 1 Jan (Berlin) gets the previous year's prefix.
  - The duplicate-active-invoice-per-order check (`:342-354`) races too; there's no partial unique index.
- **Fix:** Use a per-year counter table updated with `SELECT … FOR UPDATE` (or PostgreSQL sequences), derive the year in Europe/Berlin, and add a partial unique index `invoices(order_id) WHERE status <> 'cancelled'`.
- **Effort:** S | **Confidence:** high

#### BE-17: Quote workflow allows cross-customer quotes, duplicate orders on convert, and expired approvals
- **Evidence:**
  - `quote_service.py:390-409` validates the customer and the order separately but never checks `order.customer_id == quote_in.customer_id`.
  - `convert_quote` (`:921-934`) *always* creates a new order and overwrites `quote.order_id`, even if the quote was built from an existing order. The UI shows "In Auftrag umwandeln" for every approved quote (`QuotesPage.tsx:668-671`).
  - `approve_quote` accepts DRAFT (`:813`); `valid_until` is never checked; `QuoteStatus.EXPIRED` is never set; convert isn't locked.
- **Failure scenario:** The goldsmith creates order #65, builds KV-2026-0007 from it, approves it and converts it. Now order #66 exists as "Auftrag aus KV-2026-0007" at the gross price (BE-01) with no metal or deadline, and the link to #65 is lost. Work continues on #65, which never gets an invoice total from the quote.
- **Fix:** When `quote.order_id` is set, convert confirms that order instead of creating a new one. Enforce the same customer. Reject approval or conversion after `valid_until`, add an expiry job, and use `with_for_update` in convert.
- **Effort:** S | **Confidence:** high

#### BE-18: Editing a time entry can store negative or stale durations
- **Evidence:**
  - `time_tracking_service.py:438-449` recomputes duration from `update_data["end_time"] - entry.start_time` without checking `end > start`. `TimeEntryUpdate` (`models/time_entry.py:115-121`) has no cross-field validator, unlike `TimeEntryCreate` (`:100-110`).
  - `duration_minutes` and `end_time` can both be sent and conflict.
  - PUT with `end_time` on a *running* entry stops it without the stop-flow side effects (average duration, cost watch).
- **Failure scenario:** A correction sets `end_time` to 08:00 on an entry started at 09:00. The stored `duration_minutes` is −60, which lowers the order's `actual_hours`, the Soll/Ist and the estimator corpus.
- **Fix:** Add a validator for `end > start` and ≤ 24 h, reject explicit `duration_minutes` when an end time exists, and send "stop" through `stop_time_entry`.
- **Effort:** S | **Confidence:** high

#### BE-19: Interruptions never reduce time, and `actual_hours` is frozen at first completion
- **Evidence:**
  - Scan interruptions are stored with `duration_minutes=0` "sentinel" (`time_tracking_service.py:866-876`), and nothing ever updates them.
  - Net time in `MLDataService.auto_calculate_actual_hours` (`ml_data_service.py:332-344`) subtracts `SUM(interruptions)`, which is 0.
  - `actual_hours` is only computed when `is_completing` (`order_service.py:384-410`), so rework logged after COMPLETED is never counted.
- **Failure scenario:** A 3 h entry with a 45-minute Kundenanruf interruption still counts as 3 h. A ring reopened for resizing after completion keeps its old `actual_hours`, so the estimator (BE-10) learns understated durations.
- **Fix:** Close interruptions with an end timestamp (resume scan) and compute the duration. Recompute `actual_hours` on every entry stop or edit for the order (cheap aggregate).
- **Effort:** M | **Confidence:** high

#### BE-20: Real-time events are mostly published to channels nobody subscribes to, and Redis has no timeouts
- **Evidence:**
  - Published channels include `time_tracking_updates`, `material_updates`, `repair_updates`, `consultation_updates`, `metal_price_updates` and `anomaly_alerts`. The only WebSocket subscriptions are `order_updates` and `notifications:{id}` (`main.py:309`, `:338`).
  - `publish_event` swallows every error (`pubsub.py:42-59`), so the "notify on publish failure" paths (`order_service.py:477-520`, time-tracking `_safe_publish`) are dead.
  - The pool has no `socket_connect_timeout`/`socket_timeout` (`pubsub.py:23`), yet every authenticated request calls Redis for token revocation (`token_revocation.py:103-133`, fail-open).
  - If the subscription task dies, the WebSocket stays open and silent (`pubsub.py:94-100`).
- **Failure scenario:**
  - A timer switched on the bench tablet never updates the office dashboard live.
  - With Redis unreachable (packet drop rather than refused), each request can hang on connect, and each publish adds ≥1.5 s of retry sleep.
- **Fix:** Add a single `/ws/events` hub with one Redis subscriber per channel, make `publish_event` return a bool, set pool timeouts (e.g. 0.5 s connect, 1 s read), and close the WebSocket when its subscriber dies.
- **Effort:** M | **Confidence:** high

#### BE-21: The monitor loop shares one session across steps, and each worker runs its own copy
- **Evidence:**
  - `system_monitor.py:295-329` has one `AsyncSessionLocal()` for the health checks, the price refresh and 4 scans, with no `rollback()` after a caught exception.
  - `main.py:359` does `asyncio.create_task(...)` without keeping a reference or cancelling it on shutdown.
  - Prod runs 2 workers (see BE-09).
- **Failure scenario:** A DB error in `check_low_stock_alerts` leaves the PostgreSQL transaction aborted, so `pickup_reminders` and `fitting_reminders` in the same cycle fail with `InFailedSqlTransaction`. Health notifications and metal price history entries are duplicated per worker.
- **Fix:** Use a fresh session per step (or `await db.rollback()` in each `except`). Move to the `lifespan` pattern with a stored task and cancellation. Use a single-runner lock.
- **Effort:** S | **Confidence:** high

#### BE-22: The metal price feed silently treats USD as EUR and prices platinum at 999
- **Evidence:**
  - `metal_price_service.py:271`: `eur_rate = rates.get("EUR", 1.0) if base_currency == "USD" else 1.0`.
  - `:297`: the XPT (pure Pt) price is assigned to `PLATINUM_950` with no 0.95 factor.
  - `metal_inventory_service.py:146`: `price_per_gram=round(price_total / weight_g, 2)` truncates purchase cost to cents per gram.
- **Failure scenario:** If the API omits EUR, gold is recorded roughly 8% too high as "API" source, and the Altgold daily rate follows it. A 1 kg purchase at 65,432.10 stores 65.43/g, which drifts about 2 € on the batch.
- **Fix:** Raise when EUR is missing (the fallback chain takes over), apply fineness per metal type, and store `price_per_gram` as `Numeric(12,4)`.
- **Effort:** S | **Confidence:** high

#### BE-23: Invoice PDFs are rendered from the live customer record and lack mandatory §14 UStG fields
- **Evidence:**
  - `pdf_service.py:215ff` takes a `customer` object at render time. `Invoice` (`models.py:1309-1379`) stores no recipient name or address snapshot.
  - There's no Steuernummer/USt-IdNr setting and no Leistungsdatum field anywhere (grep over `pdf_service.py`, `config.py`, `models.py` returns nothing; only `WORKSHOP_NAME`/`WORKSHOP_CONTACT` exist in `config.py:150-156`).
- **Failure scenario:** The customer moves. Re-downloading a 2026 invoice now shows the 2027 address, and after GDPR anonymization it shows "deleted_user_…". Invoices are also missing required fields, so the customer's (or the shop's own) input tax deduction can be challenged.
- **Fix:** Snapshot the recipient block, seller tax ID and service date on the Invoice at creation, and store the rendered PDF (hash) at SENT.
- **Effort:** M | **Confidence:** high (missing fields), medium (legal impact; confirm with the Steuerberater)

### LOW

#### BE-24: Dead repository layer references columns that don't exist
- **Evidence:** `db/repositories/order.py:301,684-700` uses `Order.order_number`, `order_type="custom_jewelry"`, `priority`, etc. `Order` has no `order_number` (grep `models.py`). The code is imported only by tests (`tests/test_basic_setup.py:111`).
- **Failure scenario:** A developer reuses `OrderRepository.create_order` and gets an `AttributeError`/TypeError at runtime. It also misleads reviewers: "OrderStatusHistory is supported" is false (BE-06).
- **Fix:** Delete `db/repositories/order.py` (keep `customer.py`/`material.py` if used), or fix it and make it the single data-access path.
- **Effort:** S | **Confidence:** high

#### BE-25: Duplicate line-item builders in the invoice and quote services
- **Evidence:** `invoice_service.py:139-227` and `quote_service.py:222-307` are near-identical, including the hardcoded `hourly_rate or 75.0` (`invoice_service.py:175`, `quote_service.py:256`) instead of `settings.DEFAULT_HOURLY_RATE` (`config.py:182`), which `cost_calculation_service.py:324` uses.
- **Failure scenario:** The shop changes `DEFAULT_HOURLY_RATE` to 85. Pre-calculation uses 85, while quotes and invoices for orders with NULL `hourly_rate` still use 75. (The Order column default is 75.0, `models.py:497`, so in practice NULL is rare, but the three code paths already disagree.)
- **Fix:** One `LineItemBuilder` used by both services; read the rate from settings.
- **Effort:** S | **Confidence:** high

#### BE-26: List endpoints without limits, and stale test DBs in the repo root
- **Evidence:** No `limit`/`offset`/`page` in `calendar.py`, `customer_updates.py`, `handoffs.py`, `hallmarks.py`, `measurements.py`, `photos.py`, `metal_types.py` (most are per-order scoped). There are 9 `integration_test_*.db` and 8 `unit_test_*.db` files in the repo root and more in `src/`, because `tests/conftest.py:42-43` uses cwd-relative SQLite paths.
- **Failure scenario:** The calendar range endpoint returns an unbounded event list over large ranges. Stray DB files contain seeded test PII-like data and clutter `git status` risk.
- **Fix:** Add a `limit` cap to calendar; write test DBs to `tmp_path`/`tempfile`.
- **Effort:** S | **Confidence:** high

---

## C. Data-model assessment

| Entity | Fits the goldsmith workflow? | Gaps | Proposed change |
|---|---|---|---|
| **Order** | Partly. It has rich intake fields (alloy, ring size, fitting, Punzierung). | No human-readable order number (only int id; `order_number` exists only in the dead repository). No assignee or "who's at the bench" (only handoffs). Status is free to jump (BE-06). Price meaning (net/gross) is ambiguous (BE-01). `labor_hours` is never fed from time tracking. `title`/`description` are unbounded `String`. `deadline` is a naive DateTime although the UI sends a date. | Add `order_number` (Auftragsnummer, counter table), `assigned_to_user_id`, `price_net` + `vat_rate`, transition table + history, `deadline` as `Date`. |
| **Customer** | Yes (encrypted PII, measurements, no-gos). | Invoices don't snapshot the address (BE-23). | Snapshot the recipient block on Invoice/Quote. |
| **Quote / QuoteLineItem** | Yes as a document. | Lines aren't carried into the order or invoice. There's no expiry. Customer consistency with the order isn't enforced (BE-17). Money is Float. | `order_id` required on convert, lines copied or linked, expiry job, Numeric. |
| **Invoice / InvoiceLineItem** | No, not as a legally sound document. | Status is editable via PUT (BE-05). Lines come from cost fields (BE-02). No Altgold credit model (BE-03). No Leistungsdatum or seller tax ID (BE-23). No storno/credit-note entity. Float. | Immutable once SENT, `InvoiceCorrection`/Storno entity, `service_date`, snapshot fields, Numeric. |
| **TimeEntry / Interruption** | Mostly (scan switching, stale-timer guard). | No one-running-timer constraint (BE-12). Interruptions have no end or duration (BE-19). No overlap check for manual entries. `id` is `String(36)` vs PostgreSQL UUID (April P1). | Partial unique index, `resumed_at` on Interruption, overlap validator. |
| **MetalPurchase / MaterialUsage** | Yes (batches, FIFO/LIFO, alloy guard, row locks). | Wrong AVERAGE draw (BE-08). The order aggregate is overwritten (BE-07). `price_per_gram` has 2 dp. Float grams. No reversal/undo of a usage. | Aggregate from usage rows, `Numeric(10,3)` grams, reversal entry type. |
| **Material + `order_materials`** | Weak. | The M2M link has no quantity or price snapshot, and no ondelete. `Material.stock` isn't decremented by order linkage. `OrderItem` (with quantity/price) is unused. | Replace the M2M with `OrderItem` usage (quantity, unit, unit_cost snapshot) or drop the link. |
| **ScrapGold / ScrapGoldItem** | Partly. | Mutable after signing, mixed metals at one price, no Scheidekosten/refining deduction, no uniqueness per order (BE-11). | Per-metal totals and prices, lock at SIGNED, `UNIQUE(order_id)`, refining-fee field. |
| **Notification** | Functional. | Dedup keyed on `is_read` (BE-09). Customer emails are coupled to staff rows. | Separate `CustomerMessage` log with `sent_at`. |
| **OrderStatusHistory / OrderItem** | Would fit. | Defined but never written (dead). | Wire them in or drop the tables. |
| **CalendarEvent / Consultation** | Yes. | Naive DateTime with aware inputs (BE-15). | tz-aware columns. |

**Is the order lifecycle a validated state machine?** No. Any status can be set to any other through `PATCH /orders/{id}` and the scan `advance_status`. The only gates are CONFIRMED Pflichtfelder and the Punzierung check before completion. No transition history is written. The quote conversion bypasses even the CONFIRMED gate (BE-06, BE-17). Invoices have ad-hoc guards in `mark_as_paid`/`cancel`, but the generic PUT undoes them (BE-05). Quotes are the best modelled: dedicated actions, and PUT rejects status changes.

**Is money handled as Decimal end to end?** No. Every money column except `Activity.hourly_rate` is `Float`. All Pydantic schemas use `float`. Arithmetic uses float `round()` (banker's rounding on binary floats). Even `Activity.hourly_rate` (Numeric) is converted back to float immediately (`cost_calculation_service.py:370-374`). Consequences: BE-14, and the ambiguous net/gross semantics compound into BE-01 and BE-02.

**Is time handled tz-aware end to end?** No. The DB columns are naive (about 98 vs 3 aware). The code uses `datetime.utcnow()`, which is naive and deprecated in 3.12. The frontend sends aware `Z` timestamps, and only the repair schemas normalize them. The number-generation year and "today" boundaries in the notification scanners are UTC, not Europe/Berlin, so late-evening local events land on the wrong day (BE-04, BE-15, BE-16).

---

## D. Code-health metrics

| Metric | Value |
|---|---|
| Backend Python files / LOC (`src/goldsmith_erp`) | 160 files / 57,238 lines |
| Largest 15 files | `db/models.py` 3245; `services/customer_service.py` 1856; `services/pdf_service.py` 1483; `services/scanner_service.py` 1305; `services/time_tracking_service.py` 1116; `api/routers/customers.py` 1066; `services/file_erasure_service.py` 1031; `services/quote_service.py` 985; `api/routers/ml.py` 914; `services/customer_update_service.py` 905; `services/metal_inventory_service.py` 776; `db/repositories/order.py` 771 (dead); `services/notification_service.py` 754; `services/comparison_service.py` 734; `services/order_service.py` 702 |
| Functions > 100 lines (AST count) | **40**. Worst: `customer_service.scrub_customer_pii` 407, `file_erasure_service.erase_customer_files` 321, `user_service.anonymize_user` 253, `comparison_service.get_workshop_statistics` 253, `customers.gdpr_erase_customer` 247, `metal_inventory_service.consume_material` 201, `time_tracking_service.switch_timer` 188 |
| `# type: ignore` | 33 total. Top: `services/label_service.py` 8, `api/routers/ml.py` 7, `api/routers/calendar.py` 4, `ml/model_registry.py` 2, `middleware/audit_logging.py` 2, `db/repositories/__init__.py` 2 |
| `except Exception` / bare `except:` | 160 / **0** (the 2 grep hits for `except:` are in comments). Top: `health.py` 11, `customers.py` 11, `ml.py` 8, `metal_inventory.py` 7, `order_service.py` 6, `ml/duration_model.py` 6 |
| Bare `db.commit()` outside `transactional()` in services | `time_tracking_service` 10, `scrap_gold_service` 6, `notification_service` 3, `cost_calculation_service` 1 |
| TODO / FIXME / XXX | **0** real (3 grep hits are `XXXX` format strings in docstrings) |
| Model column signals | `Float` 70, `Numeric` 4 mentions (1 money column), `DateTime(timezone=True)` 3, `index=True` 166 |
| Migrations | 19 active revisions, linear, single head `20260610_e1_gdpr_audit_nofk` (file date ≠ chain order: e1 sits after v13t5). There's an extra `archive/` dir and a stale `alembic_backup/`. The chain can't run on SQLite. |
| Tests | 1812 collected; **1805 passed / 6 skipped / 1 xfailed** in 234 s (SQLite). None covers BE-01, -03, -04, -05, -07, -08, -12. |

---

## E. Recommended fix order (value / effort)

1. **BE-04** (S): timezone normalizer for `InvoiceCreate.due_date` and all datetime inputs. It unblocks invoicing today.
2. **BE-05** (S): remove `status` from `InvoiceUpdate`. This closes the paid-invoice cancel path.
3. **BE-12** (S): partial unique index for one running timer, plus a 409.
4. **BE-09** (M): fix the reminder dedup, send the customer email once per event, run a single monitor. It's customer-facing and ships the moment email is enabled.
5. **BE-01 + BE-02** (M): define net/gross, bill from the approved quote or agreed price, fix quote conversion (with **BE-17**). This is the biggest money impact.
6. **BE-03** (M): model the Altgold credit as a post-tax deduction and confirm VAT with the Steuerberater.
7. **BE-07 + BE-08** (S): aggregate material usage and fix the AVERAGE draw.
8. **BE-10** (S): estimator cost basis consistent with `hours_p50`, before quotes rely on it.
9. **BE-13** (S): export filter, VAT-rate account mapping, storno bookings.
10. **BE-06 + BE-11** (M): order transition table and history; lock scrap gold at SIGNED. Then start the **BE-14/BE-15** Numeric + tz-aware migration (L) with a PostgreSQL CI job.

---

## F. Things the user might have missed

- **Test coverage looks strong but avoids the money seams.** 1805 green tests, yet the cross-service paths (quote → convert → invoice, Altgold → invoice, aware datetimes from the real frontend, concurrent timers) have no tests. Every CRITICAL and HIGH finding above passes CI. One end-to-end "life of a ring" integration test on PostgreSQL would have caught BE-01, -02, -03, -04 and -07.
- **CI runs on SQLite, production runs on PostgreSQL.** The Alembic chain can't upgrade on SQLite, so tests use `create_all` from the ORM. Migrations, partial indexes, `FOR UPDATE` and asyncpg tz binding are untested in CI. `alembic check` against a PostgreSQL service container should be a required job.
- **Enabling customer email is a one-flag risk.** `EMAIL_NOTIFICATIONS_ENABLED=true` immediately triggers BE-09's repeated pickup emails to real customers.
- **`--workers 2` in prod doubles every background job** (monitor, price refresh, reminders) and splits WebSocket clients across processes. Only Redis fan-out keeps them consistent, and most channels have no subscriber (BE-20).
- **The stop endpoint has no ownership check.** `POST /time-tracking/{id}/stop` (`time_tracking.py:59-80`) doesn't verify `entry.user_id == current_user.id`, unlike switch, patch and interrupt. That's a correctness issue on shared bench tablets (one goldsmith stops a colleague's timer) as well as an authz gap; handing it to the security agent.
- **The order has no human-facing number.** Customers, bag labels and the portal refer to `Auftrag #65` (the DB id). Repairs have `REP-/TU-` numbers; orders don't. Renumbering later is painful, so decide before production.
- **`datetime.utcnow()` is deprecated** in Python 3.12+ (the venv here is 3.11, but the base Python is 3.13). There are about 100 call sites; fold this into the tz-aware migration.
- **Side effect of this review:** `poetry run` created and used the venv `~/Library/Caches/pypoetry/virtualenvs/goldsmith-erp-DSjS342B-py3.11` (outside the repo). Test DBs and the drift DB were written only to the session scratchpad.

---

## Verification (2026-09-25)

Verifier: `.orchestrated-fable/ux-erp-audit-2026-09/verify-backend-architecture.md` (adversarial; BE-01, -02, -03, -04, -05 and -14 reproduced empirically). 14 of 14 CRITICAL/HIGH findings confirmed, none refuted.

| ID | Title (short) | Claimed | Verdict | Corrected severity | Verifier note |
|---|---|---|---|---|---|
| BE-01 | Quote to order copies gross total; invoice adds VAT again | CRITICAL | CONFIRMED | CRITICAL | Reproduced: subtotal 1190.0, tax 226.1, total 1416.1. No test covers convert to invoice |
| BE-02 | Invoice bills raw cost, never applies margin | CRITICAL | CONFIRMED | CRITICAL | Reproduced 952.00 vs 1,332.80 agreed; `grep profit_margin` finds nothing; the quote builder has the identical bug |
| BE-03 | Altgold credit crashes invoice creation | HIGH | CONFIRMED | HIGH | `ValidationError` reproduced; no handler catches it, so a 500. The SIGNED/CREDITED scoping of the credit lookup is correct |
| BE-04 | `due_date` validator crashes on aware datetimes | HIGH | CONFIRMED | HIGH | Raw `TypeError` reproduced; tests only use naive dates; the repair schema already has the fix pattern |
| BE-05 | `PUT /invoices/{id}` can cancel a PAID invoice | HIGH | CONFIRMED (empirically) | **CRITICAL** | Scratch pytest passed: `cancel_invoice()` 422s, `update_invoice()` cancels anyway. Also an authorization bypass (see below) |
| BE-06 | No order transition table; history never written | HIGH | CONFIRMED | HIGH | Same root cause as ARCH-01 |
| BE-07 | Second consumption overwrites order cost and weight | HIGH | CONFIRMED | HIGH | Plain assignment at `metal_inventory_service.py:562-565` |
| BE-08 | AVERAGE costing allocates all weight to the first batch | HIGH | CONFIRMED | HIGH | The "concurrent consume" message is misleading: a design bug, not concurrency |
| BE-09 | Reminder scanners re-fire and email customers repeatedly | HIGH | CONFIRMED | HIGH | Dormant today: `EMAIL_NOTIFICATIONS_ENABLED=False` by default; one flag activates it |
| BE-10 | Estimator shown hours and priced cost from different bases | HIGH | CONFIRMED | HIGH | Genuinely different populations and aggregations |
| BE-11 | Scrap gold mutable after SIGNED; mixed metals at gold price | HIGH | CONFIRMED | HIGH | Exposure is "can mutate after signing", not "credit applies to unsigned records" |
| BE-12 | No lock or unique index against two running timers | HIGH | CONFIRMED (structural) | HIGH | TOCTOU and missing constraint verified statically; not run under live concurrency |
| BE-13 | DATEV export includes DRAFT/CANCELLED, books all to 19% | HIGH | CONFIRMED | HIGH | Filter defaults to none; `inv.tax_rate` never read for the account |
| BE-14 | Float money and `round()` give cent errors | HIGH | CONFIRMED | HIGH | Reproduced `_round_price(244.50) == 243.99` and subtotal 3.01 vs 3.00 |

**New while verifying:** invoice cancellation authorization bypass. GOLDSMITH holds `INVOICE_EDIT` but is deliberately denied `INVOICE_DELETE` (`core/permissions.py:~190`), yet `PUT /invoices/{id}` (INVOICE_EDIT) applies `status` unguarded, so a goldsmith can cancel any invoice, including PAID ones, then issue a second one (duplicate check ignores CANCELLED; DATEV exports CANCELLED). Merged into BE-05, which is why BE-05 is now CRITICAL.
