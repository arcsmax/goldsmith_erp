# Progress: audit 2026-09-25 fix waves

Tracks what has actually landed on `audit/2026-09-fixes` against
[FINDINGS-REGISTER.md](FINDINGS-REGISTER.md) (212 findings) and
[MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md) (83 fix items). Source of truth: the
~35 scratch reports in `.orchestrated-fable/ux-erp-audit-2026-09/` (`fix-*.md`,
`adversarial-w1.md`, `fix-w1c-adversarial.md`) and `git log --oneline main..HEAD`
on this branch. Where a report and a commit message disagreed, the report won.

## (a) Changelog

All commits below are on `audit/2026-09-fixes`, dated 2026-09-25. Short SHAs are
from `git log --oneline main..HEAD`. "Suite" lines are the exact totals each
report recorded after its own fix, not a re-run by this pass.

### W1-01 — Reject placeholder secrets; bind dev stack to loopback
- Findings: SEC-02, SEC-08. Commits: `b315d25` (placeholder rejection, first pass), `948ddf5` (loopback-bound dev Redis/backend ports), `e121bfb` (adversarial fix: whitespace/case-insensitive placeholder comparison).
- The adversarial round found the exact-match placeholder check could be bypassed by lowercasing the value or adding trailing whitespace — a CRITICAL gap in a CRITICAL finding's own fix. `e121bfb` normalises both sides (`.strip().lower()`) before comparing, for `SECRET_KEY` and `ANONYMIZATION_SALT`.
- Evidence: `tests/scripts/test_compose_hardening.py` GREEN 37 passed; full suite after `e121bfb`, `tests/adversarial/` 31 passed, 8 xfailed, exit 0.

### W1-02 — Bootable, hardened production config
- Findings: SEC-F1, SEC-03, SEC-06, SEC-F2, OPS-15. Commits: `29fab2f` (`setup.sh` writes a bootable `.env.production`, drops the 7-day token default), `4518e2f` (nginx security headers, CSP with the theme-script hash), `948ddf5` (10 MB `client_max_body_size`, `AUTH_REVOCATION_FAIL_CLOSED` documented in `.env.example`).
- Evidence: `tests/scripts/` 37 passed; full suite 1999 passed, 6 skipped, 1 xfailed, exit 0.

### W1-03 — Real client IP for rate limits; portal behind a flag; login timing
- Findings: SEC-04, SEC-10, SEC-17. Commits: `b315d25` (`core/client_ip.py`, `TRUSTED_PROXIES`), `8940316` (`CUSTOMER_PORTAL_ENABLED=False` default, per-request 404 dependency), `ec46dd6` (dummy-bcrypt constant-time login for unknown emails).
- Evidence: `tests/unit/test_client_ip.py` + `tests/integration/test_portal_flag.py` + `tests/unit/test_login_timing.py` all green; full suite 1856 passed (config agent) / 1994 passed (portal agent), 6 skipped, 1 xfailed.

### W1-04 — Role projection sweep: financial and design data — **partial**
- Findings: SEC-01, SEC-09, GDPR-03, GDPR-04, GDPR-09 (gating), SEC-15. Commits: `fd15807` (backend: `FINANCIAL_VIEW`/`DESIGN_VIEW`, `role_projection.py`, 22 endpoints gated or projected), `90fe1b5` (valuation PDF ADMIN-only), `083b1f9` (frontend: hide financial/design UI, fix 5 live crashes on `undefined` fields VIEWER now receives), `c8065f8` (closes the WebSocket side-channel that leaked price/cost past the same projection — see W2-13).
- Left open: SEC-15 (financial reads on repairs/materials/customer-stats still not audit-logged), `SollIstTab.tsx` has no internal guard (relies on the parent tab being hidden), and `App.tsx`'s route guards are now *stricter* than the backend model (VIEWER is blocked from four pages outright that the backend would now serve projected).
- Evidence: `tests/integration/test_viewer_role_projection.py` 54 passed; backend full suite 1859 passed; frontend full suite 542 passed (61 files).

### W1-05 — Consent store; allergies behind explicit consent — **partial**
- Findings: GDPR-02, GDPR-11, DOM-07. Commits: `996703f` (`CustomerConsent` model + migration, `consent_service.py`, write/read gating, Art. 15 export, erasure scrubbing), `f976482` (frontend `ConsentPanel`, `CustomerFormModal` edit-path grant-then-save flow).
- Left open: a brand-new customer's allergies can't be saved with consent in one step (the modal has no customer id to grant against before creation); `photo_use`/`marketing`/`email_contact` consents are recorded and grantable but nothing yet checks them before a photo is used or a marketing mail is sent.
- Evidence: `tests/integration/test_customer_allergy_consent.py` 13 passed; backend full suite 1837 passed; frontend `CustomerFormModal.consent.test.tsx` + `ConsentPanel.test.tsx` 8 passed, full suite 524 passed (56 files).

### W1-06 — Invoice status only via actions; tz-safe dates
- Findings: BE-05, BE-04. Commit: `41c1a4f`.
- `InvoiceUpdate` no longer accepts `status` (`extra="forbid"`); `POST /invoices/{id}/send` replaces PUT for DRAFT→SENT; aware `due_date`/`paid_date` normalise to naive UTC via the new `UtcNaiveDatetime` type instead of crashing.
- Evidence: `tests/integration/test_invoice_status_guard.py` 7 passed; full suite 1834 passed, 6 skipped, 1 xfailed.

### W1-07 — Invoice amounts from the agreed price; safe quote conversion — **partial**
- Findings: BE-01, BE-02, BE-17 (partial), BE-25 (not done). Commits: `6cecd9e` (`convert_quote` writes net, reuses the linked order instead of duplicating it), `41c1a4f` (invoices bill the agreed price — converted quote lines, then `Order.price`, then `calculated_price`→net — never cost).
- `docs/architecture/ADR-2026-09-25-price-semantics.md` records the NET decision (D-01).
- Left open: BE-25 (quotes still build lines from a separate, cost-based, hardcoded-rate path — no shared `LineItemBuilder` was created); the adversarial round found a quote with no lines converts silently to a zero-price CONFIRMED order (A3.1), two concurrent conversions of one quote both succeed and each creates an order (A3.3, `FOR UPDATE` is a no-op on SQLite, not re-verified on PG), and a quote's customer-match invariant isn't re-checked at conversion time (A3.4) — all three routed to W2-05.
- Evidence: `tests/integration/test_life_of_a_ring.py` (1,190.00 not 1,416.10); full suite 1834 passed.

### W1-08 — Altgold: correct valuation, immutable after signing, credit after tax — **partial**
- Findings: BE-03, BE-11, DOM-19, DOM-20 (partial). Commits: `41c1a4f` (Altgold credit is a post-tax deduction, not a negative line — fixes the 500), `33ddd44` (each item valued at its own metal's spot price; unknown alloys 422 instead of silently valuing at 0), `9639f64` (frontend sends the canonical string alloy code, not a number), `17adb24` (record locked 409 after SIGNED/CREDITED).
- Left open: DOM-20's fuller ask (`total_fine_gold_g` split per metal, an Ankaufsabschlag % field) needs a schema migration, out of this item's scope; no `AlloyType` for Palladium; the receipt PDF still prints one aggregate "Feingold" total.
- Evidence: `tests/unit/test_scrap_gold_valuation.py` 22 passed (15g 585 + 8g 750 → 14.775g; 10g Ag925 valued at silver price, not gold); backend full suite 1827 passed; frontend 493 passed (50 files).

### W1-09 — DATEV/lexoffice export correctness
- Finding: BE-13. Commit: `4e7b77f`.
- Draft/cancelled invoices excluded by default; account chosen per VAT rate (`DATEV_REVENUE_ACCOUNTS`, only 19%→8400 known); cancelled-and-issued invoices emit a reversal ("Storno") booking; created-date computed per call, not once at import time.
- Left open: only 19% has a mapped account (7%/0% need the Steuerberater, D-02); every CANCELLED invoice is conservatively treated as "was issued" for reversal purposes (no `issued_at`/`cancelled_at` column yet to tell the difference — closes once W1-10's snapshot fields are used here).
- Evidence: `tests/unit/test_accounting_export.py` 20 passed (new file — none existed before); full suite 2000 passed, 6 skipped, 1 xfailed.

### W1-10 — Immutable invoice snapshot; erasure keeps statutory records — **partial**
- Findings: GDPR-01, BE-23. Commits: `996703f` (erasure: 8 columns moved from `SCRUBBABLE_FIELDS` to `RETAINED_RECORD_FIELDS`, `retention_hold_until` legal hold, Altgold receipt PDF no longer deleted on erasure), `1230e8f` (`Invoice.snapshot` JSON at creation, frozen PDF + SHA-256 at SENT, write-once; PDF for a DRAFT renders from the snapshot instead of the live, possibly-anonymised customer row).
- Left open: the seller half of the snapshot only has workshop name/contact — full §14 UStG fields (tax number, Leistungsdatum) land with W2-04; nothing yet purges retained records once `retention_hold_until` expires (W5-07); the Art. 15 export of the snapshot fields is W5-08.
- Evidence: `tests/integration/test_gdpr_erasure_retains_tax_records.py` 3 passed; `tests/integration/test_invoice_snapshot.py` + `test_invoice_pdf_frozen.py` 12 passed; full suite (batch B) 3285 passed, 6 skipped, 1 xfailed (includes a 1,200-case parametrised rounding sweep from the same batch — see Open follow-ups).

### W1-11 — Metal consumption accumulates; AVERAGE draws across batches
- Findings: BE-07, BE-08. Commit: `d07b769`.
- A second consumption on an order now sums into `material_cost_calculated`/`actual_weight_g` instead of overwriting them; AVERAGE costing draws physically FIFO across batches while pricing every gram at the weighted average, instead of trying to take the whole draw from batch one.
- Left open: PG-only concurrency test not run live this session (no PG instance in the worktree); a same-order, different-batch race on the order aggregate (not on inventory) is possible in principle, untested.
- Evidence: `tests/unit/test_metal_consumption_accumulates.py` + `test_metal_average_draw.py` 7 passed; full suite 1987 passed, 6 skipped, 1 xfailed.

### W1-12 — Stop the customer-email loop; one message per event — **partial**
- Findings: BE-09, DOM-10, GDPR-13, VER-01, VER-02. Commits: `4fb66d7` (`automated_customer_email.py`: one mail per order event via the Kundeninfo/ CustomerUpdate path, not per staff-user loop; customer-facing text only, never the internal staff message; repair-ready notification now routed through `create_notification` so it publishes and is ADMIN/GOLDSMITH-only), `22612fb` (system monitor runs on one worker via a PostgreSQL advisory lock), `9af6d05` (DB-level unique dedupe key — the adversarial round's C2.2 finding: two concurrent monitor ticks on non-leader-locked engines could still double-send; the DB constraint closes it regardless of engine).
- Left open: BE-21 (the monitor still shares one session across its four scans — one error aborts the rest of that tick); no per-order opt-out column yet; the dedupe key is per `(order, kind)`, so a second genuine completion after an order is reopened sends no mail (adversarial C1.2, routed to W2-02).
- Evidence: `tests/integration/test_customer_email_once.py` 5 passed; `tests/unit/test_leader_lock.py` 6 passed; full suite 1818 passed, then 3285 passed after the C2.2 backstop (batch B).

### W1-13 — Customer portal route outside the staff providers
- Finding: FE-01. Commit: `405bf6c`.
- `App.tsx` split into `PublicShell`/`StaffApp`; `/portal` mounts with no `AuthProvider`/`ScannerProvider`/`TimeTrackingProvider`, so an unauthenticated visitor no longer triggers a 401→redirect-to-login loop.
- Evidence: `App.portal.test.tsx` 2 passed; frontend full suite unaffected.

### W1-14 — Honest bench session: per-user lifecycle, no fake pause, no PII cache — **partial**
- Findings: FE-07, FE-09, FE-10, FE-11, FE-19. Commits: `775c3c0` (timer context keyed on `user?.id`, resets and stops polling on logout, clears per-user localStorage/SW caches), `4208877` (removed the fake "Pause" button entirely — it froze the display while the server kept counting), `1d57dc8` (service-worker caching rewritten: `/api/*` is `NetworkOnly` except `activities`, so orders/materials/customers/prices are never written to Cache Storage; offline banner text corrected to "Änderungen werden nicht gespeichert").
- Left open: FE-09's other half — disabling submit buttons while offline — needs per-form wiring across pages out of this item's file list.
- Evidence: `frontend/src/contexts/UserLifecycle.test.tsx` + `TimerWidget.test.tsx` + `OfflineIndicator.test.tsx` + `cachingRules.test.ts` all green; built `dist/sw.js` contains no `api/v1/orders` or `api/v1/materials` substring (checked directly); frontend full suite 538 passed (56 files).

### W1-15 — QR bench flow works on a fresh device; entity-type aware actions — **partial**
- Findings: FE-02, FE-03. Commits: `3cf39de` (scan-to-timer-start now opens an activity picker instead of dead-ending on a permanently-null `activityId`; remembers the last activity per user), `d1c82a3` (repair scans never offer `start_timer`; take_photo/print_label route to `/repairs/:id`, not `/orders/:id`).
- Left open: FE-04 — unhandled quick-action IDs still throw "Unbekannte Aktion", and `?action=take-photo`/`?action=print-label`/`?edit=` deep-link params are still not read by the Order/Repair detail pages (this overlaps W2-01's own deep-link scope).
- Evidence: `ScanTimerFreshDevice.test.ts` + `ScanOverlayFreshDeviceTimer.test.tsx` + `test_scanner_service.py::TestRepairVsOrderDisambiguation` all green; frontend `src/test` 270 passed (19 files); backend `-k "scanner or scan"` 123 passed, 1 skipped.

### W1-16 — Estimator cost consistent with the shown median
- Finding: BE-10. Commit: `27ea4f4`.
- Per-activity hours are now zero-filled across the full matched order set (an activity logged by 1 of 5 comparable orders no longer contributes its full median); labor cost prices at `hours_p50 × blended rate` instead of summing per-activity costs that could exceed the shown median hours.
- Evidence: `tests/unit/test_estimator_cost_basis.py` 8 passed (new); full suite 1988 passed, 6 skipped, 1 xfailed.

### W1-17 — One running timer per user; sane time edits; owner checks
- Findings: BE-12, BE-18, SEC-13. Commit: `d5f4b22` (service/router logic); migration and further hardening folded into batch B (`fix-w1b-migrations.md`).
- Partial unique index `uq_time_entries_one_running` (`WHERE end_time IS NULL`) makes a double-tap start 409 instead of a silent second running timer or a `MultipleResultsFound` 500; `TimeEntryUpdate` rejects `end <= start`, spans over 24h, and mixing `duration_minutes` with an explicit `end_time`; stop/PUT/interruption routes now check ownership (or `TIME_VIEW_ALL`/ADMIN) before acting on someone else's entry.
- Left open: the migration refuses to run if any user already has several open timers in production — **run `SELECT user_id, COUNT(*) FROM time_entries WHERE end_time IS NULL GROUP BY user_id HAVING COUNT(*) > 1` before deploying**; the real two-session PG race test was not written (SQLite serialises writers, so the race was only proven via a missed pre-check, not genuine concurrency).
- Evidence: `tests/integration/test_single_running_timer.py` + `test_time_entry_validation.py` green; full suite (batch B) 3285 passed.

### W1-18 — Escaped labels, bounded image decoding, EXIF stripped — **partial**
- Findings: SEC-07 (partial — see below), SEC-18, GDPR-19 (partial). Commits: `e9cfca8` (every interpolated value in printable labels HTML-escaped), `77c7a35` (`Image.MAX_IMAGE_PIXELS` capped, `DecompressionBombWarning` raised as an error, decoding moved to a thread pool with a timeout, EXIF stripped from stored originals — not just the email variant).
- Left open: F-3 (the label print script is still blocked by CSP — this is a deliberate non-fix: relaxing to `'unsafe-inline'` was explicitly avoided); "labels print initials unless a setting enables full names" was not implemented (labels still print full names); `api/routers/materials.py`'s separate photo-upload path was not wired through the new hardening.
- Evidence: `tests/unit/test_label_service_escaping.py` 4 passed; `tests/unit/test_image_hardening.py` 10 passed; full suite 1856 passed (labels) / 1990 passed (images).

### W1-19 — Credential changes need the current password; roles assignable by ADMIN
- Findings: SEC-11, SEC-F6. Commits: `467bc3b` (`PUT /users/me` requires `current_password` for an email/password change), `61dc5a3` (ADMIN-only `role` field on the admin update route, last-admin demotion guard), `e121bfb` (adversarial fix: the *admin* route, `PUT /users/{id}`, could change an ADMIN's own email/password with **no** re-authentication at all, because `USER_EDIT` doesn't distinguish self from others — closed by requiring `current_password` on that route too when `user_id == current_user.id`).
- Evidence: `tests/integration/test_users_me_reauth.py` + `test_role_assignment.py` green; `tests/adversarial/test_admin_self_edit_bypasses_reauth.py` 3 passed after the fix; full suite 1856 passed / 1994 passed.

### W1-20 — No PII or tokens in request logs
- Findings: SEC-05, GDPR-10. Commits: `b315d25` (log `request.url.path` only, no query string), `4518e2f` (matching nginx access-log format, no query args/referer), `54c0815` (regression test scanning every `logger.*` call in `src/goldsmith_erp` for PII field references — tree was already clean, test guards against regression).
- Evidence: `tests/unit/test_request_logging_no_query.py` + `tests/unit/test_no_pii_in_logs.py` green; full suite 1994 passed.

### W2-13 — Live updates reach the screens — **partial**
- Findings: FE-08, BE-20 (partial). Commits: `c8065f8` (new `core/ws_manager.py`: one Redis subscriber per process, role-safe hint whitelist, dead-socket pruning, 30s heartbeat; `/ws/orders` and `/ws/notifications/{id}` — which relayed raw Redis payloads including `Order.price` to any authenticated socket, VIEWER included — removed in favour of one `/ws/events` socket), `faa106e` (frontend `WebSocketProvider`, `useRealtime` hook, `NotificationBell`/`TimeTrackingContext` wired to it).
- This also closes the adversarial round's **CRITICAL D.1 finding**: `/ws/orders` bypassed the entire W1-04 RBAC projection sweep and handed VIEWER live order prices with zero role check — the worst single finding in the adversarial report, because it invalidated fix W1-04's premise for anything reading the realtime feed. `581bf34` removes the now-obsolete leak test and its strict-xfail marker.
- Left open: Dashboard/Orders/OrderDetail/Repairs pages don't yet call the new `useRefetchOn` bus (the hub is ready, the pages that would consume it are owned by other in-flight items); `repair_updates`, `material_updates`, `consultation_updates`, `metal_price_updates` and `anomaly_alerts` are published but have no subscriber wired in `route_event` yet; W3-10's ask (reject `?token=`, check `is_active`, Origin check, lifespan-managed tasks) is still open.
- Evidence: `tests/integration/test_ws_fanout.py` 14 passed (incl. a VIEWER case receiving `order_id`+`status` but no price/cost/title/description); backend full suite 2088 passed, 6 skipped, 1 xfailed; frontend 557 passed (60 files).

### W2-15 — Metal price feed correct and visible
- Findings: BE-22, DOM-11c. Commit: `60a8289`.
- The feed now raises `MetalPriceCurrencyError` instead of silently treating a missing/zero EUR rate as 1:1 with USD; every price is asserted `> 0` before persisting; `EstimatorPanel` shows price/gram, currency, "Kurs vom `<Datum>`, Quelle: `<Quelle>`", a stale badge, and a red warning when a hardcoded fallback price is in use.
- Confirmed, not a bug: `PLATINUM_950` as an internal base/pure-metal storage key already had its fineness factor applied everywhere it's consumed (`ALLOY_RATIOS[PLATINUM_950] = 0.950`) — a regression test pins this so it isn't "fixed" into a real bug later.
- Left open: no debounce on the estimator's alloy-override input (re-fetches per keystroke); `metal_inventory_service.py`'s 2-decimal `price_per_gram` rounding intentionally deferred to W3-11.
- Evidence: `tests/unit/test_metal_price_service.py` 25 passed; backend full suite 2085 passed, 6 skipped, 1 xfailed; frontend 542 passed (56 files).

### Adversarial round (W1) — 39 tests, 13 confirmed defects, then closed
- `adversarial-w1.md`: a second agent wrote 39 tests attacking the W1 money, auth, email and RBAC fixes; **13 failed** on first run, revealing 13 real gaps (3 CRITICAL: the `/ws/orders` leak, the placeholder whitespace/case bypass, and the admin-self-edit reauth bypass — all covered above under their owning items).
- `fix-w1c-adversarial.md` (commit `e121bfb`): fixed the 2 CRITICAL findings it owned directly (placeholder normalisation, admin self-edit reauth). Commit `24a036d` marks the other 8 confirmed-but-not-yet-fixed findings `xfail(strict=True)` with a named owner (W2-02, W2-05, or "batch B"), so they fail loudly again the moment any of those owners' fixes regress or never land. Commit `581bf34` removes the D.1 test (obsolete — the whole `/ws/orders` endpoint it targeted no longer exists after W2-13) and lifts the xfail on C2.2 and A1.1/A1.2 once batch B's commits (`9af6d05`, `f827746`) closed them.
- Final state: 39/39 accounted for — 31 pass outright, 8 xfail-and-routed (of which C2.2, A1.1, A1.2 and D.1 have since landed and were unmarked; A3.1, A3.3, A3.4 route to W2-05; C1.2 routes to W2-02).
- Evidence: `tests/adversarial/` 31 passed, 8 xfailed, exit 0 (post-`e121bfb`); 0 unrouted findings.

## (b) Decisions taken during execution

Each needs a named person's confirmation before it should be treated as final
for production. Sources: `docs/architecture/ADR-2026-09-25-price-semantics.md`
and the scratch reports' own "Assumption"/"Decision followed" sections.

| Decision | What was implemented | Needs confirmation by |
|---|---|---|
| **NET price semantics** (D-01) | `Order.price` and all order/quote line amounts are NET (VAT excluded). Quote conversion writes `quote.subtotal`; the invoice adds VAT on top; a gross fallback (`calculated_price`) is converted with `Decimal`/`ROUND_HALF_UP`. Reversible to gross, but every path must change together. | Anne, Max (issue #28) |
| **Altgold credit is post-tax** (D-02) | VAT is computed on the full sale price; the Altgold credit (Ankaufswert) is deducted from the gross total afterward, with its own Ankaufbeleg, not netted before VAT. | Steuerberater |
| **DATEV account mapping** (D-02) | Only 19%→8400 is known; 7%/0% rates 422 with a clear message until an account is configured. No §19/§25a Kleinunternehmer switch implemented. | Steuerberater |
| **Public portal off by default** (D-03) | `CUSTOMER_PORTAL_ENABLED=False`; the router 404s per-request when disabled. Mails still carry a link (falls back to "reply by email" once W6-07 exists). | Anne, Max |
| **VIEWER role kept, made safe** (D-04) | VIEWER stays; the W1-04 sweep hides financial/design fields instead of removing the role. No APPRENTICE role added. | Anne, Max |
| **Allergy/health-data consent wording** (D-05) | Explicit per-purpose consent, `wording_version="v0-draft"` (placeholder text, not lawyer-approved); withdrawing consent clears the `allergies` field. ALLERGY no-gos stay visible to GOLDSMITH/ADMIN by role even without an active consent (a deliberate safety choice so material warnings keep working). | lawyer, Anna |
| **Invoice snapshot shape and retention** (D-06) | JSON snapshot at creation; frozen PDF + SHA-256 at SENT, write-once. Retention defaults used: invoices 8y, accepted quotes 6y, Altgold/GwG records 5y — **not yet verified against BEG IV/§257 HGB/§8 GwG by a tax professional.** | Steuerberater |
| **Reminder emails until CustomerMessage exists** (D-07) | At most once per order event, recorded as a `CustomerUpdate` row visible in Kundeninfo, never sent directly from a staff-notification path. | Max |
| **Estimator cost basis** (D-09) | Labor priced at `hours_p50 × blended rate`; `suggested_activities` zero-filled and shown only when present in ≥50% of the matched set. The alternative (per-activity medians as a breakdown) was not chosen. | Max |
| **Fake timer "Pause" removed** (D-15) | The Pause button (which froze the *display* while the server kept billing) was deleted outright in W1-14, not replaced. A real server-side pause (an interruption) is planned for W2-14 only if Anne wants it back. | Anne |
| **Valuation PDF export is ADMIN-only** | GOLDSMITH lost the ability to download the valuation PDF as part of the VIEWER-projection sweep (the permission model made ADMIN-only the safe default). If Anne needs GOLDSMITH to hand these to customers directly, it's a one-line permission grant. | Anne, Max |
| **GDPR erasure keeps statutory records via a legal hold, not a hard block** | Erasure now anonymises the customer row and sets `retention_hold_until` (newest retained record's year-end + 10y) rather than refusing the request outright; invoices/accepted quotes/signed Altgold records are excluded from `SCRUBBABLE_FIELDS` with their own `RETAINED_RECORD_FIELDS`/`RETAINED_RECORD_MODELS` lists. | Anna, lawyer |
| **All quotes retained on erasure, not just accepted ones** | Conservative: every quote (including drafts and rejected ones) is currently kept, though §147 AO likely only requires Handelsbriefe (sent/accepted). Retention length used is 10y; Steuerberater should confirm whether 8y (Buchungsbelege, BEG IV) applies instead. | Steuerberater |
| **System-monitor single-runner via advisory lock, PostgreSQL-only** | `pg_try_advisory_lock` elects one leader among uvicorn workers; on any non-PostgreSQL engine (e.g. SQLite dev) every process is treated as leader — a documented, not-fixed gap for non-PG deployments. Production must run PostgreSQL with `--workers 2`. | Max |
| **`ANONYMIZATION_SALT` length/entropy floor deliberately not added** | The adversarial round suggested mirroring `validate_secret_key`'s length check on the salt; not implemented because several out-of-scope test fixtures use shorter, realistic salts in `DEBUG=False` tests and would break. Flagged, not fixed. | Max / whoever owns SEC-02 next |
| **Realtime hints never carry price/cost/title/description over the wire** | The new `/ws/events` whitelist only ever sends `action, source, order_id, status, location` (orders) or ids/timestamps (timers/notifications) — clients must refetch the already-role-projected REST endpoint for details. This assumes no screen needs live financial data pushed, only a "something changed, go refetch" signal. | Max (product) |

## (c) Open follow-ups

Collected from every report's "Open items" section. Severity is a guess, not
a re-triage; suggested wave follows the master plan's existing item where one
owns the area, otherwise the most plausible new home.

| Item | Source report | Severity guess | Suggested wave |
|---|---|---|---|
| `App.tsx` route guards are stricter than the backend's new VIEWER model (blocks `/materials`, `/metal-inventory`, `/customers(/:id)`, `/repairs(/:id)` outright) | fix-w1b-viewer-ui.md | M | W1-04 follow-up / product decision |
| `SollIstTab.tsx` has no internal `FINANCIAL_VIEW` guard, relies solely on the parent tab being hidden | fix-w1b-viewer-ui.md | M | W3-04 (defense-in-depth, alongside `CostAlertBanner`'s pattern) |
| `cap_drop: [ALL]` (+ minimal `cap_add`) not added to any compose service — needs a live container runtime to boot-test | fix-w1-01-02-deploy.md | L | W5-03 |
| Image digest pinning (sha256) instead of exact tags | fix-w1-01-02-deploy.md | L | W5 (deliberate, separate process) |
| PG-only verification never run: migrations (enum text casts, partial-index predicates), the two-session timer race, quote-conversion race, and W1-11's concurrent-batch test | fix-w1b-migrations.md, fix-w1-11-metal.md, adversarial-w1.md | H | before any go-live checkpoint |
| **W1-17 migration aborts if a user already has several open timers** — run `SELECT user_id, COUNT(*) FROM time_entries WHERE end_time IS NULL GROUP BY user_id HAVING COUNT(*) > 1` before deploying | fix-w1b-migrations.md | H | deploy blocker, W1-17 |
| `QuoteService.calculate_totals` still uses float + `round()`, unlike the now-Decimal `InvoiceService.calculate_totals` | fix-w1-money-path.md, fix-w1b-migrations.md | M | W3-11 |
| `EstimatorPanel.module.css` uses hardcoded hex fallbacks (`var(--token, #hex)`) since the Wave-4 `src/ui` primitives don't exist yet | fix-w2-15-metal-prices.md | L | W4-01 |
| `CustomerFormModal` create-path: allergies can't be saved with consent for a brand-new customer (no id to grant against yet) | fix-w1-gdpr-erasure-consent.md, fix-w1b-consent-ui.md | M | W1-05 follow-up |
| Remaining WS hardening: reject `?token=` query auth, check `is_active` on connect, Origin check, lifespan-managed task cancellation | fix-w2-13-realtime.md | M | W3-10 |
| Unrouted realtime channels: `repair_updates`, `material_updates`, `consultation_updates`, `metal_price_updates`, `anomaly_alerts` (anomaly payload has employee names — route ADMIN-only) | fix-w2-13-realtime.md | M | W2-13 follow-up / W3-10 |
| Dashboard/Orders/OrderDetail/Repairs pages don't call the new `useRefetchOn` bus yet | fix-w2-13-realtime.md | M | owned by W2-01/02/03/07's pages |
| `total_fine_gold_g` still mixes metals into one aggregate (no per-metal gram breakdown); no Ankaufsabschlag % field | fix-w1-altgold.md | M | W2-16 (needs a schema migration) |
| Cost of the 1,200-case rounding boundary sweep (`test_invoice_totals_decimal.py`) on suite time — pushed the backend suite from ~2,000 to 3,285 tests in one batch | fix-w1b-migrations.md | L | test-suite hygiene, consider `@pytest.mark.slow` or trimming |
| Quote-conversion: zero-subtotal quote converts silently to a zero-price CONFIRMED order (A3.1); concurrent double-conversion creates two orders from one quote, `FOR UPDATE` unverified on real PG (A3.3); customer-reassignment invariant not re-checked at conversion (A3.4) | adversarial-w1.md | A3.3: H, A3.1/A3.4: M/L | W2-05 |
| Customer-mail dedupe has no per-occurrence bound: reopening a completed order and completing it again sends no second mail | adversarial-w1.md | M | W2-02 |
| `get_client_ip`: a malformed hop between two trusted proxies returns the last trusted address, not the real client (non-exploitable in the documented 2-hop topology); an IPv4-mapped-IPv6 peer isn't matched against IPv4 `TRUSTED_PROXIES` CIDRs (fails safe) | adversarial-w1.md | L | backlog |
| `ANONYMIZATION_SALT` has no length/entropy floor (see Decisions) | adversarial-w1.md, fix-w1c-adversarial.md | M | whoever owns SEC-02 next, alongside fixture updates |
| Full-suite "814 errors" (`RuntimeError: Event loop is closed`) reproduced at full-tree scale in one adversarial worktree; investigated and judged pre-existing/environmental (a sibling agent's clean run on the same merged tree showed 0 errors), not caused by any file in that agent's scope | fix-w1c-adversarial.md | M | needs a `tests/conftest.py`-owning agent to bisect; possibly W5-02 |
| DOM-12: `repair_service.complete_repair` still sets `customer_notified_at=now` with no actual send | fix-w1-email-loop.md | H | W2-02 (already the register's fix item for DOM-12) |
| No per-order customer-email opt-out column | fix-w1-email-loop.md | M | W6-02 |
| SEND_FAILED automated mail retries once per day forever while SMTP stays misconfigured | fix-w1-email-loop.md | L | W1-12 follow-up |
| Monitor still shares one DB session across its 4 scans (BE-21) — one error aborts the rest of that tick | fix-w1-email-loop.md | M | W1-12 follow-up (register already tracks BE-21 as open) |
| `api/routers/materials.py`'s photo-upload path is not wired through the new EXIF-stripping/bomb-protection hardening | fix-w1-18-images.md | M | W1-18 follow-up |
| F-3: the label print script is still blocked by CSP (deliberately not relaxed to `'unsafe-inline'`) | fix-w1-security-config.md | M | needs a CSP-hash-friendly print approach |
| SEC-04 extras: slowapi rate-limit storage still in-memory per worker (no Redis `storage_uri`); `TRUSTED_PROXIES` should be narrowed per deployment LAN | fix-w1-security-config.md | M | W1-03 follow-up |
| No email notice to the old address when a user's email/password changes (SEC-11) | fix-w1-security-config.md | L | W1-19 follow-up |
| `pdf_service.py` doesn't yet print the Altgold-Gutschrift or Zahlbetrag on the invoice PDF | fix-w1-money-path.md | M | W2-04 |
| Existing orders from earlier quote conversions may hold gross values in `Order.price` under the new NET semantics — needs a one-off data review before go-live | fix-w1-money-path.md | H | pre-go-live data migration |
| Invoice `tax_rate` defaults to 19% even when a converted quote used a different rate | fix-w1-money-path.md | M | W2-04 |
| Quote conversion still bypasses the CONFIRMED Pflichtfelder gate (BE-06's state machine doesn't exist yet) | fix-w1-money-path.md | M | W2-07 |
| `update_invoice` still allows notes/due_date edits on SENT/OVERDUE invoices (the frozen PDF itself is unaffected) | fix-w1b-migrations.md | M | W2-04 (issued-invoice locking) |
| C2.2 edge case: a crash between `create_draft` and send permanently blocks that dedupe key; a stale `SEND_FAILED` retry can collide with a newer live send | fix-w1b-migrations.md | M | W6-01 (outbox) territory |
| `ActiveTimerWidget.tsx` still has the same fake-pause pattern as the fixed `TimerWidget.tsx`, but is dead/orphaned code | fix-w1-14-bench-session.md | L | W3-01 (dead-code cleanup) |
| `MainLayout.tsx` calls `timeTrackingApi.stop()` directly, bypassing `TimeTrackingContext` (harmless today due to self-healing polling) | fix-w1-frontend-flows.md | L | cleanup when `MainLayout.tsx` is next touched |
| `api/client.ts`'s interceptor still hard-redirects to `/login` on any `/refresh` 401 unless the path is `/login` (portal no longer triggers it, but no explicit public-path exemption) | fix-w1-frontend-flows.md | L | W1-13 follow-up |
| Time booking on repairs needs `TimeEntry.repair_job_id` — until then `start_timer` is hidden for repairs on both ends | fix-w1-frontend-flows.md | M | W6-04 (jobs spine) |
| `db/repositories/customer.py::update_consent()` targets attributes that no longer exist (dead code) | fix-w1-gdpr-erasure-consent.md | L | W3-09 |
| `seed_demo.py` sets `allergies="Nickel"` directly via the ORM with no consent row (demo UI will now hide it) | fix-w1-gdpr-erasure-consent.md | L | demo-data cleanup |
| Repair `item_description`/`diagnosis_notes` still shown to VIEWER (front-desk needs them to identify a piece) | fix-w1-viewer-leaks.md | M | product decision |
| `/customers/top` now nests `CustomerListItem` under `customer`; `frontend/src/api/customers.ts` consumes it as `any[]` | fix-w1-viewer-leaks.md | L | cleanup |
| Hub's `get_message(timeout=1.0)` poll adds up to ~1s idle wake-ups per process | fix-w2-13-realtime.md | L | revisit if it matters at scale |
| `EstimatorPanel`'s metal-price fetch has no debounce (re-fires per keystroke on the alloy-override input) | fix-w2-15-metal-prices.md | L | polish |

## (d) How to verify locally

Environment values below match `.github/workflows/ci.yml` exactly (throwaway,
non-secret — carry no security meaning outside CI/local dev).

```bash
# Backend, SQLite-backed unit/integration suite (from repo root, not src/ —
# testpaths=["tests"] means running from src/ collects 0 tests):
export SECRET_KEY=ci-test-secret-key-minimum-32-characters-long-enough
export ENCRYPTION_KEY=V0Ae_U1MhSkUCNugAmmQV7Jl2GnxkizHeurQnglXVOc=
export ANONYMIZATION_SALT=testsalt1234567890abcdef
export DEBUG=true
export PYTHONPATH=$PWD/src
poetry run pytest -q

# Backend gates (from src/):
cd src
poetry run mypy goldsmith_erp/ --ignore-missing-imports
poetry run black --check goldsmith_erp/
poetry run isort --check-only goldsmith_erp/
poetry run bandit -r goldsmith_erp/ -c ../pyproject.toml
cd ..

# Adversarial round only:
poetry run pytest -q tests/adversarial/ -rxX
# Expect: passed + xfailed, 0 failed, 0 unrouted (see the adversarial section
# above for which findings are still behind an xfail and who owns them next).

# PostgreSQL-dependent paths (migrations, partial indexes, FOR UPDATE,
# tz-aware columns) — none of this was run in this pass; a PG instance is
# required:
export TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test
poetry run pytest -q tests/integration/<file>
poetry run alembic upgrade head && poetry run alembic downgrade -1 && poetry run alembic upgrade head

# Frontend:
cd frontend
yarn vitest run                    # full suite
yarn vitest run <path>              # a single file
npx tsc --noEmit
node node_modules/vite/bin/vite.js build   # `yarn build` itself still exits
                                             # 127 in a fresh checkout — FE-25,
                                             # unresolved; this is the documented
                                             # workaround every fix agent used
```

Every fix agent ran from a git worktree with no `.env` file, so `Settings()`
needs the four env vars above set explicitly or it refuses to boot
(`ENCRYPTION_KEY must be set in production`) — this is expected, not a bug.

## (e) Checkpoint for Max

Wave 1 is functionally complete (20/20 items landed; 9 of them partial, all
documented above and in `MASTER-FIX-PLAN.md` section 0). Two pieces of Wave 2
(W2-13, W2-15) and one adversarial round have also landed. Before treating
this as a release candidate:

1. **Run `/code-review ultra` on this branch now that Wave 1 is complete.** This is user-triggered — the orchestrator that produced this document cannot run it. Point it at `audit/2026-09-fixes` vs `main`.
2. Work through the **Decisions** table above with the named people — several (NET price semantics, Altgold VAT treatment, invoice retention periods, the allergy consent wording) need a Steuerberater or lawyer's sign-off before this goes near real customer data, and are currently running on this session's best-guess default.
3. Treat the **H-severity open follow-ups** (PG-only verification, the W1-17 migration's open-timer pre-check, the pre-go-live `Order.price` data review, DOM-12's false `customer_notified_at`) as blockers for any production cutover, not backlog.
4. The full findings register and master fix plan now distinguish `fixed`, `partial: <what's left>`, and `open` — re-run this same method (reports first, commits second, never invent a status) after each future wave lands.
