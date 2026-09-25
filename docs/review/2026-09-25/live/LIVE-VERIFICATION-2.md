# Live verification pass 2, audit/2026-09-fixes (2026-09-25)

Main checkout `/Users/maxbook/Documents/Github/Anne/goldsmith_erp`, branch `audit/2026-09-fixes` (HEAD cb0cf0b). I made no source edits and no commits. The only tracked change in the tree is `frontend/.yarn/install-state.gz`, which Yarn touches whenever it runs.

- **Raw logs** (in this folder): `commands.log` (every command with its exit code), `alembic-*.txt`, `seed-demo.txt`, `seed-*.txt`, `pytest-integration-pg.txt`, `uvicorn.log`, `vite.log`
- **Screenshots:** `shots/` (64 files)
- **Capture scripts:** `scripts/` (template, admin, viewer, out)
- **Accessibility snapshot:** `snap-order13.yml`
- **Runner:** `run.sh`

**Environment** (same as pass 1):
- `SECRET_KEY=ci-test-secret-key-minimum-32-characters-long-enough`
- `ENCRYPTION_KEY=V0Ae_U1MhSkUCNugAmmQV7Jl2GnxkizHeurQnglXVOc=`
- `DEBUG=true ANONYMIZATION_SALT=worktree-test-salt PYTHONPATH=src`
- venv: `goldsmith-erp-DSjS342B-py3.11`
- Migrations: `MIGRATION_DATABASE_URL=postgresql://user:pass@127.0.0.1:5434/goldsmith`

## 1. Infrastructure

| Command | Exit | Result |
|---|---|---|
| `docker info` | 0 | Daemon up |
| `docker ps` | 0 | `goldsmith_erp-db-1` (127.0.0.1:5434, healthy) and `goldsmith_erp-redis-live` (127.0.0.1:6391) both still running from pass 1 |
| read `docker-compose.yml` | n/a | Redis port is now `${REDIS_HOST_IP:-127.0.0.1}:${REDIS_EXT_PORT:-6379}:6379`, DB is `${DB_PORT:-5432}` (LV-17 fixed) |

## 2. Migrations on PostgreSQL 15

This time the round trip ran **on data**: the old pass-1 demo seed was still in `goldsmith`.

| Command | Exit | Result |
|---|---|---|
| `alembic current` | 0 | `20260925_w207_order_events` |
| `alembic upgrade head` | 0 | w207 → w210_email_optional → w204_invoice_ustg14 → w206_gemstone_intake → w214_interrupt_resume → w216_altgold_id |
| `alembic current` | 0 | `20260925_w216_altgold_id (head)` |
| `alembic downgrade -5` | 0 | w216 → w214 → w206 → w204 → w210 → w207 |
| `alembic current` | 0 | `20260925_w207_order_events` |
| `alembic upgrade head` | 0 | The same 5 upgraded again |
| `alembic current` | 0 | `20260925_w216_altgold_id (head)` |

**Result:** all five new migrations round-trip on PG 15, with seed data present.

## 3. Fresh seed

| Command | Exit | Result |
|---|---|---|
| `psql -d postgres -c "DROP DATABASE IF EXISTS goldsmith WITH (FORCE)"` | 0 | |
| `psql -d postgres -c "CREATE DATABASE goldsmith"` | 0 | |
| `alembic upgrade head` | 0 | 29 revisions applied from empty |
| `DATABASE_URL=postgresql+asyncpg://…/goldsmith python scripts/seed_demo.py` | 0 | "Demo-Daten erfolgreich erstellt!". Users: demo-goldschmied, demo-inhaber (admin), demo-buero (viewer). Password `demo2026!`. |

Checks on the fresh seed:
- **Order statuses:** draft 1, confirmed 3, in_progress 5, completed 3, delivered 3. There is **no `new` status** (`seed-order-status.txt`).
- **Photos:** 6 `order_photos` rows point to real files under `uploads/photos/<order>/…jpg`. The thumbnails render as coloured swatches on /orders.
- **Repair notification timestamps** (`seed-repairs.txt`): `customer_notified_at` is set only on repairs 4 (ready) and 5 (picked_up). Both have a `customer_updates` row with `status=sent` and a matching `sent_at`.

## 4. PG integration suite

Setup: `DROP/CREATE DATABASE goldsmith_test` (exit 0). Env: `TEST_DATABASE_URL=DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5434/goldsmith_test` and `REDIS_URL=redis://127.0.0.1:6391/0`.

| Command | Exit | Summary |
|---|---|---|
| `pytest -q -p no:cacheprovider tests/integration -x --maxfail=10` | 1 | `2 failed, 876 passed, 2 skipped, 138 warnings in 387.99s` |

Both failures are in `tests/integration/test_hallmark_soft_gate.py::TestServiceLayerSoftGate`:
- `test_advance_status_with_reason_marks_succeeds`
- `test_orders_without_alloy_are_exempt`

The error is `ForeignKeyViolationError … fk_orders_punzierung_verified_by_users DETAIL: Key (punzierung_verified_by)=(1) is not present in table "users"`. It is the same pattern as LV-03: the tests pass `user_id=1` with no user row (lines 238, 251, 261). The pass-1 failure in `test_punzierung_bypass_enumeration.py` now passes, but the sibling file still has the bug (LV2-01).

## 5. App start

| Command | Exit | Result |
|---|---|---|
| `uvicorn goldsmith_erp.main:app --host 127.0.0.1 --port 8010` (bg) | n/a | `REDIS_URL=redis://127.0.0.1:6391/1` (kept apart from pytest's db 0) |
| `curl localhost:8010/health` | 0 | HTTP 200, `"status":"healthy"`. The disk warning (81 %) no longer degrades the overall status (LV-17, second part, fixed). |
| `VITE_API_TARGET=http://localhost:8010 VITE_WS_TARGET=ws://localhost:8010 yarn dev --port 3000 --strictPort` (bg) | n/a | Ready; `GET /` 200 |

The shared Playwright browser still had another agent's tab open on `127.0.0.1:5199/dev/ui` with a beforeunload dialog. I dismissed the dialog (stayed on that page) and did all my work in a separate tab.

## 6. Screenshot loop and flows

**Pages captured.** The scripts ran at 1280x800 and 390x844 and recorded console errors, failed `/api` responses, overflow, controls under 44 px, suspicious text, money strings and badges.
- **Admin "Petra":** /, /orders, /orders/1, /customers, /customers/1, /repairs, /repairs/4, /scanner, /quotes, /invoices, /admin/system, /settings, /dev/ui
- **Logged out:** /login, /portal
- **Viewer "Lisa":** /, /orders, /orders/1, /repairs, /repairs/4, /customers

**Admin: no failed API request and no console error on any page.**

**Order detail /orders/13 (confirmed):**
- There are five tabs: Übersicht, Arbeit, Fotos (0), Kunde, Verlauf.
- The Verlauf tab showed "Noch kein Verlauf" before the change.
- "Weiter: In Bearbeitung" sent `200 PATCH /api/v1/orders/13/status`, with no dialog.
- Afterwards Verlauf shows "Status · gerade eben · Bestätigt → In Bearbeitung", and the next action became "Weiter: Qualitätskontrolle".
- "Weitere Statuswechsel" lists: Wartet auf Anprobe, Anprobe abgeschlossen, Bereit zum Fassen, Fertiggestellt, Pausiert, Storniert.
- "Pausiert" opens the "Auftrag pausieren" dialog (Grund = Pflichtfeld, "Weiter am" optional). "Abbrechen" closed it, sent no request, and the status stayed.
- Screenshots: `order13-*`

**Customer /customers/1:**
- Tabs: Stammdaten, Verlauf, Maßbibliothek, Auftragshistorie, Rechnungen.
- The Verlauf tab lists 4 entries (repair, orders, invoice) with German status and money.
- The Einwilligungen block reads "Noch keine Einwilligungen erfasst." and has an "Einwilligung erfassen" button.

**Repair intake:** "Neue Reparatur" opens `/repairs?neu=1` with these sections:
- Kundin/Kunde search plus "Neuer Kunde"
- piece chips, metal chips and description
- Fotos und Zustand
- Anliegen chips
- Preis und Termin, with quick dates
- "Reparatur annehmen"

At 390 there is no overflow and no control under 44 px.

**Repair /repairs/4 (ready):**
- The panel reads "Kundeninfo — Abholbereit · Verschickt · Ihre Reparatur ist abholbereit · Verschickt am 23.09.2026, 03:26 per Email · Abholung bestätigen / Stornieren".
- "Kunde benachrichtigt 23.09.2026" matches the sent update.
- Repair 2 shows "Kunde benachrichtigt —".

**Quotes:** "Neues Angebot" now has a customer search field. Typing "Schn" calls `200 GET /customers/search?q=Schn&limit=8` and offers "Maria Schneider". Escape does not close the modal (LV2-07).

**Admin /admin/system:**
- Sections: Systemstatus ("Alle Systeme betriebsbereit"), Backup, Metriken, **Werkstatt-Stammdaten**, E-Mail-Konfiguration, Kunden-Import (CSV), Erscheinungsbild.
- There is **no "Nachrichten-Warteschlange"** section, and no route or string for it in `frontend/src` (not present, so skipped).

**/dev/ui:** renders the primitives (money cells, deadline chips ■/▲/●, DataTable error states). The two toasts, "Aufträge/Kunden konnten nicht geladen werden.", are intentional demo states from `UiDemoPage.tsx`.

**/portal (logged out):** renders at both widths, with no error.

**Viewer "Lisa":**
- The sidebar shows Dashboard, Aufträge, Zeiterfassung and Kalender only.
- On /orders there is no "Neuer Auftrag" button. Columns are Foto, ID, Titel, Beschreibung, Status, Frist, Erstellt; there is no Preis column and no Gesamtwert.
- No €, "Preis", "Kosten" or "Wird berechnet" text on the dashboard, /orders or /orders/1.
- No failed API calls, no console errors and no toasts.
- /repairs, /repairs/4 and /customers silently redirect to /dashboard (route guard).
- On /orders/1 the viewer still sees "Angebot erstellen", which lands on /dashboard with no feedback (LV2-04).

## 7. Per-page checks (390 unless noted)

**Overflow:** `scrollWidth` is 390 on every page for admin, viewer and logged out. Wide tables scroll inside their container.

**Focus:** I tabbed 5 elements on /dashboard, /orders and /orders/13:
- The ring is always a 2 px solid outline: white on the orange header (search, Scanner, bell, Abmelden), dark on the sidebar (Dashboard).
- There is still no skip link; the first Tab lands on "Suche öffnen".
- Screenshots: `focus-*-tab2-1280.png`

**Controls under 44 px at 390:**
- none on dashboard, orders, customers, repairs, repair detail, scanner, quotes, invoices, intake
- remaining: /customers/1 phone and mail links (18 px high) and a 24x24 checkbox; /orders/1 mail and phone links (24 px); /admin/system a 13x18 checkbox and a 24x24 checkbox; /settings a 24x24 toggle input

**Status badges:** icon plus German label on orders, order detail, repairs, quotes and invoices (Bestätigt, Entwurf, In Bearbeitung, Fertiggestellt, Ausgeliefert, Eingang, Diagnose, Abholbereit, Gesendet, Genehmigt, In Auftrag umgewandelt, Bezahlt, Versendet).

**Umlauts:** UI copy is mostly fixed. The remaining ASCII forms:
- `/settings` "Aktiviert den USB-HID-Scanner **fuer** die Werkbank"
- `/admin/system` "max. 64 px **Hoehe** empfohlen"
- in code, not seen live: `components/scanner/ActionHandlers.ts:326,333,381,388` ("aendern … fuer Auftraege moeglich", "verfuegbar"), `AlloyMismatchModal.tsx:202,317,337,355,401` ("Begruendung", "auswaehlen"), `PunzierungsCheckModal.tsx:373,385` ("Pruefer", "auswaehlen")

The seed data also uses ASCII forms ("fuer", "uebernommen", "Loetstellen pruefen"), which is demo content only.

**Money:** de-DE everywhere ("2.100,00 €", "20.530,00 €", "60,00 €"). The raw `\d+\.\d{2} €` pattern appears nowhere. The dashboard KPIs are rounded ("2.250 €", "8.868 €").

**Bad text:** no "undefined", "NaN", "null" or "Invalid Date" in visible text. However, the accessibility tree has `button "Systemstatus: undefined"` (LV2-02).

**VIEWER:** no price or cost text, and no 403 toasts.

**Offline banner** (`context.setOffline(true)` on /orders): the banner is fixed at top 0–20 px, and the header shifts down to top 36 px, so there is no overlap at 1280 or 390 (`offline-orders-*.png`).

**Per page:**
- login: LV-21
- portal: clean
- dashboard: clean; handoff reads "Übergabe: Prüfung anfordern"
- orders: LV-19 (Aktionen column clipped at 1280, FAB over the last column)
- order detail: LV2-05 (tab strip at 390)
- customers: LV2-03 (table clipped at 1280), LV-20
- repairs, intake and repair detail: clean
- scanner: clean
- quotes: LV2-06 and LV2-07, LV-02 residual
- invoices: table wider than the card at 1280 (`TABLE.invoices-table r=1357`); status select 98x21
- admin: LV2-02; the "Hoehe" umlaut
- settings: the "fuer" umlaut

## 8. LV-01..LV-21 re-verification

| ID | Verdict | Evidence |
|---|---|---|
| LV-01 header overflow at 390 | **fixed** | `scrollWidth` 390 on all pages. The header at 390 is hamburger, search and bell (44x44 each); Scanner and Abmelden are collapsed. `dashboard-390.png`, `order13-viewport-390.png` |
| LV-02 quotes customer list 422 | **fixed** (residual) | Customer search works (`200 /customers/search?q=Schn&limit=8`), `quotes-customer-search-1280.png`. No 422 anywhere. The list's "KUNDE (ID)" column still shows "#5", "#7" instead of names (`quotes-1280.png`). |
| LV-03 PG test FK (`user_id=1`) | **still open** (moved) | The original test passes, but the same bug fails 2 tests in `test_hallmark_soft_gate.py` (LV2-01), `pytest-integration-pg.txt` |
| LV-04 Historie ignores events | **fixed** | The Verlauf tab gained "Bestätigt → In Bearbeitung" after "Weiter", `order13-verlauf-before/after-1280.png` |
| LV-05 raw CONFIRMED/DRAFT, seed `new`, no icons | **fixed** | German badges with icons on /orders; the seed has no `new` status (`seed-order-status.txt`), `orders-1280.png` |
| LV-06 blank search icon | **fixed** | The magnifier renders in the header, `orders-1280.png` |
| LV-07 VIEWER create button / price column | **fixed** | No "Neuer Auftrag", no Preis column, no Gesamtwert, `viewer-orders-1280.png`. Related new issue: LV2-04. |
| LV-08 "Übergabe: request_review" | **fixed** | "Übergabe: Prüfung anfordern", `dashboard-390.png` |
| LV-09 ASCII umlauts in UI copy | **still open** (mostly fixed) | Scanner, quotes, order detail and portal are clean. "fuer" on /settings, "Hoehe" on /admin/system, and scanner/modal strings in code (section 7). |
| LV-10 money format | **fixed** | de-DE on every page, no raw `x.yy €`, `orders-1280.png` |
| LV-11 orders search unstyled | **fixed** | Styled, full placeholder "Titel, Beschreibung oder Nr. …", `orders-1280.png` |
| LV-12 controls < 44 px | **still open** (much reduced) | At 390 only contact links (18–24 px) and small checkboxes remain. At 1280: header "System" 77x27, quotes status select 194x21, invoices select 98x21, PDF 46x32. |
| LV-13 offline banner covers header | **fixed** | Banner 0–20 px, header at top 36 px, `offline-orders-1280/390.png` |
| LV-14 14 tabs, no advance flow | **fixed** | 5 tabs, a primary "Weiter: …" button, "Weitere Statuswechsel" menu, and a Pausiert dialog with a required reason, `order13-*`. At 390 the tab strip is cramped (LV2-05). |
| LV-15 quotes header unstyled | **fixed** (residual) | Page header layout matches /orders. The status filter select is still unstyled (LV2-06), `quotes-1280.png` |
| LV-16 photo 404s | **fixed** | 0 failed `/api` requests on /orders; thumbnails render (real seeded files) |
| LV-17 Redis port hard-coded; health degraded on disk | **fixed** | `${REDIS_EXT_PORT:-6379}` in compose; `/health` returns `healthy` with the disk at 81 % "warning" |
| LV-18 notified shown while draft | **fixed** | Repair 4 shows notified 23.09 with a "Verschickt" Kundeninfo; repairs 1–3 and 6 have no timestamp (`seed-repairs.txt`, `repair4-kundeninfo-viewport-1280.png`) |
| LV-19 orders table clipped at 1280, FAB overlap | **still open** | The AKTIONEN column is cut at the right edge (`TABLE.orders-table r=1356` vs 1280); the FAB covers the Erstellt cell of row #5, `orders-1280.png` |
| LV-20 raw preference keys | **still open** | /customers/1 "PRÄFERENZEN & ALLERGIEN … bevorzugt Gelbgold · style klassisch", `customer-detail-1280.png` |
| LV-21 /login console noise | **regressed** | Logged-out /login now logs 6 console errors: `WebSocket … /ws/events … 403`, `401 GET /users/me`, `401 GET /time-tracking/running`, `401 GET /activities/?sort_by_usage=true…`, `401 POST /refresh`. Pass 1 had only the `/users/me` + `/refresh` probe. The timer and activities fetches and the WS connect now also fire before login. (`out-login-1280.png`; capture facts) |

**Counts:** fixed = 01, 02, 04, 05, 06, 07, 08, 10, 11, 13, 14, 15, 16, 17, 18 (**15**, LV-02 and LV-15 with residuals); still open = 03, 09, 12, 19, 20 (**5**); regressed = 21 (**1**).

## 9. New findings

| ID | Page | Severity | What is wrong | Evidence | Suggested fix |
|---|---|---|---|---|---|
| LV2-01 | CI / PG tests | MEDIUM | `test_hallmark_soft_gate.py::TestServiceLayerSoftGate` passes `user_id=1` with no user row (lines 238, 251, 261). On PG, `fk_orders_punzierung_verified_by_users` rejects it, so 2 tests fail and the `test-integration-pg` CI job stays red. Same class as LV-03. | `pytest-integration-pg.txt` (`2 failed, 876 passed`) | Use a real user fixture id. Grep `tests/integration` for other hard-coded `user_id=1`. |
| LV2-02 | Sidebar footer health dot (ADMIN, every page) | MEDIUM | `HealthDot` calls `apiClient.get('/health', {baseURL: ''})`. `/health` is proxied neither by Vite (only `/api`, `/ws`, `/uploads`) nor by `frontend/nginx.conf` (`location /` serves the SPA). So it receives `index.html`, `data.status` is undefined, the button is announced as **"Systemstatus: undefined"**, and the dot never turns yellow or red. This is a silent monitoring failure that also affects production. | `snap-order13.yml` line 68; `curl localhost:3000/health` returns `<!DOCTYPE html>`; `HealthDot.tsx:29,47`, `api/admin.ts:75-79` | Call a proxied path (e.g. `/api/v1/health`, or reuse the admin system-info endpoint), or add `location = /health` and a Vite proxy entry. Treat a non-JSON or unknown status as `error`. |
| LV2-03 | /customers at 1280 | LOW | The table (r=1530) is wider than its card, so TAGS is cut mid-word ("Stammkund", "Geschaeftsk") and the columns after it are hidden, with no scroll cue. Same pattern on /invoices (r=1357). | `customers-1280.png`, capture facts | Hide low-value columns under 1440 px, or wrap tags. Show a horizontal-scroll affordance. |
| LV2-04 | /orders/:id (VIEWER) | LOW | "Angebot erstellen" (and "Etikett drucken") are shown to VIEWER. Clicking "Angebot erstellen" navigates to /quotes, which the route guard silently bounces to /dashboard. It is a dead-end control with no message. | `viewer-order-detail-1280.png`, `viewer-angebot-erstellen-click-1280.png` (URL ended at /dashboard) | Gate the button on `QUOTE_CREATE`, as the status button is gated on `canChangeStatus` (`OrderDetailPage.tsx:352`). |
| LV2-05 | Order detail at 390 | LOW | The 5-tab strip has no gaps: labels run together ("ÜbersichtArbeit", "Fotos (0) Kunde") and "Verlauf" is clipped at the right edge, with no scroll cue. | `order13-viewport-390.png` | Add gap and horizontal scroll snap with an edge fade, or shorten to icons plus labels. |
| LV2-06 | /quotes | LOW | The "Status" filter select is unstyled (browser default, 194x21) while every other page uses the shared select style. The customer column shows the ID "#5" instead of a name. | `quotes-1280.png` | Use the shared `<Select>` primitive. Resolve customer names (list endpoint join, or the batch search). |
| LV2-07 | /quotes "Neues Angebot" modal | LOW | Escape does not close the dialog (it has `role=dialog aria-modal=true`); Playwright timed out behind `.modal-overlay` after Escape. The form fields sit flush against the modal's left and right edges (no body padding). | `quotes-create-modal-1280.png`; run log (Escape did not close) | Add an Escape handler (or use the shared Dialog primitive) and body padding. |
| LV2-08 | /login (logged out) | LOW | Covered in LV-21 (regressed). Before login, the app opens the `/ws/events` WebSocket (403) and fetches `/time-tracking/running` and `/activities` (401). | capture facts for `out-login-1280` | Mount the WS, timer and activity providers only inside the authenticated shell. |

**Counts:** 0 CRITICAL, 0 HIGH, 2 MEDIUM (LV2-01, LV2-02), 6 LOW (LV2-03 to LV2-08).

## 10. Screenshots (`shots/`, 64 files)

- **Logged out:** out-login-1280/390, out-portal-1280/390
- **Admin, 1280 and 390:** dashboard, orders, order-detail (order 1), customers, customer-detail, repairs, repair-detail-ready (repair 4), scanner, quotes, invoices, admin-system, settings, dev-ui
- **Order flow (order 13):** order13-uebersicht-before-1280, order13-tab-arbeit/fotos/kunde-1280, order13-verlauf-before-1280, order13-verlauf-after-1280, order13-more-menu-1280, order13-pausiert-dialog-1280, order13-viewport-390
- **Customer:** customer1-verlauf-1280, customer1-stammdaten-viewport-1280
- **Repairs:** repair-intake-1280/390, repair4-kundeninfo-viewport-1280
- **Quotes:** quotes-create-modal-1280, quotes-customer-search-1280
- **Focus:** focus-dashboard-tab2-1280, focus-orders-tab2-1280, focus-orders-13-tab2-1280
- **Offline:** offline-orders-1280/390
- **Viewer, 1280 and 390:** viewer-dashboard, viewer-orders, viewer-order-detail, viewer-repairs and viewer-repair-detail (both show the dashboard after the redirect), viewer-customers (also the dashboard); plus viewer-angebot-erstellen-click-1280

## 11. Teardown

- uvicorn (:8010) and Vite (:3000) were killed; `lsof -iTCP:8010 -iTCP:3000 -sTCP:LISTEN` is empty.
- The containers are still running: `goldsmith_erp-db-1` (127.0.0.1:5434) and `goldsmith_erp-redis-live` (127.0.0.1:6391).
- The `goldsmith` DB holds a fresh seed at head `20260925_w216_altgold_id`, with order 13 now `in_progress` and one `order_events` row.
- `goldsmith_test` is left after the pytest run.
