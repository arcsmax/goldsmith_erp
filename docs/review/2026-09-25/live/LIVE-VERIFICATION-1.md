# Live verification, audit/2026-09-fixes (2026-09-25)

Main checkout `/Users/maxbook/Documents/Github/Anne/goldsmith_erp`, branch `audit/2026-09-fixes` (HEAD 48cd9fe). No source edits, no commits. Raw logs are in this folder (`commands.log`, `alembic-*.txt`, `pytest-*.txt`, `seed-demo.txt`, `uvicorn.log`, `vite.log`). Screenshots are in `shots/`, and the Playwright capture scripts are in `scripts/`.

Env used everywhere: `SECRET_KEY=ci-test-secret-key-minimum-32-characters-long-enough ENCRYPTION_KEY=V0Ae_U1MhSkUCNugAmmQV7Jl2GnxkizHeurQnglXVOc= DEBUG=true ANONYMIZATION_SALT=worktree-test-salt PYTHONPATH=src`, with the venv at `/Users/maxbook/Library/Caches/pypoetry/virtualenvs/goldsmith-erp-DSjS342B-py3.11`.

## 1. Infrastructure

| Command | Exit | Result |
|---|---|---|
| `docker info` | 1 | Daemon was down |
| `open -a Docker`, then polled `docker info` | 0 / 0 | Up after 5 s |
| `docker compose up -d db redis` | 1 | db started on `127.0.0.1:5434` (`DB_PORT=5434` in `.env`). redis failed: `Bind for 127.0.0.1:6379 failed: port is already allocated` (held by `coffee_lab-redis-1`). The compose file hard-codes host port 6379, so `REDIS_EXT_PORT=6380` in `.env` has no effect. |
| `docker run -d --name goldsmith_erp-redis-live -p 127.0.0.1:6391:6379 redis:7` | 0 | Stand-in Redis. Port 6380 was also taken, by a local "Code Helper" process. |
| `docker compose exec db pg_isready` | 0 | `/var/run/postgresql:5432 - accepting connections` |

## 2. Migration chain on PostgreSQL 15

`alembic/env.py` only reads `MIGRATION_DATABASE_URL` (sync driver), so I set `MIGRATION_DATABASE_URL=postgresql://user:pass@127.0.0.1:5434/goldsmith`. The database started empty (`alembic current` showed no revision).

| Command | Exit | Result |
|---|---|---|
| `python -m alembic upgrade head` | 0 | 24 revisions applied. W1-10 backfill log: "0 issued invoices backfilled". |
| `python -m alembic current` | 0 | `20260925_w207_order_events (head)` |
| `python -m alembic downgrade -5` | 0 | w207 → c22 → w110 → w117 → gdpr01 → `20260610_e1_gdpr_audit_nofk` |
| `python -m alembic upgrade head` | 0 | The same 5 upgraded again; current is `20260925_w207_order_events (head)` |

**Result:** all five new migrations round-trip on PG 15 without errors. Caveat: the round trip ran on an empty schema. The demo seed was loaded afterwards, so the data-bearing paths (enum casts, the open-timer pre-check, the invoice backfill with real rows) were not exercised by the downgrade.

## 3. PostgreSQL integration tests

I created the database with `CREATE DATABASE goldsmith_test` (exit 0). The env followed the CI job `test-integration-pg`: `TEST_DATABASE_URL` and `DATABASE_URL` set to `postgresql+asyncpg://user:pass@127.0.0.1:5434/goldsmith_test`, and `REDIS_URL=redis://127.0.0.1:6391/0`.

| Command | Exit | Summary line |
|---|---|---|
| `pytest -q -p no:cacheprovider tests/integration -x --maxfail=10` | 1 | `1 failed, 711 passed, 2 skipped, 107 warnings in 295.25s` |
| `pytest -q -p no:cacheprovider tests/integration -k concurrent -rA` | 0 | `4 passed, 710 deselected` |

- The failure is `test_punzierung_bypass_enumeration.py::TestAdvanceStatusService::test_advance_status_alloy_none_is_exempt`:
  - Error: `ForeignKeyViolationError: insert or update on table "order_events" violates foreign key constraint "order_events_user_id_fkey" DETAIL: Key (user_id)=(1) is not present in table "users"`.
  - Cause: the test calls `OrderService.advance_status(..., user_id=1)` with no user row. SQLite does not enforce FKs, so this only shows on PG. The W2-07 `order_events.user_id` FK exposes it. See LV-03.
- The concurrency tests passed on PG:
  - `test_concurrent_metal_consumption.py`: `test_two_parallel_consumes_serialise`, `test_two_parallel_consumes_that_both_fit_both_succeed` and `test_stock_never_negative_under_burst`
  - `test_customer_email_dedupe_index.py::test_concurrent_tick_does_not_send_twice`
- Two races that PROGRESS.md flags still have no real two-session test on PG, because none exists in `tests/integration`:
  - the two-session timer race (W1-17)
  - the quote double-conversion race (A3.3)

## 4. App start

| Command | Exit | Result |
|---|---|---|
| `DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5434/goldsmith python scripts/seed_demo.py` | 0 | "Demo-Daten erfolgreich erstellt". Users: demo-goldschmied (goldsmith), demo-inhaber (admin, "Petra"), demo-buero (viewer, "Lisa"). Password `demo2026!`. |
| `python -m uvicorn goldsmith_erp.main:app --port 8010` (background) | n/a | Port 8000 was held by `coffee_lab-web-1` and VS Code |
| `curl localhost:8010/health` | 0 | HTTP 200, `"status":"degraded"`. DB and Redis were up; the only cause was a disk `warning` at 80.1 % used. |
| `VITE_API_TARGET=http://localhost:8010 VITE_WS_TARGET=ws://localhost:8010 yarn dev --port 3000 --strictPort` (background) | n/a | Vite 7.3.6 ready; `GET /` 200; proxied login POST 200 |

Auth is cookie-based: the login returns `{"message":"Login successful"}` and sets an HttpOnly `access_token` cookie.

## 5. Screenshot loop (admin "Petra", 1280x800 and 390x844)

Each route was loaded, left to reach network idle, and captured as a full-page screenshot. The script also collected console errors, failed `/api` responses, horizontal overflow, controls under 44 px and suspicious text (`undefined`, `NaN`, ASCII umlauts, money strings). Script: `scripts/capture.js`.

| Page | Console errors / failed API calls | Notes |
|---|---|---|
| /login | `401 GET /api/v1/users/me`, `401 POST /api/v1/refresh` | Session probe on the logged-out page. It renders correctly. |
| /portal (logged out) | none | Renders at `/portal` with no redirect (OK) |
| / (Heute dashboard) | none | Redirects to `/dashboard`. Handoff card reads "Übergabe: request_review" (LV-08). 390: overflow (LV-01). |
| /orders | 6x `404 GET /api/v1/photos/<uuid>/thumbnail` | Status badges "CONFIRMED" and "DRAFT" untranslated (LV-05); prices shown as "2100.00 €" (LV-10); table clipped (LV-19) |
| /orders/13 detail | none | The brief's "Übersicht / Verlauf / Weiter" flow does not exist (LV-14). The Status tab did change the status (see below). The Historie tab does not show the event (LV-04). |
| /customers, /customers/1 | none | "Einwilligungen" block present, with "Noch keine Einwilligungen erfasst." and an "Einwilligung erfassen" button (OK). Raw keys "bevorzugt" and "style" in preferences (LV-20). |
| /repairs, /repairs/2, /repairs/4 | none | Repair 2 (status Diagnose) shows no Kundeninfo panel, which matches the code: the panel appears only at READY. Repair 4 (Fertig) shows "Kundeninfo — Abholbereit / Entwurf / Kunde benachrichtigen" (OK). |
| /scanner | none | "Oeffnen" (LV-09) |
| /quotes | `422 GET /api/v1/customers/?limit=500` (x2 console) | Customer list empty (LV-02). Header layout unstyled (LV-15). |
| /invoices | none | German money format (OK) |
| /admin/system, /settings | none | Many 37–38 px controls (LV-12) |

**Order advance check (/orders/13, status confirmed):**
- In the Status tab I clicked "In Bearbeitung". The network showed `200 PUT /api/v1/orders/13`, and the header badge changed from "Bestätigt" to "In Bearbeitung".
- No confirmation dialog appeared.
- The DB has `order_events` row 1: `13 | confirmed | in_progress | user 2`.
- `GET /orders/13/timeline` returns `"Bestätigt → In Bearbeitung"`.
- The Historie tab still shows only "Auftrag erstellt" and "Zuletzt aktualisiert" (`order-detail-historie-after-1280.png`).

## 6. VIEWER (demo-buero@werkstatt.de, "Lisa")

- The sidebar shows only Dashboard, Aufträge, Zeiterfassung and Kalender.
- /dashboard, /orders and /orders/1 at both widths: no failed API calls, no console errors, no toasts, and no price or cost value on the dashboard or order detail.
- The orders list still shows the "Preis" column, where every cell reads "Wird berechnet", and the header reads "Gesamtwert: 0.00 €".
- The "+ Neuer Auftrag" button is visible and opens the create dialog (`viewer-new-order-click-1280.png`), although VIEWER does not have `Permission.ORDER_CREATE`. I did not submit it. See LV-07.
- Checked for a sort-by-price leak: the API ignores the `sort_by=price` and `sort=price` query parameters for the viewer (same order as the default, all `price: null`). No leak.

## 7. Playbook 7e checklist, per page

- **Focus:** tabbing through 5 elements on /dashboard and /orders shows a 2 px solid outline on every element: white on the orange header, dark on the sidebar (`focus-*-tab1..5-1280.png`). The first Tab lands on the header search button; there is no skip link.
- **Touch targets at 390:**
  - Header "System" 77x27 on every page
  - /orders search field 177x24
  - /repairs "Details" 63x31 and status select 167x37
  - /quotes "PDF" 46x32 and status select 121x21
  - /invoices status select 98x21
  - /customers page-size select 63x37
  - /admin/system inputs 38 px high and a 13x18 checkbox
  - /customers/1 phone links 18 px high
  - /settings toggle 48x28
- **Status badges:** label only on /orders, /quotes, /invoices, /repairs and the detail headers; no icon anywhere. Orders show untranslated "CONFIRMED" and "DRAFT" next to the German "NEU".
- **Umlauts:** UI copy has ASCII umlauts (LV-09). The seed data does too ("Mueller", "Anhaenger", "Tuebinger Strasse"), which is demo content only.
- **Broken or odd items:**
  - The header search icon renders as a blank square (LV-06).
  - The header overflows at 390 on every staff page (LV-01).
  - The offline banner is visible but covers the top of the header (LV-13).
  - The text scan found no "undefined", "NaN", "null" or "Invalid Date" on any page.
- **Per page:**
  - login: clean at both widths
  - portal: placeholder and footer text are low contrast on the dark background (visual only, not measured)
  - dashboard: LV-01, LV-08
  - orders: LV-05, LV-10, LV-11, LV-19
  - order detail: LV-04, LV-14
  - customers: LV-20
  - repairs: LV-12, LV-18
  - scanner: LV-09
  - quotes: LV-02, LV-15
  - invoices: LV-12
  - admin/system: LV-12
  - settings: LV-09

## Findings

| ID | Page | Severity | What is wrong | Evidence | Suggested fix |
|---|---|---|---|---|---|
| LV-01 | All staff pages at 390 | HIGH | Page scrolls sideways: `scrollWidth` 448 > 390. `.user-menu` (246 px) pushes "Abmelden" to right=448, off screen. | `dashboard-390.png`, `orders-390.png`, `scanner-390.png`; overflow probe `DIV.user-menu right=448` | Below 480 px, collapse the user menu (Scanner, bell, name, logout) into the hamburger or icon-only buttons. Add `min-width:0` and `overflow:hidden` on the header flex children. |
| LV-02 | /quotes | HIGH | `customersApi.getAll({limit:500})` gets 422 (`limit` must be <= 100). The error is swallowed (QuotesPage.tsx:894–898). The required "Kunde" select in "Neues Angebot" contains only "Kunde auswaehlen...", so no quote can be created from this page. The "Kunde (ID)" column shows "#5" instead of names. | `quotes-create-modal-1280.png`, `quotes-1280.png`; `curl .../customers/?limit=500` returns 422 | Page through with `limit<=100` or add a customer search endpoint. Surface a toast on failure instead of failing silently. ConsumeMetalModal.tsx:122 and InvoicesPage.tsx:684 use the same `limit:500` pattern (orders allows it today: 200). |
| LV-03 | CI / PG tests | MEDIUM | PG integration run: 1 failed, 711 passed. `test_advance_status_alloy_none_is_exempt` passes `user_id=1` with no user row, which trips the W2-07 `order_events_user_id_fkey`. The `test-integration-pg` CI job will be red. | `pytest-integration-pg.txt` | Create a user fixture in the test and pass its id. |
| LV-04 | Order detail, Historie tab | MEDIUM | W2-07 records `order_events` and `GET /orders/{id}/timeline` returns them, but the Historie tab is hard-coded to show "created" and "updated" only (OrderDetailPage.tsx:594–610). After the status change the tab showed no event. | `order-detail-historie-after-1280.png`; DB row `order_events.id=1`; timeline JSON | Render the Historie tab from `/timeline`. |
| LV-05 | /orders list | MEDIUM | Badges show raw "CONFIRMED" and "DRAFT" (the detail view shows "Bestätigt"). The seed still writes legacy `status="new"` after the W2-07 legacy mapping (2 orders are `new` on a fresh DB). No badge has an icon. | `orders-1280.png`, `viewer-orders-1280.png`; `select status,count(*)` shows `new=2` | Route list badges through `status.ts` / `<StatusBadge>` with icon + label. Update seed_demo.py:1074 and :1149 to use a current status. |
| LV-06 | Header, all pages | MEDIUM | The global search button (44x44) renders as a blank orange square: its SVG is squashed to 3.6x20 px. | `header-search-trigger-1280.png`; computed `svgW 3.61` | Give the SVG `flex-shrink:0` and `width/height:20px` (or `min-width`) in the `.global-search__trigger` CSS. |
| LV-07 | /orders (VIEWER) | MEDIUM | VIEWER sees "+ Neuer Auftrag" and it opens the create dialog, but VIEWER lacks `ORDER_CREATE`, so submitting would 403. The price column and "Gesamtwert: 0.00 €" still appear, and "Wird berechnet" is shown for all 15 orders, which misrepresents their state. No real price value leaks. | `viewer-new-order-click-1280.png`, `viewer-orders-1280.png` | Gate the button on the permission. Hide the price column and Gesamtwert for roles without financial access. |
| LV-08 | Dashboard, "Übergaben an mich" | LOW | Raw enum shown: "Übergabe: request_review" (HandoffLane.tsx:67). | `dashboard-390.png` | Map `handoff_type` through a labels table (as HandoffTab.tsx does). |
| LV-09 | Scanner, Quotes, Order detail, Settings, Portal | LOW | ASCII umlauts in UI copy: ScannerPage.tsx:452 "Oeffnen" and :532 "oeffnen"; QuotesPage.tsx:174 "auswaehlen", :190 "fuer", :201 "Gueltig fuer", the "GUELTIG BIS" column and "4 Kostenvoranschlage"; OrderDetailPage.tsx:218 "fuer"; UserSettingsPage.tsx:39 "fuer"; CustomerPortalPage.tsx:208 and :229 "pruefen" and "moeglich"; AlloyMismatchModal.tsx:401 and PunzierungsCheckModal.tsx:276 "auswaehlen" / "Begruendung". | `scanner-390.png`, `quotes-1280.png`; grep | Replace with ä, ö and ü. |
| LV-10 | /orders, order detail, /repairs | LOW | Money format is inconsistent: "2100.00 €", "1450.00 €" and "800.00 EUR" here, versus "1.450,00 €" on quotes and invoices. In the orders table the "€" wraps onto its own line. | `orders-1280.png`, `repair-detail-1280.png` | Use one `formatCurrency` (de-DE) and `white-space:nowrap`. |
| LV-11 | /orders | LOW | Search field is unstyled: no border, 24 px high, and the placeholder is cut off ("Suche nach Titel, Beschr"). | `orders-1280.png`, `viewer-orders-1280.png` | Apply the shared input style with min-height 44 px. |
| LV-12 | Several pages at 390 | LOW | Controls under 44 px (list in section 7). | capture facts; `repairs-390.png`, `quotes-390.png`, `admin-system-390.png` | Set min-height 44 px on buttons, selects and inputs in the bench and mobile layout. |
| LV-13 | Global offline banner | LOW | The banner (fixed, top-0) is visible but covers the top ~18 px of the header. | `offline-banner-orders-1280.png`, `offline-banner-orders-390.png` | Offset the header or push the layout down while offline. |
| LV-14 | Order detail | LOW | 14 tabs in one strip: at 390 only 3 are visible, with no overflow cue. There is no "Übersicht / Verlauf / Weiter" advance flow. The status changes with one click in the Status tab list (generic `PUT /orders/13`), with no confirmation. | `order-detail-390.png`, `order-detail-status-tab-1280.png` | Group the tabs. Add a primary "next status" action with a confirm/undo step, if that is the intended W2 design. |
| LV-15 | /quotes | LOW | Header block unstyled: oversized h1, and the "Neues Angebot" button and status filter stack with no spacing. | `quotes-1280.png` | Use the page-header layout used by /orders. |
| LV-16 | /orders (demo data) | LOW | 6 thumbnails return 404 (`/api/v1/photos/<uuid>/thumbnail`). The seed creates photo rows without files, so rows show a broken-image icon. | `orders-1280.png`; network log | Seed real files or skip photo rows; render a placeholder when the fetch 404s. |
| LV-17 | Infra | LOW | `docker-compose.yml` hard-codes Redis host port 6379 (`REDIS_EXT_PORT` is unused), so it collides with other stacks. `/health` reports "degraded" only because of a disk-usage warning at 80 %. | `commands.log` | Use `${REDIS_EXT_PORT:-6379}`. Consider not degrading overall health on a disk warning. |
| LV-18 | /repairs/4 | LOW | "Kunde benachrichtigt 23.09.2026" is shown while the Kundeninfo draft is still "Entwurf" (not sent). This is the known DOM-12, reproduced on seed data. | `repair-detail-ready-1280.png` | As in the DOM-12 follow-up. |
| LV-19 | /orders at 1280 | LOW | Table is clipped: the ERSTELLT and AKTIONEN columns are cut off, and the scan FAB covers the row #13 creation date. | `orders-1280.png` | Allow wrapping or hide low-value columns at 1280; add bottom padding for the FAB. |
| LV-20 | /customers/1 | LOW | Preferences show raw keys "bevorzugt" and "style". | `customer-detail-1280.png` | Label map for preference keys. |
| LV-21 | /login | LOW | Console shows 3 errors from the expected `401 /users/me` and `401 /refresh` session probe. This is noise that hides real errors. | capture facts for /login | Skip the probe on /login, or treat 401 as a silent result. |

**Counts:** 2 HIGH, 5 MEDIUM, 14 LOW (21 in total).

## Screenshots (`shots/`, 55 files)

- **Logged out:** login-1280, login-390, portal-1280, portal-390
- **Admin:** dashboard, orders, order-detail, customers, customer-detail, repairs, repair-detail, repair-detail-ready, scanner, quotes, invoices, admin-system and settings, each at -1280 and -390
- **Order flow:** order-detail-status-tab-1280, order-detail-historie-1280, order-detail-after-advance-1280, order-detail-historie-after-1280
- **Quotes:** quotes-create-modal-1280
- **Header:** header-search-trigger-1280
- **Focus:** focus-dashboard-tab1..5-1280, focus-orders-tab1..5-1280
- **Offline:** offline-banner-orders-1280, offline-banner-orders-390
- **Viewer:** viewer-dashboard, viewer-orders and viewer-order-detail, each at -1280 and -390; viewer-new-order-click-1280

## 8. Teardown

- uvicorn (:8010) and Vite (:3000) were killed; `lsof` confirms both ports are free.
- The containers are **still running**: `goldsmith_erp-db-1` (127.0.0.1:5434) and the stand-in `goldsmith_erp-redis-live` (127.0.0.1:6391).
- The `goldsmith` database holds the migrated schema, the demo seed, and order 13 now `in_progress`. `goldsmith_test` is empty after the pytest teardown.
- Remove the stand-in Redis with `docker rm -f goldsmith_erp-redis-live`.
