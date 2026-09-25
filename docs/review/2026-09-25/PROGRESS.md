# Progress: audit 2026-09-25 fix waves

Tracks what has actually landed on `audit/2026-09-fixes` against
[FINDINGS-REGISTER.md](FINDINGS-REGISTER.md) (212 findings) and
[MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md) (83 fix items). Source of truth: the
~53 scratch reports in `.orchestrated-fable/ux-erp-audit-2026-09/` (`fix-*.md`,
`adversarial-w1.md`, `fix-w1c-adversarial.md`, `live/LIVE-VERIFICATION.md`,
`live2/LIVE-VERIFICATION-2.md`) and `git log --oneline main..HEAD` on this
branch. Where a report and a commit message disagreed, the report won. PR #51
(draft) is the review vehicle for this branch.

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
- Left open: BE-25 (quotes still build lines from a separate, cost-based, hardcoded-rate path — no shared `LineItemBuilder` was created); the adversarial round found a quote with no lines converts silently to a zero-price CONFIRMED order (A3.1), two concurrent conversions of one quote both succeed and each creates an order (A3.3, `FOR UPDATE` is a no-op on SQLite, not re-verified on PG), and a quote's customer-match invariant isn't re-checked at conversion time (A3.4) — all three routed to W2-05, **since closed there, see below**.
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
- Left open: the seller half of the snapshot only has workshop name/contact — full §14 UStG fields (tax number, Leistungsdatum) land with W2-04, **since partially closed there, see below**; nothing yet purges retained records once `retention_hold_until` expires (W5-07 landed the sweep mechanism, but extending it to these records is still open); the Art. 15 export of the snapshot fields shipped with W5-08.
- Evidence: `tests/integration/test_gdpr_erasure_retains_tax_records.py` 3 passed; `tests/integration/test_invoice_snapshot.py` + `test_invoice_pdf_frozen.py` 12 passed; full suite (batch B) 3285 passed, 6 skipped, 1 xfailed (includes a 1,200-case parametrised rounding sweep from the same batch — see Open follow-ups).

### W1-11 — Metal consumption accumulates; AVERAGE draws across batches
- Findings: BE-07, BE-08. Commit: `d07b769`.
- A second consumption on an order now sums into `material_cost_calculated`/`actual_weight_g` instead of overwriting them; AVERAGE costing draws physically FIFO across batches while pricing every gram at the weighted average, instead of trying to take the whole draw from batch one.
- Left open: PG-only concurrency test not run live this session (no PG instance in the worktree); a same-order, different-batch race on the order aggregate (not on inventory) is possible in principle, untested.
- Evidence: `tests/unit/test_metal_consumption_accumulates.py` + `test_metal_average_draw.py` 7 passed; full suite 1987 passed, 6 skipped, 1 xfailed.

### W1-12 — Stop the customer-email loop; one message per event — **partial**
- Findings: BE-09, DOM-10, GDPR-13, VER-01, VER-02. Commits: `4fb66d7` (`automated_customer_email.py`: one mail per order event via the Kundeninfo/ CustomerUpdate path, not per staff-user loop; customer-facing text only, never the internal staff message; repair-ready notification now routed through `create_notification` so it publishes and is ADMIN/GOLDSMITH-only), `22612fb` (system monitor runs on one worker via a PostgreSQL advisory lock), `9af6d05` (DB-level unique dedupe key — the adversarial round's C2.2 finding: two concurrent monitor ticks on non-leader-locked engines could still double-send; the DB constraint closes it regardless of engine).
- Left open: BE-21 (the monitor still shares one session across its four scans — one error aborts the rest of that tick); no per-order opt-out column yet (W6-02 added an Art. 21 opt-out mechanism instead, via consent rows); the dedupe key is per `(order, kind)`, so a second genuine completion after an order is reopened sends no mail — **this C1.2 gap was closed for repairs in W2-02 (`718791a`)**, the order-side equivalent is unconfirmed.
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
- Left open: FE-04 — unhandled quick-action IDs still throw "Unbekannte Aktion", and `?action=take-photo`/`?action=print-label`/`?edit=` deep-link params are still not read by the Order/Repair detail pages. **The photo deep link was closed by W2-01** (`8f8e1b9`, `f5cf713`); `print-label`, `consume-material` and `edit=location` are still unhandled.
- Evidence: `ScanTimerFreshDevice.test.ts` + `ScanOverlayFreshDeviceTimer.test.tsx` + `test_scanner_service.py::TestRepairVsOrderDisambiguation` all green; frontend `src/test` 270 passed (19 files); backend `-k "scanner or scan"` 123 passed, 1 skipped.

### W1-16 — Estimator cost consistent with the shown median
- Finding: BE-10. Commit: `27ea4f4`.
- Per-activity hours are now zero-filled across the full matched order set (an activity logged by 1 of 5 comparable orders no longer contributes its full median); labor cost prices at `hours_p50 × blended rate` instead of summing per-activity costs that could exceed the shown median hours.
- Evidence: `tests/unit/test_estimator_cost_basis.py` 8 passed (new); full suite 1988 passed, 6 skipped, 1 xfailed.

### W1-17 — One running timer per user; sane time edits; owner checks
- Findings: BE-12, BE-18, SEC-13. Commit: `d5f4b22` (service/router logic); migration and further hardening folded into batch B (`fix-w1b-migrations.md`).
- Partial unique index `uq_time_entries_one_running` (`WHERE end_time IS NULL`) makes a double-tap start 409 instead of a silent second running timer or a `MultipleResultsFound` 500; `TimeEntryUpdate` rejects `end <= start`, spans over 24h, and mixing `duration_minutes` with an explicit `end_time`; stop/PUT/interruption routes now check ownership (or `TIME_VIEW_ALL`/ADMIN) before acting on someone else's entry.
- Left open: the migration refuses to run if any user already has several open timers in production — **run `SELECT user_id, COUNT(*) FROM time_entries WHERE end_time IS NULL GROUP BY user_id HAVING COUNT(*) > 1` before deploying**; the real two-session PG race test was not written in W1, **it was added and run in the live-verification pass 1, see below — no actual race was found in 5 repeated runs**.
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

### Adversarial round (W1) — 39 tests, 13 confirmed defects, then closed
- `adversarial-w1.md`: a second agent wrote 39 tests attacking the W1 money, auth, email and RBAC fixes; **13 failed** on first run, revealing 13 real gaps (3 CRITICAL: the `/ws/orders` leak, the placeholder whitespace/case bypass, and the admin-self-edit reauth bypass — all covered above under their owning items).
- `fix-w1c-adversarial.md` (commit `e121bfb`): fixed the 2 CRITICAL findings it owned directly (placeholder normalisation, admin self-edit reauth). Commit `24a036d` marks the other 8 confirmed-but-not-yet-fixed findings `xfail(strict=True)` with a named owner (W2-02, W2-05, or "batch B"), so they fail loudly again the moment any of those owners' fixes regress or never land. Commit `581bf34` removes the D.1 test (obsolete — the whole `/ws/orders` endpoint it targeted no longer exists after W2-13) and lifts the xfail on C2.2 and A1.1/A1.2 once batch B's commits (`9af6d05`, `f827746`) closed them.
- Final state: 39/39 accounted for — 31 pass outright, 8 xfail-and-routed. **All 8 have since landed**: A3.1/A3.3/A3.4 closed by W2-05 (`ef3b1f8`), C1.2 closed by W2-02 (`718791a`), C2.2/D.1/A1.1/A1.2 already closed in the original pass.
- Evidence: `tests/adversarial/` 31 passed, 8 xfailed, exit 0 (post-`e121bfb`); 0 unrouted findings.

### W2-01 — Order photo upload and scanner deep links
- Findings: FE-13, DOM-01, FE-04 (photo action). Commits: `2d1a92d` (`first_photo_id` in the orders list projection), `342ac5a` (thumbnail column), `f5cf713` (photo upload on the Fotos tab and order deep links), `8f8e1b9` (scanner "Foto" on an order opens the camera on the Fotos tab), `836c281` (refresh orders list, open order on 'orders' hints).
- New `PhotoUpload` component; scanning "Foto" on an order opens `/orders/{id}?tab=fotos&capture=1` and auto-triggers the camera — 3 taps end to end (scan, capture, tick in the picker); iOS Safari may block the auto-open, falling back to a 4th manual tap on the visible button.
- Left open: `?edit=location`, `?action=print-label` and `?action=consume-material` deep links still unhandled on the order page; no `order_updates` publish on photo upload/delete so realtime refetch misses new photos from other devices (**closed later by W7 hygiene**, `7287033`); no client-side photo downscale (>8MB rejected with a German error); `CustomerDetailPage` had a wrong photo URL and an N+1 query (**also closed later by W7 hygiene**, `3d43ea2`).
- Evidence: `pytest tests/` after the realtime merge 3393 passed, 6 skipped, 1 xfailed; frontend `yarn vitest run` 74 files, 617 passed; `tsc` 0.

### W2-02 — Repairs get customer updates; truthful notified timestamp
- Finding: DOM-12. Commit: `664231b`. Also closes the C1.2 × C2.2 dedupe interaction bug found mid-batch, `718791a`.
- `complete_repair` no longer stamps a false `customer_notified_at`; instead it creates a DRAFT `CustomerUpdate` on READY, sent through the existing CAS-protected `CustomerUpdateService.send`, and the timestamp is only stamped once `delivered=true`. `718791a` fixes a real regression the two dedupe mechanisms caused each other: C1.2's occurrence-scoped `_already_handled` check and C2.2's DB-level unique dedupe key disagreed — the key itself wasn't occurrence-scoped, so a second legitimate occurrence's insert hit `IntegrityError`, whose rollback broke the caller with `MissingGreenlet`. Fixed by folding the occurrence into the dedupe key and routing the automated sender's insert through a `begin_nested()` SAVEPOINT that raises a typed `DuplicateDedupeKeyError` instead.
- Left open: a PDF-manual "mark delivered" for a repair update doesn't stamp `RepairJob.customer_notified_at`; `RepairCustomerUpdatePanel` has no PDF-download/mark-delivered fallback when SMTP is down.
- Evidence: `test_repair_updates.py` 7 passed; dedupe adversarial test 2 passed post-fix; full suite 3475 passed, 6 skipped, 4 xfailed (348.27s); frontend full suite 543 passed (57 files).

### W2-03 — "Heute" dashboard: overdue first, customer-pending lanes, repairs included — **partial**
- Findings: FE-05, DOM-14, DOM-15, DOM-15b. Commit(s) referenced by the report: `9bb29ba`, `f6b4c57`.
- New `GET /api/v1/dashboard/today` aggregates overdue/due-soon work items, a customer-pending lane (cost changes, failed updates, ready repairs/orders, sent quotes) and today's timers, role-projected (no financials for VIEWER); the frontend `TodayView` replaces the old dashboard for every role.
- Left open: DOM-15c (a receivables/overdue-invoices glance) explicitly not built; `/quotes` still ignores `?quote_id` so the dashboard's quote row opens the quotes list, not the specific quote (FE-18); old `DeadlinesWidget` unmounted but still exported (dead code); `days_overdue`'s Berlin-day calculation could be off by one for legacy naive-UTC deadlines.
- Evidence: `pytest -k dashboard` 10 passed; full backend suite 2128 passed, 6 skipped, 1 xfailed. Frontend vitest 71 files/603 tests passed; `tsc` 0.

### W2-04 — §14 UStG invoice, workshop settings, Storno, gap-free numbering — **partial**
- Findings: DOM-24 (partial), DOM-24b, BE-16. Commit: `4286fc2`.
- New `WorkshopSettings`/`NumberSequence` tables back gap-free RE/KV numbering and full §14 Abs. 4 UStG invoice content; a Storno (credit-note) flow with immutable linkage was added.
- Left open: D-12's order number (Auftragsnummer) is not built (the counter service is ready for WG/REP adoption); `templates/invoice.html`'s preview template was not updated to the new §14 layout; issuing an invoice with incomplete Werkstatt-Stammdaten only warns, doesn't block; only one VAT rate per invoice is supported; `InvoicesPage.tsx` has no Storno button/badge yet.
- Evidence: final full backend suite 1 failed (pre-existing, unrelated adversarial dedupe test owned by another agent), 3722 passed, 6 skipped, 1 xfailed (baseline 3682, +40 new). Frontend `tsc` 0; vitest 81 files/657 passed.

### W2-05 — Quote Versenden sends; consultation to quote to order carries data
- Findings: DOM-11, DOM-11d, FE-18 (partial), DOM-03, DOM-11b, DOM-09, A3.1, A3.3, A3.4. Commits: `34d1cfb` (Versenden emails the quote PDF or records PDF_MANUAL), `ef3b1f8` (conversion carries deadline/alloy/ring size/photos).
- `send_quote` now actually calls the email service (previously only flipped status); `approve_quote` requires `response_method` as agreement evidence; `convert_quote` gained a CAS guard (closes A3.3), a 0.00-price guard (A3.1), and a customer-match re-check (A3.4) — closing the three adversarial-round gaps routed here from W1-07; consultation fields (deadline, metal/alloy, ring size, photos) now flow through the quote into the created order.
- Left open: concurrent "Versenden" clicks could still send two emails (no CAS before send); a quote with no linked order leaves a delivery record with `order_id=NULL`, invisible in any Kundeninfo tab; approval evidence is stored as text in `quote.notes`, not a dedicated column; the approve/decline link in the customer email was not built (that's W6-07); gemstones/weight from W2-06 are not yet carried into the order on conversion.
- Evidence: `pytest tests/ -k "quote or consultation or email"` 282 passed; full suite 2088 passed, 6 skipped, 1 xfailed. Frontend vitest 57 files, 545 passed.

### W2-06 / W2-11 / W2-14 / W2-16 — Gemstone intake, interruption time math, Altgold ID capture, handover PDF
- **W2-06** (order intake: type, alloy, gemstones) — done. Findings: DOM-04 (partial), DOM-05, DOM-06, DOM-09. Commit: `a57beac`.
  - Gemstone (4C, Fassung, Kundenstein) CRUD and PDF blocks; single alloy picker replaces the previous double metal/alloy entry; order intake now sets `order_type`.
  - Left open: gemstones not wired into quote/invoice PDF renderer callers; a new order can't add stones until it's saved; legacy metal types (333/900 gold) missing from the new picker; a Kundenstein (customer-supplied gemstone) cannot carry a cost value (422 if attempted, by design).
- **W2-14** (interruptions reduce time) — done. Finding: BE-19. Commit: `93889f8`.
  - Interruption minutes now net real elapsed time; `actual_hours` is recomputed instead of frozen at completion.
  - Left open: a real server-side pause/resume UI (D-15) was explicitly not built; `InterruptionRead` lacks `resumed_at`; summaries still use gross minutes.
- **W2-16** (Altgold Ankaufsbuch and optional ID capture) — done. Finding: DOM-21. Commit: `abd162c`.
  - ID-document fields (encrypted) plus Ankaufsbuch CSV/PDF export, gated on ID capture above the €2,000 threshold.
  - Left open: GDPR Art. 15 export and 5-year retention of the ID fields not implemented; no admin export UI; the €2,000 threshold applies to purchase value regardless of payout method (no cash/credit field exists — flagged as an assumption needing validation); pre-existing `ScrapGoldCreate` requires `order_id`/`customer_id` while the frontend posts `{}`.
- **W2-11** (handover report PDF and valuation button) — partial. Findings: DOM-34, DOM-35 (partial). Commit: `f6f5628`.
  - New Abholprotokoll PDF and a Wertgutachten button on delivered orders.
  - Left open: handover care text is hardcoded, not workshop-editable; the DeliveredActions button is shown only right after the delivered status change, not persistently (by design — "keep the edit minimal").
- Shared evidence for this batch: `pytest -k "gemstone or scrap or migration or pdf or valuation or order"` 700 passed; final full suite 3949 passed, 12 skipped, 1 xfailed (baseline ~3740). Frontend: `tsc` 0; vitest 106 files/865 passed; hex-ratchet 2086 (baseline 2087).

### W2-07 — Order lifecycle: transition table, history, on-hold and cancelled
- Findings: ARCH-01, BE-06, DOM-13, DOM-46. Commits: `34d1c6d` (schema + migration, on_hold/cancelled, NEW mapping), `e5511ef` (`order_workflow.py` transition table + service wiring), `4acfa8d` (`PATCH /orders/{id}/status`, `GET /orders/{id}/timeline`).
- New `order_workflow.py` transition table, an `order_events` audit table, and the two new endpoints; legacy `NEW` status maps to DRAFT (no price) or CONFIRMED (a price already set); reasons required for hold/cancel.
- Left open: `quote_service.convert_quote` still creates orders with `status=CONFIRMED` directly, bypassing the transition/validation/creation event; `dashboard_service` doesn't yet use the new `order_workflow` helpers; `customer_portal.py` and `scanner_service`'s label/status maps lack on_hold/cancelled; a rework transition (completed→in_progress) keeps a stale `completed_at`; the legacy `order_status_history` table and the dead `db/repositories/order.py` writer remain (ARCH-03); the migration was not exercised on PostgreSQL, flagged **H severity, before any go-live checkpoint**.
- Evidence: `test_order_workflow.py`/`test_order_timeline.py`/migration tests 181 passed; full suite 3572 passed, 6 skipped, 1 xfailed.

### W2-08 — Order page: 5 tabs, Weiter button, real timeline, milestone prompts
- Findings: DOM-16, DOM-17, DOM-18, DOM-30. Commits: `962edbd`, `487d3e2`, `b033057`, `1aa8f0b`, `72b9e9e`.
- Order page collapsed from up to 14 ad-hoc tabs to 5 (Übersicht/Arbeit/Fotos/Kunde/Verlauf) with a WAI-ARIA tablist; header "Weiter: &lt;next status&gt;" button drives the status endpoint; `OrderTimeline` renders the real `/timeline` feed; milestone prompts pre-fill a Kundeninfo draft on completed/delivered.
- Left open: status label maps are still duplicated across pages (needs the Wave 4 `src/design/status.ts`); the status transition table is mirrored client-side; `PRIMARY_NEXT_STATUS` next-step suggestions are a product guess pending Anne/@goldsmith's confirmation; a milestone prompt also fires on a realtime refetch triggered by another device's change.
- Evidence: final vitest 81 files, 678 passed (+28 vs baseline); `tsc` 0; hex-ratchet 2076 (baseline 2113, −37).

### W2-09 — Hallmark vocabulary + soft completion gate — **partial**
- Findings: DOM-22, DOM-23; DOM-44 confirmed still open. Decision D-10.
- Feingehalt options expanded 4→10 via a new `hallmark_vocabulary.py` shared by the Pydantic validator and the completion gate; added a "nicht punziert: &lt;Grund&gt;" documented-exception path; tightened the gate so an additional mark alone (e.g. Meisterzeichen) no longer satisfies it; OrderDetailPage now auto-opens the QC modal on the 409 and retries. In the QC modal, the option matching the order's stored alloy is flagged but deliberately not pre-checked, so the goldsmith confirms what they physically read.
- Left open: `frontend/src/api/hallmarks.ts` (orphaned OrderHallmark client) confirmed still dead, not removed (DOM-44); `AlloyType` still missing bare 935 (Ag935) and Palladium; **the report's own post-merge full backend suite run did not complete/confirm in-session (contended CPU) — flagged as needing re-verification**, though later merges in this branch's history (Wave 5/6/7) ran clean full suites that included this code.
- Evidence: `test_hallmark_vocabulary.py` 76 passed; `test_hallmark_soft_gate.py` 17 passed; pre-merge full suite 3910 passed, 6 skipped, 1 xfailed. Frontend post-merge: 863 passed/0 failed (103 files), `tsc` clean.

### W2-10 — Customers without email
- Findings: DOM-02, D-11. Commit: `16eb65a`.
- Customer email made optional; requires at least one of email/phone/mobile.
- Left open: `CustomerInfoCard.tsx`'s local `Customer.email: string` type should become optional; CSV customer import still requires an email column.
- Evidence: shared with W2-04's suite run above (one combined report).

### W2-12 — Repair intake at the counter; customer 360 — **partial**
- Findings: FE-17, DOM-08 (partial), DOM-38 (partial). Commits: `470d3b0`, `49e2efd`, `d8f13d2`, `3b91696`, `3340086`, `22dfd7a` (merge), `07e9714` (types).
- New single-screen `RepairIntakeScreen` (chips, camera, price) cuts intake from 16–18 taps to ~14 full / ~6 minimum, plus prints an Annahmeschein PDF; new `GET /customers/{id}/activity` powers a "Verlauf" tab on CustomerDetailPage merging orders/repairs/quotes/invoices/updates.
- Left open: intake signature persistence explicitly stopped, no schema change made; consultations still missing from Verlauf despite DOM-38 naming them; invoices in Verlauf still capped at 200; the stone-liability clause and pickup note in the Annahmeschein PDF are draft wording pending legal/workshop-owner review; customer-activity UNION verified on SQLite only, not against PostgreSQL.
- Evidence: new backend tests 19 passed (RED was 14 failed/5 passed); full suite 3897 passed, 12 skipped, 1 xfailed. Frontend vitest 107 files, 868 passed; hex-ratchet 2087 (baseline 2087).

### W2-13 — Live updates reach the screens — **partial**
- Findings: FE-08, BE-20 (partial). Commits: `c8065f8` (new `core/ws_manager.py`: one Redis subscriber per process, role-safe hint whitelist, dead-socket pruning, 30s heartbeat; `/ws/orders` and `/ws/notifications/{id}` — which relayed raw Redis payloads including `Order.price` to any authenticated socket, VIEWER included — removed in favour of one `/ws/events` socket), `faa106e` (frontend `WebSocketProvider`, `useRealtime` hook, `NotificationBell`/`TimeTrackingContext` wired to it).
- This also closes the adversarial round's **CRITICAL D.1 finding**: `/ws/orders` bypassed the entire W1-04 RBAC projection sweep and handed VIEWER live order prices with zero role check — the worst single finding in the adversarial report, because it invalidated fix W1-04's premise for anything reading the realtime feed. `581bf34` removes the now-obsolete leak test and its strict-xfail marker.
- Left open: Dashboard/Orders/OrderDetail/Repairs pages don't yet call the new `useRefetchOn` bus; `repair_updates`, `material_updates`, `consultation_updates`, `metal_price_updates` and `anomaly_alerts` are published but have no subscriber wired in `route_event` yet (**confirmed still true after the later W7 hygiene pass, which itself started publishing `repair_updates` without wiring a subscriber**); W3-10's ask (reject `?token=`, check `is_active`, Origin check, lifespan-managed tasks) is still open.
- Evidence: `tests/integration/test_ws_fanout.py` 14 passed (incl. a VIEWER case receiving `order_id`+`status` but no price/cost/title/description); backend full suite 2088 passed, 6 skipped, 1 xfailed; frontend 557 passed (60 files).

### W2-15 — Metal price feed correct and visible
- Findings: BE-22, DOM-11c. Commit: `60a8289`.
- The feed now raises `MetalPriceCurrencyError` instead of silently treating a missing/zero EUR rate as 1:1 with USD; every price is asserted `> 0` before persisting; `EstimatorPanel` shows price/gram, currency, "Kurs vom `<Datum>`, Quelle: `<Quelle>`", a stale badge, and a red warning when a hardcoded fallback price is in use.
- Confirmed, not a bug: `PLATINUM_950` as an internal base/pure-metal storage key already had its fineness factor applied everywhere it's consumed (`ALLOY_RATIOS[PLATINUM_950] = 0.950`) — a regression test pins this so it isn't "fixed" into a real bug later.
- Left open: no debounce on the estimator's alloy-override input (re-fetches per keystroke); `metal_inventory_service.py`'s 2-decimal `price_per_gram` rounding intentionally deferred to W3-11.
- Evidence: `tests/unit/test_metal_price_service.py` 25 passed; backend full suite 2085 passed, 6 skipped, 1 xfailed; frontend 542 passed (56 files).

### W2b — Per-occurrence dedupe key vs. C2.2 unique-index interaction
- See W2-02 above (`718791a`) — folded into that item's landing since it fixes an interaction between DOM-12's fix and W1-12's C2.2 backstop.

### W3-02 — Generated frontend API types with a CI drift gate
- Finding: FE-12; ARCH-07. Commits: `f532896` (generate frontend API types from OpenAPI), `d0cbb13` (CI fails on generated-type drift).
- New `scripts/gen-api-types.mjs` generates `src/api/generated/schema.d.ts` + `enums.json` from the live OpenAPI spec (openapi-typescript), replacing 47 hand-written type aliases and fixing real case-mismatch bugs (`UserRole`/`NotificationSeverity`/`CalendarEventType` were uppercase in hand-written types vs. lowercase from the backend, breaking role checks, notification-bell classes, and calendar-event creation). Wired into `make types-check` and a CI `lint-frontend` step that fails on drift.
- Left open: `OrderLegacyFields` kept on `OrderType` rather than migrating every legacy field; `AuthContext.hasRole`/`lib/roles.ts` still normalise to uppercase; input (Create/Update) types for materials, metal inventory, calendar events, estimator and time-stats remain hand-written; `GET /customers/top` is still `response_model=List[dict]` (untyped).
- Evidence: `yarn tsc --noEmit` 0; `yarn vitest run` 0 (80 files, 660 tests); `vite build` 0; hex-ratchet 0 (2106 ≤ baseline 2113); `make types-check` clean tree 0, with an induced docstring drift caught and reverted.

### W3-07 / W3-08 — Backend contract: DomainError, Page[T], OpenAPI check — **partial**
- Findings: ARCH-07, ARCH-08, FE-06 (partial), SEC-16. Commits: `5183407` (DomainError hierarchy + one handler), `7e48494` (`Page[T]` envelope + server-side filter/search), `8dff361` (OpenAPI documents every paged list endpoint).
- Added a `DomainError` hierarchy (NotFoundError/ConflictError/ForbiddenError/DomainValidationError/UpstreamError) with a single handler emitting `{detail, code, extra}` (still subclasses `HTTPException` for one release for backward compat); added a generic `Page[T]` envelope with filtered list builders (status/customer/date filters + `q` search) for orders, repairs, quotes, materials, time-tracking, notifications — triggered by presence of `offset` (legacy shape kept otherwise, capped at `limit<=500`, closing SEC-16); `test_openapi_contract.py` asserts every paged path documents a `Page_*` schema.
- Left open: the frontend is not migrated to send `offset`/read `code` yet — the legacy path stays live; customer-name search decrypts all active customers per `q` (O(N), needs per-field blind indexes); customers/invoices lists still not paginated; activities/comments/users/calendar routers not paged at all; 63 router except-blocks not yet migrated to `DomainError`; `list_queries.py` duplicates OrderService/RepairService filter logic (tracked as W3-09).
- Evidence: targeted domain-error/pagination suites 17 + 50 passed; mypy 0; full suite 3732 passed, 6 skipped, 1 xfailed (1 unrelated failure owned by another agent); `test_openapi_contract.py` + `test_pagination_other_lists.py` 5 passed.

### W3-06 — Frontend ESLint 9 rollout — **partial**
- Findings: OPS-13, FE-15. Two commits (`445b5bd` flat-config setup, `1f0c253` a11y/mechanical fixes) plus a remainder pass (`ee852ed`).
- Rolled out ESLint 9 flat config (typescript-eslint + hand-tuned react-hooks + jsx-a11y's 6 named rules, `--max-warnings 198` gate). Fixed 124 of 142 initial errors: `label-has-associated-control` via id/htmlFor or aria-labelledby, click/static-interaction pairs via real `<button>`s or documented modal-backdrop `role="presentation"` exemptions, `no-autofocus` removals (a deliberate UX change — fields no longer autofocus), unescaped-entities. The remainder pass closed 4 of the last 5 excluded files (`CustomerDetailPage.tsx`, `StatusChangeDialog.tsx`, `IntakeChecklist.tsx`, `RepairDetailPage.tsx`).
- Left open: **`OrderFormModal.tsx` — 5 ESLint errors remain** (owned by another in-flight agent): 2× `click-events-have-key-events`/`no-static-element-interactions`, 2× `no-unescaped-entities`. This is the sole remaining blocker for `yarn lint`/CI `lint-frontend` to go fully green. `ActiveTimerWidget`'s div→button conversion inherits the global `button{}` CSS reset — a visual delta not checked in a browser.
- Evidence: first run 142 errors/198 warnings; after in-scope fixes 22 (excluded files only); after the remainder pass, 5 errors (OrderFormModal.tsx only)/197 warnings; `tsc --noEmit` 0; `vitest run` 0 (110 files/898 tests); `vite build` 0; hex-ratchet 2086 (baseline 2087).

### W4-01 — Design tokens, AA contrast, focus, status coverage — **partial**
- Findings: DES-01 (partial), DES-02, DES-03, DES-08 (partial), DES-09 (partial), DES-10, DES-19 (partial), DES-27, DES-29 (partial). Commits: `54f9c3b` (semantic tokens, AA primary, focus ring, full status coverage), `316935f`/`782d2c4` (hex-ratchet baseline).
- Added semantic tokens (surface/text/border/primary/accent/feedback/tone/focus/z-index/spacing) to `brand-tokens.css`, repointed 37 of 42 undefined custom properties to them, verified 0 AA contrast failures on ~30 introduced pairs, added a global `:focus-visible` ring overriding 35 pre-existing `outline:none` rules across 21 stylesheets, gave all 10 order + 9 repair statuses full tone coverage via new `status-tones.css`, fixed offline-banner/drawer z-index layering, and patched `useTheme.ts` to reject non-AA admin theme colors at runtime.
- Left open: backend theme default (`#d97706`) was not moved in this item — **closed later by W7 hygiene** (`7c30827`); `@axe-core/playwright` not installed so the axe smoke test is skipped; ~20 umlaut strings (DES-17) untouched here — **partially closed by the live-verification passes** (`e451ef5`, `36509cd`, `862189f`); hardcoded `#d97706`/`#f59e0b` remain in `order-detail.css`/`dashboard.css`; legacy z-index literals not remapped; focus ring shipped at 2px vs. the playbook's 3px, unreconciled.
- Evidence: `useTheme.test.ts` RED (3 failed) → GREEN (5 passed); `tsc --noEmit` 0; `vitest run` 0 (70 files/600 tests); `vite build` 0; hex-ratchet 0 (2113, baseline lowered from 2137); contrast script 0 introduced-pair failures.

### W4-02/W4-03 — src/ui component primitives (numbering caveat, see MASTER-FIX-PLAN §2)
- The fix agent working under the `W4-02` label built the `src/ui` primitive library that the plan's table actually assigns to W4-03 (Button/IconButton, Card, Modal/Sheet/Dialog + `useDirtyGuard`, PromptDialog, Field, DataTable, ListCard, EmptyState, PageState, PageHeader, Tabs/TabBar, DeadlineChip, error-message helpers), each with dedicated a11y behavior (focus trap, aria-*, keyboard nav) and tests, plus a dev-only `/dev/ui` demo page (verified absent from prod `dist`). 8 commits, `163a781`..`a8113e8`.
- The plan's actual W4-02 ask (a single status map, DES-03/DES-04) was covered separately: DES-03 by the pre-existing `StatusBadge`/status map (`dc83d95`) plus W4-01's status-tone sweep; DES-04 (deadline urgency in the Orders list) is not confirmed — `DeadlineChip` exists as a primitive with no confirmed adoption.
- Left open: `StatusBadge` not yet wired into `DataTable`; icon set is an inline stand-in (no icon-library dependency added); `ConfirmDialog`/`useConfirm` not migrated onto the new Modal; Modal uses portal+focus-trap rather than native `<dialog>` (happy-dom test-environment limitation); none of these primitives are adopted by existing pages yet (that's W4-05 through W4-07).
- Evidence: RED (11 files failed) → GREEN (90 passed); `tsc --noEmit` 0; full suite `vitest run` 784 passed (94 files, up from 688 baseline); `vite build` 0; hex-ratchet 2092 (baseline 2113). Manual check at 1280/390px: no horizontal overflow, modal full-screen on mobile, table→cards.

### W5-01 — Dependency backlog + frontend coverage tool — **partial**
- Findings: OPS-06 (partial — see W7 hygiene below), OPS-02. Commits: `94a272f` (chore(deps): clear critical/high Dependabot alerts), `40fe1a4` (chore(test): add frontend coverage tool).
- Bumped backend (cryptography, anyio, pytest/pytest-asyncio, pip, click) and frontend (react-router-dom, vitest, lodash→4.18.1 — not the Dependabot-listed 4.18.0, which broke `vite build`'s service-worker generation via workbox-build's `lodash/template` use — plus resolutions for fast-uri/postcss/browserslist/nanoid/baseline-browser-mapping) to clear Dependabot alerts; added `@vitest/coverage-v8` with a baseline (Statements 54.35%, Branches 46.33%, Functions 48.57%, Lines 56.13%).
- Left open: `ecdsa` (high, no upstream fix) required finishing the python-jose→pyjwt migration, deferred here — **closed by W7 hygiene** (`250e5a9`); `docs/architecture/likec4/package-lock.json` still vulnerable (separate Node project, out of scope); coverage has no enforced threshold yet.
- Evidence: backend full suite 3391 passed/6 skipped/1 xfailed before and after; frontend tsc 0, vitest 69 files/591 tests both baseline and final; vite build (incl. PWA/SW) green after the lodash pin.

### W5 GDPR ops — backups, retention, export, legal docs
- Findings: GDPR-06, GDPR-07 (done), GDPR-08, GDPR-16 (partial), GDPR-05 (done), GDPR-13 (verified, pre-existing), GDPR-14/GDPR-15 (documented, not closed), GDPR-17 (done), D-19.
- Item 1 — `3f0e7f7`: encrypted backups (age/gpg), fixed two pre-existing retention-loop bugs (oldest/newest inversion; a `set -e`-fatal counter bug), a restore-then-replay erasure ledger and CLI.
- Item 2 — `15bd0c0`: `RETENTION_EXECUTE` (default False/dry-run), `--dry-run`/`--execute` CLI flags, new `RETENTION_SCHEDULE.md`.
- Item 3 — `7b1d756`: strict, full GDPR export models/service, export handler, D-13 sentinel test.
- Item 4 — `537594a`: processors list documented; employee-analytics conflict (GDPR-14) documented, not resolved.
- Item 5 — `863b38c`: VVT v1.2 (controller=Anne, processor=Max with an AVV), TOMS.md, DATENSCHUTZHINWEISE-KUNDEN.md, AVV-CHECKLIST.md, BREACH-RUNBOOK.md.
- Left open: no live restore drill; erasure-ledger gap for post-backup erasures; `restore.sh` lacks `ON_ERROR_STOP`; the systemd cleanup service still defaults to the dev compose file; `backup-sync.sh` still URL-only auth, `./uploads` not backed up; sweep coverage not extended past its original tables; `GDPR_EXPORT` permission not added (export still gated on `CUSTOMER_DELETE`); GDPR-14/15 need Anne's/legal decisions; D-13 pending lawyer confirmation; retention periods and DPO/AVV structure pending Steuerberater/Datenschutzberater sign-off.
- Evidence: baseline `-k` gdpr-ish 259 passed; new erasure-replay 12 passed; backup/restore script tests 15 passed; retention-execute 10 passed; final `-k` gdpr-ish 299 passed; final full suite 3722 passed/6 skipped/1 xfailed.

### Wave 5 Ops/CI — nightly E2E, audits, ruff, caching, timers
- Findings: OPS-07, OPS-01, OPS-11, OPS-12, OPS-04, OPS-05. Commits: `533e62d` (Poetry/Yarn caching + local Make targets), `a3642f1` (advisory audits + ruff in lint), `23fd91c` (nightly e2e workflow), `33cce19` (systemd timer installer).
- Added `install-timers.sh`, a nightly e2e workflow for 4 previously-unwired specs, advisory `pip-audit`/`yarn npm audit` (continue-on-error), ruff in CI lint (`--exit-zero`, 994-error baseline), and Poetry/Yarn caching.
- Left open: e2e seed-credential drift across 3 seed scripts — **closed by W7 hygiene** (`4b2d1ec`); no live CI run yet for the nightly workflow; ruff's baseline stays non-blocking by design.
- Evidence: `pytest tests/scripts/` 43 passed; `bash -n` clean; YAML/actionlint clean except 4 pre-existing shellcheck nits; `ruff check src/` → 994 errors (recorded baseline).

### W5/W7 docs and tooling remainder
- Findings closed: OPS-08, ARCH-16 (partial), SEC-F8, SEC-F10, OPS-14, DES-08 (hex-ratchet wiring, partial). Commits: `2d748f6` (OPS-08/SEC-F8/SEC-F10), `03bf8ac` (ARCH-16 ADR), `c3df1a4` (OPS-14), `6f01897` (CHANGELOG.md), `3664961` (archive the 2026-04-23 review), `b1f3b6a` (DES-08 hex-ratchet wired into pre-commit/CI), `fd21d21` (dead doc references), `3792f45` (README fixes).
- Archived stale `DEPLOYMENT.md`/`ARCHITECTURE_REVIEW.md` with superseded banners, added rollback/log-rotation docs and a single-box deployment ADR, a read-only stale-worktree reporter (never auto-deletes), wired the hex-ratchet script into pre-commit/CI, added `CHANGELOG.md`, fixed ~15 broken README links and 2 false "(geplant)" claims.
- Left open (explicitly out of scope): C4/likec4 model update (the tool itself is broken, pre-existing); other ADRs (jose, estimator, no-portal); OPS-03's mypy widen-without-shrink gate needs real design work; OPS-10's test relocation; W5-04 (realtime contract test), W5-06 (column encryption), W5-12 (migrate-service/Sentry wiring); W7-01/02/03/05 (workshop model, aftercare, offline queue, audit decorator); W7-04 (feature flags, unused `boto3`); W7-06's frontend hygiene (e.g. the committed `.yarn/install-state.gz`).
- Evidence: all `bash -n`/YAML checks exit 0; `tests/scripts/` 58 passed; hex-ratchet 2088 literals vs. baseline 2113.

### W6-02 / W6-06 — CustomerMessageService, the single outbound customer channel
- Findings: GDPR checklist E1/E2/E4-E6/E15/E16 (own paths), GDPR-11 (pre-existing consent store). Commits: `777137d` (backend service/policy table), `815196d` (Kundeninfo composer preview UI), `2ab80c0` (email opt-out switch).
- Built one policy-driven outbound path (`MESSAGE_POLICIES`), enforcing PHOTO_USE consent for photo updates, a price guard, an Art. 21 opt-out → PDF_MANUAL fallback, EXIF-stripped 1200px photo downscaling, and a `customer_message_sent` audit row for every send.
- Left open (at this point): `quote_delivery.py` still bypassed the service — **closed by W6b**, see below; retry of a failed `quote_sent` via the generic `/updates/{id}/send` endpoint mis-derives kind as "question", still open; E7's recipient-confirmation step not built; PHOTO_USE consent purpose is overloaded (portfolio/social vs. email-photos, a tension flagged for the Datenschutzberater); no privacy line on the customer-update PDF.
- Evidence: new unit suite 53 passed; wider subset 61/61 after fixing 8 regressions; full backend 3878 passed/12 skipped/1 xfailed after merge; frontend vitest 103 files/849 tests passed; hex-ratchet 2087/2087.

### ARCH-04 / ARCH-05 / ARCH-12 — Transactional outbox and worker (W6-01)
- Findings: ARCH-04, ARCH-05, ARCH-12. Commits: `c4e4090` (`outbox_messages` table + settings), `d41625b` (enqueue customer/quote mails), `f55fbaf` (worker entrypoint), `1409dc8` (worker compose service), `d099e0e` (admin endpoints + UI panel), `30e63c0` (ADR + runbook).
- New `OutboxMessage` table + `OutboxService` (lease/backoff/dead-letter via `FOR UPDATE SKIP LOCKED`), a `worker.py` process, an admin retry endpoint/UI, and mode selection (`outbox_mode` = inline in DEBUG, worker otherwise; dev compose defaults to inline, prod compose sets `OUTBOX_MODE=worker` on backend + worker).
- Left open: no invoice-email path through it yet; a queued message shows as delivered until the worker actually sends (no distinct "queued" UI label; the outbox panel uses `DataTable`, not `StatusBadge`); delivery is at-least-once (possible resend after a lease expires mid-crash); no retention job for sent rows yet.
- Evidence: targeted `-k` outbox|worker 405 passed/4 skipped; full backend after merge 4110 passed/12 skipped/1 xfailed (baseline 4009); frontend tsc 0; vitest 111 files/901 tests passed.

### W6b — Quote e-mail routing to CustomerMessageService + LV-17 health threshold
- Findings: E6, E16 (quote routing, done); LV-17 (done); E7, E8, E17 (investigated, not closed). Commits: `2669451` (quote routing), `bb6450e` (disk-warning no longer degrades health).
- Routed `quote_service.send_quote`/`quote_delivery.py` through `CustomerMessageService` (audit row + Art. 21 opt-out honored for quotes, previously ignored); made `HEALTH_DISK_CRITICAL_PERCENT` configurable (default 95%) and stopped disk's routine 80% warning alone from degrading overall `/health` status — only "down" components or disk "critical" do now.
- Left open: E7 (recipient confirmation before the first photo/PDF mail) needs frontend UI; E8 (TLS on every SMTP port, tracked as W5-09; AVV is a legal contract, not code); E17 (Art. 30 record + DSFA screening needs a VVT doc edit).
- Evidence: `test_quote_send.py` 10 passed; `-k` quote/email/customer_message/health 295 passed/2 skipped; full suite after final merge 4071 passed, 12 skipped, 1 xfailed, exit 0.

### W6c — Customer Status Report PDF (DOM section D, Option 2)
- Commit: `c4c1ff5` (feat(comms): customer status report PDF for orders and repairs).
- New live-generated (never stored) status-report PDF for orders/repairs, gated a second time by active PHOTO_USE consent at generation time; composer gets a "Statusbericht anhängen" option; standalone download buttons added to Kundeninfo/repair panels.
- Left open: `attach_status_report` is a request-time flag only (no DB column/migration); repair photos have no consent/selection mechanism, so the latest 6 are shown unconditionally; `next_steps` is a plain query param, not wired into the composer as free text; repair timeline is thin (no `RepairEvent` history table).
- Evidence: full backend suite final 4086 passed, 12 skipped, 1 xfailed, 0 failed; frontend vitest 904 passed/110 files; hex-ratchet 2086 (baseline 2087).

### W7 backend hygiene — python-jose → PyJWT, seed credentials, theme AA contrast
- Findings: OPS-06 (closes the `ecdsa` transitive vuln); seed-credential consistency; theme default-color/WCAG AA. Commits: `250e5a9` (jose→PyJWT), `4b2d1ec` (unify seed credentials), `7c30827` (AA-compliant theme defaults + server-side contrast gate).
- Removed `python-jose`/`ecdsa` entirely in favor of PyJWT repo-wide; unified 4 disagreeing credential sources (scripts + 3 hardcoded Playwright specs) onto one canonical `demo-inhaber@werkstatt.de`/`demo2026!` set; fixed backend theme defaults (`#d97706`→`#b45309`) and added a server-side contrast gate on `PUT /theme` mirroring the frontend's client-side guard.
- Left open: `docs/DEPLOYMENT.md`/`DEPLOYMENT_LOCAL.md` still show stale sample creds; LV-05/LV-16/LV-18 (legacy order status "new", orphaned order-photo rows, `customer_notified_at` without a matching SENT update) were **not** implemented here — a mid-task message purporting to be "the coordinator" asked this agent to also fix them; the agent correctly flagged it as a likely prompt injection, declined the scope creep, and those three items were separately closed by the live-verification passes below (`75b0f3a`, `f4c68e1`, `09c5307`).
- Evidence: full suite after all 3 commits 3702 passed, 6 skipped, 1 xfailed, exit 0; `pip-audit` reports no known vulnerabilities.

### W7 hygiene — photo-upload realtime publish + CustomerDetailPage thumbnail fix
- Follow-ups from W2-01, no formal register ID. Commits not individually captured in the report; `7287033` (publish reduced order event after upload) and `3d43ea2` (thumbnails from `first_photo_id`, no per-order photo requests) match this work in `git log`.
- Order/repair photo uploads now publish a reduced `order_updates`/`repair_updates` event after commit (ids/action/timestamp only); `CustomerDetailPage`'s Auftragshistorie tab fixed from N+1 unauthenticated-URL fetches to one authenticated `/photos/{id}/thumbnail` call.
- Left open: `repair_updates` is published but still not subscribed/routed by `ws_manager.py` (a pre-existing gap, confirmed still open); no "publish skipped on repair-upload failure" test (asymmetric with the order-photo coverage).
- Evidence: `-k` photo/realtime/publish 127 passed; full backend suite 3686 passed, 6 skipped, 1 xfailed; frontend vitest 79 files/650 tests passed.

### Live verification pass 1
- `.orchestrated-fable/ux-erp-audit-2026-09/live/LIVE-VERIFICATION.md`, HEAD `48cd9fe`. Real stack: Postgres 127.0.0.1:5434, a stand-in Redis container on 127.0.0.1:6391, backend on :8010, frontend vite on :3000. Verified: infra bring-up, an Alembic migration round-trip on an **empty** PG15 schema, the PG integration suite, then a Playwright screenshot loop at 1280×800 and 390×844 for ADMIN and VIEWER across every staff page plus focus/touch-target/umlaut/money checks.
- **Verdict: 21 findings — 2 HIGH, 5 MEDIUM, 14 LOW, 0 CRITICAL.** All 21 were fixed same-session except two left partial: LV-12 (touch targets — header "System" button 77×27, invoices status select 98×21, invoices PDF button 46×32 still under 44px) and LV-19 (orders table at 1280 — AKTIONEN column still clipped, FAB still overlaps a row). Fix commits: `4e18bf0` (header overflow, search icon, offline banner, touch targets), `e451ef5` (quote customer select, umlauts), `5fd3394`/`47b54ef` (PG user-FK test fixture), `dc83d95` (status badges), `36509cd` (money format, umlauts, orders table), `9115489` (VIEWER order-create/price hiding), `f4c68e1` (demo photo thumbnails), `972da8f` (Redis port), `09c5307` (repair notified-timestamp seed fix), `75b0f3a` (legacy status "new" seed fix), `dc988ab` (login console noise, later regressed and re-fixed — see pass 2), `862189f` (round-2 umlaut sweep), `910aacc` (round-2 touch targets), `5d4cd3e` (round-2 orders table).
- Notable: the order-advance workflow already worked correctly and recorded a real `order_events` row — LV-04 was purely that the Historie tab didn't render it. `/health` "degraded" was solely an 80.1% disk-usage warning (LV-17), not a real DB/Redis problem — the threshold was later made configurable (`bb6450e`). A new `test_pg_concurrency.py` (two real DB sessions) found **no actual race** in 5 repeated runs for the timer and quote-conversion PG-only concerns flagged since W1-17/W1-07.

### Live verification pass 2
- `.orchestrated-fable/ux-erp-audit-2026-09/live2/LIVE-VERIFICATION-2.md`, HEAD `cb0cf0b`, same environment reused. Re-verified all 21 pass-1 findings (15 fixed outright, 2 with residuals, 1 regressed) and covered new ground: a migration round-trip re-run **with real seed data present** (closing pass 1's empty-schema caveat), a full fresh reseed with data-integrity checks, and deep click-through flows on order 13, customer 1, repair intake and repair 4, quotes customer search, `/admin/system`, `/dev/ui`, and VIEWER role checks.
- **8 new findings (LV2-01..08), 0 CRITICAL, 0 HIGH, 2 MEDIUM, 6 LOW.** Fixed: LV2-01 (`6f1d294`, same PG user-FK pattern in the hallmark tests), LV2-02 (`9c54eb9`, `HealthDot` now proxied), LV2-03 (`fd1eed0`, customers table scroll instead of clip), LV2-04 (`2b33842`, VIEWER's dead-end "Angebot erstellen" button gated), LV2-06 partial (`6f1b165`, quotes Status filter styled + touch target; customer-name-not-id resolution still open), LV2-07 (`1e6a333`, Escape closes the Neues-Angebot dialog, body padding added). LV2-05 (order-detail tab strip at 390px has no gap/scroll cue) explicitly deferred — no plausible static-CSS cause found and no way to visually verify a fix in this environment.
- **LV-21 regressed**: the pass-1 fix reduced console noise, but `WebSocketProvider`/`TimeTrackingProvider`/`ScannerProvider`/`OrderProvider` were still mounted above `ProtectedRoute`, firing a WS connection (403) plus two 401 fetches *before* login — worse than the original probe noise. Fixed by moving those providers inside `ProtectedRoute` (`5839e68`), which also closes LV2-08.
- Evidence/gotchas: demo credentials `demo-goldschmied`/`demo-inhaber` ("Petra", admin)/`demo-buero` ("Lisa", viewer), password `demo2026!`, cookie-based auth. A concurrent `git merge` mid-`vitest run` produced 3 spurious failures in `customer-updates.test.ts`, confirmed a false positive on isolated re-run (918/918 clean).

### W2X — post-W2 open-items batch: alloy vocabulary, Altgold GDPR export, timer pause/resume, VIEWER repairs gate, gemstone PDFs
- Findings: W2-09 (partial), W2-16 (GDPR export), D-15 (timer pause/resume), plus items 2/4/6/7 of the post-W2 open-items list. Commits: `aac9bcc` (hallmark vocabulary + order-intake picker recognize Silver 935/Palladium 950/500), `86e6e78` (GDPR Art.15 export now includes `id_document_type/number/issuing_authority/id_checked_at` + a new retention-schedule row), `5242fc0` (server-side timer pause/resume), `aef4ffb` (hide "Neue Reparatur" from VIEWER), `fdbdcb1` (pass order gemstones into quote and invoice PDF renderers), `ef476b9` (`/status` docstring describes `hallmark_required` + nicht-punziert path; orphaned `frontend/src/api/hallmarks.ts` removed), `e3fecba` (resolve `OrderFormModal.tsx`'s last 5 ESLint errors), `2870b90` (carry order gemstones through `InvoiceSubject` after the merge).
- Closes the last ESLint blocker flagged in Wave 3 — `yarn lint`/CI `lint-frontend` is 0 errors project-wide after `e3fecba` — plus several small Wave 2 gaps left open at the time (Altgold GDPR export, VIEWER repairs access, PDF gemstones, dead OrderHallmark client).
- Left open: `AlloyType` enum extension itself was SKIPPED (needs a migration, out of scope — still blocks `ScrapGoldItem.alloy` persistence for the newly-recognized marks); item 6 (workshop-editable Pflegehinweise/care text) also SKIPPED, no free-text column exists; `scrap_gold_service.py`'s `_price_for_item`/`_recalculate_totals` still indexes the raw 3-metal spot-price dict and will `KeyError` (not the typed `MetalPriceError`) if `AlloyType` ever gains palladium; TimerWidget's "frozen ticker while paused" UI polish not built and it still shows emoji icons (⏸️▶️⏹️) against the playbook's ban; the full ~4000-test backend suite was **not** re-run after this final merge (targeted slice only) — recommended before merging to `main`.
- Evidence: final targeted re-run post-merge `pytest -k "invoice or quote or gemstone"` 1483 passed/2 skipped, exit 0; `tsc` 0; vitest (touched files only) 71 passed, exit 0.

### W3 — TanStack Query foundation (Orders, Customers, Dashboard)
- Commits: `9844726` (TanStack Query foundation with realtime invalidation), `18e5a0e` (OrdersPage on paged queries), `56c0eaa` (DashboardPage one query per mount), `e437c2a`, `8f2be0f` (Customers reference page).
- Establishes the query/cache pattern (one query per mount, realtime invalidation wired to the WS event bus) that the later W4-03 page migrations followed.
- Evidence: `yarn vitest run --reporter=dot` 118 files/949 tests, exit 0; `yarn lint` 183 problems (5 pre-existing OrderFormModal errors, since resolved above), exit 1 at the time; `node scripts/hex-ratchet.mjs` 2086 (baseline 2087), exit 0.

### W3-03 / W3 sort+paging — restore the Orders sort control; paged customers
- Finding: W3-03 (sort control regressed by the TanStack pass). Commits: `ed8e67f` (backend: `sort` parameter added across 6 paged list endpoints, plus a newly paged `/customers/`), `3f9fea9` (frontend: sort control reconnected to the API).
- Applies the existing legacy-list-fallback-on-`offset` contract (see Decisions) uniformly to orders/repairs/quotes/materials/time-entries/notifications/customers.
- Evidence: `test_pagination_sort.py` 15 passed; full backend suite 4186 passed/12 skipped/1 xfailed, exit 0 (525.57s); vitest 118 files/949 passed, exit 0; `tsc` 0.

### W3-11 / BE-14 / BE-15 — NUMERIC money and tz-aware datetimes, end to end
- Findings: BE-14, BE-15. Commits: `9448e0b` (money columns as `Numeric`/`Decimal` end to end), `82d285e` (timezone-aware datetimes end to end).
- Uncovered a pre-existing PostgreSQL-only outbox-migration idempotency bug (the h9 round-trip test from an empty DB) — fixed separately by `ff4dccc`.
- Left open: a naive-datetime grace period is still accepted end-to-end (~200 `datetime.utcnow()` calls remain in tests, to be removed next release); BE-14's "sum of *rounded* line totals" was not applied — needs a product/Steuerberater decision; `cli/gdpr_replay_erasures.parse_since` still returns naive UTC.
- Evidence: pytest FINAL 4171 passed/12 skipped/1 xfailed, exit 0; mypy 12 pre-existing errors (same baseline), exit 1 (expected); PG integration suite 897 passed/1 failed (the h9 roundtrip bug, fixed next). After `ff4dccc`: `pytest -k "migration or outbox"` 137 passed/1 skipped, exit 0; PG h9-roundtrip 1 passed, exit 0; full backend suite 4171 passed/12 skipped/1 xfailed, exit 0; vitest 957 passed, exit 0; `tsc` 0.

### ARCH-09 — split `db/models.py` into a domain package
- Commits: `0b30d88` (turn `db/models.py` into a package; move base/coercion/time-tracking), `925e1e6` (order models), `eca1b06` (users/customers), `4ccd863` (invoice/quote), `eeab0bd` (materials/metals/scrap gold), `766e594` (repair/consultation), `76c46cf` (comms/system, finishes the split), `40589a6` (import-linter contracts), `e372d9d` (docs note on the package layout and layering contracts).
- Left open: convert models to `Mapped[]` module-by-module; remove the `core.permissions → api.deps` edge then widen import-linter contract 2; add `lint-imports` to CI; fix pre-existing PG drift (`scan_logs` partitions/types/index); `scripts/seed_data.py` imports a nonexistent `DataRetentionPolicy`.
- Evidence: pytest FINAL 4186 passed/12 skipped/1 xfailed, exit 0; mypy 12 errors, same baseline (diffed identical), exit 1 (expected); `lint-imports` 2 kept/0 broken; `alembic check` non-empty but an identical old-vs-new-metadata diff (pre-existing PG drift only).

### W4-03 — page migration playbook, remaining waves (order detail through nav/admin/order form)
- **Order detail** — done, `df98c05`. Cut CSS 2069→614 lines, hex 182→0.
- **Quotes + invoices** — done, `8fd80c6`, `e4a3ee1` (+ `ac4cd79` post-merge query-key fix). QuotesPage 1389→135 lines, InvoicesPage 1151→185.
- **Group E** (consultations, materials, metal inventory, scrap gold) — done, `2844331`, `45acdc0`, `3afcbfe`, `836a975`. In-scope hex 418→1.
- **Group F** (calendar, users, auth, portal, header overlays) — done, `9f824a7`, `d2354a9`, `9c8d8a3`, `b837990`, `286a813`. Hex 207→0 in-scope.
- **Repairs** — done, `7759bcd`. useEffect fetches 4→0, hex 67→19 (shared PhotoCompare lightbox styles remain).
- **Bench UI** (scanner + time tracking, Werkbank-Modus) — done, `78f0176`.
- **Nav / admin panels / order form** — done, `8c89281`, `4aa1c58`, `2ec97d6` (W3-06, react-hook-form + zod), `71674ab`, `a5a6546` (tz-aware timestamps in date helpers), plus the Werkstatt-Board nav entry `b8795e2`.
- Screenshot loop (playbook 7d, 1280/390) NOT run in any worktree (no live stack available); the hex-baseline file was deliberately not force-updated by individual agents to avoid cross-branch conflicts — the orchestrator locked it in afterward (`c9523b9`, then `69d966c` "lock in hex ratchet baseline after page migrations").
- Left open (by group): stones on a new order still can't be added until it's saved, stone-deletion UX needs a product call, the Scan FAB isn't in the phone tab-bar centre yet, Altgold has no standalone route, `orders.css` still has dead rules, `adminKeys` sits outside the shared `queryKeys.ts`, `SystemStatusPanel` health labels aren't in `status.ts`, `ScanAdoptionDashboard.tsx` still has ~20 colour literals, the tab bar's "Mehr" slot needs a button item (fix-w4-page-admin-nav-form.md); CSS still leaks into out-of-scope pages (`.detail-item`, `.btn-pdf-download`, `.btn-retry`), `useMetalTypes`'s module cache wasn't migrated to a query, materials sort/low-stock filters stayed page-local, the scrap-gold manual gold-price input is still read-only, `StyleNoGoStep` keeps a plain `<label>` (fix-w4-page-group-e.md); portal's `status_label` still triggers a StatusBadge unknown-key console warning and `RegisterPage` exists with no route (fix-w4-page-group-f.md); repair Verlauf still synthesizes its own timeline instead of switching to the new `/jobs/{job_id}/timeline` now that `job_id` exists, `repairKeys` sits outside `queryKeys.ts`, status-step gating still uses `canCreateRepairs` pending a real `canEditRepairs`, `IntakeChecklist` is only partly on primitives, and intake's dirty-dialog prompts are inconsistent (Abbrechen vs. Escape/close) (fix-w4-page-repairs.md); bench mode has no footer/nav-hiding or user-menu toggle, `ScanOverlay` isn't on the `src/ui` Sheet, the time-entry list lost its free-text/activity/duration-sort filters (no server param), `TimeEntryFormModal` still parses/submits naive UTC, `status.ts` has no "Läuft" `StatusKind`, and `orderEntriesQuery` has no consumer yet (fix-w4-page-bench.md); quotes/invoices still have no realtime channel and `/invoices/` still has no Page envelope (legacy skip/limit) — same root cause as the quotes-list "Kunde #id" gap tracked in Open follow-ups.
- Evidence: order detail — vitest 119 files/954 passed, exit 0; tsc 0; lint 5 errors (OrderFormModal only, since resolved), exit 1 at the time; build 0; hex-ratchet 1881, exit 0. Quotes+invoices — vitest 983 passed (from 949), exit 0; tsc 0; hex-ratchet 1500, exit 0. Group E — vitest 125 files/984 passed; tsc 0; hex-ratchet 1083, exit 0. Group F — vitest 123 files/971 passed; tsc 0; hex-ratchet 1674, exit 0. Repairs — vitest 137 files/1064 passed; tsc 0; lint 0 errors/122 warnings; hex-ratchet 1034 (baseline 1082). Bench — vitest 140 files/1077 passed; tsc 0; lint 0 errors/84 warnings; build 0; hex-ratchet 753 (baseline 1082). Nav/admin/order-form — vitest 1076 tests (from 1021 baseline); tsc 0 throughout; lint 0 errors/119 warnings final; hex-ratchet 893 (own baseline 941).

### ARCH-02 — Jobs spine (numbering, invoicing, timeline, kanban board)
- Commits: `82fd186` (jobs spine table, backfill migration, service-side sync — part 1), `f745267` (attach invoices/updates/media/events by job; repair invoicing — part 2), `e407eb6` (`GET /jobs` list, job detail and timeline — part 3), `b601211` (ADR: jobs spine migration plan, sync rules, retirement path — part 4), `4cc90ef` (backfill jobs in seed and at startup), `3353092` (Rechnung erstellen for repairs), `a44d942` (Werkstatt board — a kanban view over jobs, W6).
- The `jobs` table now owns human-facing numbering for both orders and repairs (see Decisions) and becomes the attachment point for invoices, updates, media and events; a real per-job timeline endpoint now exists.
- Left open: `job_id` columns stay nullable (make NOT NULL once `count_missing()`=0 in prod); quote-delivery records still get no `job_id`; the Werkstatt board only supports input-free repair transitions (diagnose/approve/complete still need the detail page), has no drag-and-drop, and issues 8 requests per load (one per column); the startup job-backfill logs and continues on failure rather than stopping startup.
- Evidence: backend baseline 4239 passed; FINAL 4366 passed/12 skipped/1 xfailed, exit 0; mypy Success (41 modules); lint-imports 2 kept/0 broken; PG integration suite 943 passed/2 skipped; vitest 131 files/1007 passed, exit 0; tsc 0. Follow-ups pass: pytest FINAL 4371 passed/12 skipped/1 xfailed (baseline 4366), exit 0; vitest 134 files/1023 passed, exit 0; tsc 0; lint 5 errors (OrderFormModal, unchanged at the time); hex-ratchet 1082 (baseline 1082, unchanged).

### ARCH phase 4 — Media (media_assets, MediaStore, MediaService, customer_visible)
- Commits: `503c81f` (`media_assets` table, `MediaStore`, `MediaService`), `4e85439` (`customer_visible` flag used by messages and the status report).
- Follow-up: `restore.sh` didn't restore the media archive — fixed (manifest + restore logic added; no sha given in the report, see fix-w6-restore-media.md directly).
- Left open: no orphan sweep (soft-delete doesn't cascade to `media_assets`, polymorphic/no FK); `customer_service`'s erasure scrub only clears legacy `notes` (caption clearing is via the separate erasure pass); PDF/email/scanner/thumbnail readers still read the legacy photo tables (dual-write not retired); media restore is not erasure-replay-aware (a restored archive can resurrect a file for an already-erased customer) — a documented, not-fixed gap; `compute_sha256()` is duplicated in `backup.sh`/`restore.sh` instead of the shared lib.
- Evidence: backend suite commit-1 4232 passed; FINAL 4239 passed/12 skipped/1 xfailed, exit 0; vitest 994 passed (after an MSW handler fix), exit 0; `tests/scripts` 71 passed. Restore: `pytest tests/scripts/` FINAL 82 passed, exit 0; manual gpg round-trip + tamper-detection smoke tests all exit 0/expected non-zero on corruption.

### Repair/job realtime fan-out
- Commit: `7fa6f41` — forwards `repair_updates` and a new `job_updates` channel to staff sockets, closing gaps both fix-w4-page-repairs.md and fix-w6-jobs-followups.md had flagged open (repair_updates was published but never subscribed/routed by `ws_manager.py`).
- Left open: `job_updates` fires inside the caller's open transaction, not strictly post-commit (callers out of scope) — a documented compromise.
- Evidence: targeted pytest (`ws or websocket or realtime or pubsub or repair or job`) 354 passed/4067 deselected, exit 0; full suite launched in background, not confirmed complete before the report was written (context budget); vitest targeted 53+13 passed, exit 0; tsc 0.

### W7-06 hygiene backlog — 8/8 explicit candidates
- Findings/items closed: W1-04 follow-up, W3-04 (defense-in-depth), DOM-20 remainder, FE-06 (order pickers), portal hardcoded contact, StatusBadge user kind, dead CSS, stale docs. Commits: `f3d0b1f` (App.tsx route guards relaxed for VIEWER — Materials/MetalInventory/Customers/Repairs, each destination page already gates financial/design sections), `f4c2d5c` (SollIstTab internal FINANCIAL_VIEW guard, defense-in-depth), `e7f6913` (per-metal fine-gold breakdown added to the scrap-gold read response — no schema/migration change, so the fuller DOM-20 ask still needs one), `df4cfb3` (ConsumeMetalModal + CreateInvoiceModal use the paged+search endpoint instead of loading 500 orders), `6a08f1f` (portal serves the real workshop contact instead of a hardcoded placeholder), `4a1c7f1` (UsersPage account status via `<StatusBadge kind="user">`), `e22e925` (remove dead CSS rules with zero class usages), `2b20d6a` (docs: remove mentions of the removed Pause button and the old 14-tab order page).
- Left open: the rest of W7-06's own file list (sanitize_text blocklist, `async_sessionmaker`/`get_db` annotation, `.dict()` calls, blocking `write_bytes`, notification-scanner N+1, `metal_inventory.py detail=str(e)`, `health.py` exception text, remaining `window.prompt`/`confirm`, QrCameraScanner hooks, unmemoised context values, scan sounds not precached, LoginPage 429 message, deep-link `from` lost at login) plus `order_materials` ondelete/`orders.status` index/unbounded String columns (need a migration) — all deferred; the ~120-row Wave1-7 open-follow-ups backlog table was scanned but left untouched; a few `FEATURE_X.md` doc links missing the `features/` path were noticed, not fixed.
- Evidence: pytest FINAL (post-merge re-run) 4191 passed/12 skipped/1 xfailed, exit 0 (identical to the mid-pass run); vitest 130 files/1005 passed, exit 0; lint 5 errors (OrderFormModal, pre-existing at the time); lint-imports 2 kept/0 broken; hex-ratchet 1082 (baseline 2087, down 1005), exit 0.

### Final state on the pushed head — full-suite totals and third live pass
- **Final verified numbers**: backend 4408 tests passed, frontend 1092 tests passed, `yarn lint` 0 errors, hex-literal ratchet 2113 → 612, `make types-check` and `lint-imports` both clean.
- **Third live pass**: a fresh-database migration to head succeeded, a downgrade/upgrade round trip succeeded, `scripts/seed_demo.py` succeeded, and the PostgreSQL integration suite passed 952 (its screenshot portion was interrupted mid-run, which is not counted as a failure).
- PR #51 remains the draft PR / review vehicle for `audit/2026-09-fixes` vs. `main` at this state.

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
| **Reminder emails until CustomerMessage exists** (D-07) | At most once per order event, recorded as a `CustomerUpdate` row visible in Kundeninfo, never sent directly from a staff-notification path. **CustomerMessage now exists (W6-02)** and is the single outbound path for all customer mail, including quotes. | Max |
| **Estimator cost basis** (D-09) | Labor priced at `hours_p50 × blended rate`; `suggested_activities` zero-filled and shown only when present in ≥50% of the matched set. The alternative (per-activity medians as a breakdown) was not chosen. | Max |
| **Fake timer "Pause" removed** (D-15) | The Pause button (which froze the *display* while the server kept billing) was deleted outright in W1-14, not replaced. W2-14 explicitly did not build a real server-side pause/resume UI, leaving this for a future decision. | Anne |
| **Valuation PDF export is ADMIN-only** | GOLDSMITH lost the ability to download the valuation PDF as part of the VIEWER-projection sweep (the permission model made ADMIN-only the safe default). If Anne needs GOLDSMITH to hand these to customers directly, it's a one-line permission grant. | Anne, Max |
| **GDPR erasure keeps statutory records via a legal hold, not a hard block** | Erasure now anonymises the customer row and sets `retention_hold_until` (newest retained record's year-end + 10y) rather than refusing the request outright; invoices/accepted quotes/signed Altgold records are excluded from `SCRUBBABLE_FIELDS` with their own `RETAINED_RECORD_FIELDS`/`RETAINED_RECORD_MODELS` lists. | Anna, lawyer |
| **All quotes retained on erasure, not just accepted ones** | Conservative: every quote (including drafts and rejected ones) is currently kept, though §147 AO likely only requires Handelsbriefe (sent/accepted). Retention length used is 10y; Steuerberater should confirm whether 8y (Buchungsbelege, BEG IV) applies instead. | Steuerberater |
| **System-monitor single-runner via advisory lock, PostgreSQL-only** | `pg_try_advisory_lock` elects one leader among uvicorn workers; on any non-PostgreSQL engine (e.g. SQLite dev) every process is treated as leader — a documented, not-fixed gap for non-PG deployments. Production must run PostgreSQL with `--workers 2`. | Max |
| **`ANONYMIZATION_SALT` length/entropy floor deliberately not added** | The adversarial round suggested mirroring `validate_secret_key`'s length check on the salt; not implemented because several out-of-scope test fixtures use shorter, realistic salts in `DEBUG=False` tests and would break. Flagged, not fixed. | Max / whoever owns SEC-02 next |
| **Realtime hints never carry price/cost/title/description over the wire** | The new `/ws/events` whitelist only ever sends `action, source, order_id, status, location` (orders) or ids/timestamps (timers/notifications) — clients must refetch the already-role-projected REST endpoint for details. This assumes no screen needs live financial data pushed, only a "something changed, go refetch" signal. | Max (product) |
| **New orders start as DRAFT and must be confirmed** | W2-07's transition table makes DRAFT the entry state; the legacy `NEW` status maps to DRAFT (no price) or CONFIRMED (price already set) at migration time. Adds a step for walk-in orders that were previously created directly as an active status. | Max |
| **VIEWER valuation PDF stays ADMIN-only after Wave 2** | No change from the earlier decision above; reconfirmed as still in force through the design/status work in Wave 4. | Anne, Max |
| **Photos in customer updates need PHOTO_USE consent, in tension with the privacy-notice wording** | `photo_update` messages (W6-02) require an active PHOTO_USE consent (Art. 6(1)(a)), stricter than `DATENSCHUTZHINWEISE-KUNDEN.md` §2's Art. 6(1)(b) framing of "selected photos of your piece". PHOTO_USE's stated purpose ("Portfolio, Social Media") now also implicitly covers "photos by email to the customer" without its own dedicated purpose — flagged for the Datenschutzberater. | Anna, Datenschutzberater |
| **Outbox mode default** | `settings.outbox_mode` = `OUTBOX_MODE` env var, else `inline` if `DEBUG` else `worker`; dev compose defaults to inline, `podman-compose.prod.yml` sets `OUTBOX_MODE=worker` on backend and worker. | Max |
| **Legacy list fallback keyed on `offset` presence** | W3-08's `Page[T]` envelope triggers only when the request includes `offset`; the plan's own brief said "no limit/offset" should trigger it, but the current frontend always sends `limit`/`skip`, so presence-of-`offset` was chosen instead — needs the orchestrator/product owner to confirm this is the intended long-term contract before the frontend is migrated onto it. | Max |
| **Auftragsnummer (human-facing order number) not built** | D-12 said yes; W2-04 built the counter/`NumberSequence` service for invoice numbering only, ready for WG/REP adoption, but did not wire a customer-facing Auftragsnummer onto orders. | Max |
| **Repair intake signature not stored** | W2-12 explicitly stopped short of persisting a captured signature — no schema change was made — pending a decision on how/whether to add it. | Anne, Max |
| **lodash pinned to 4.18.1, not Dependabot's suggested 4.18.0** | 4.18.0 broke `vite build`'s service-worker generation via workbox-build's `lodash/template` use; 4.18.1 clears the same advisory without that regression. | Max (informational) |
| **Ruff runs in CI but stays non-blocking** | `ruff check` gates nothing yet (`--exit-zero` against a 994-error baseline) — a deliberate choice to surface findings without blocking merges while the baseline is burned down. | Max |
| **Demo/seed credentials unified** | One canonical set (`demo-inhaber@werkstatt.de`/`demo2026!` plus the other `DEMO_USERS`) now used by every seed script and the 3 previously-hardcoded Playwright specs, closing a drift that caused a run of live-verification and E2E failures. | Max (informational) |
| **Kundeninfo "ticked photos win"** | `default_photo_ids`: ticked ids always win; a `PHOTO_UPDATE` with no ticks falls back to flagged (`customer_visible`) photos; a text-only message never auto-attaches photos. Chosen because the literal "flagged always wins" rule would force text-only messages to also require PHOTO_USE consent. **Not yet confirmed with Max.** | Anne, Max (fix-w6-media.md) |
| **Repair costs billed net** | `RepairJob.estimated_cost`/`actual_cost` billed NET per the task's instruction, undocumented elsewhere; recorded in `docs/architecture/ADR-2026-09-25-jobs-spine.md`. | Steuerberater/workshop, re: PAngV/gross consumer-price rules (fix-w6-jobs-spine.md) |
| **Outbox inline vs. worker mode (confirmed default)** | `settings.outbox_mode = OUTBOX_MODE or (inline if DEBUG else worker)` — inline in dev/DEBUG, worker/queue in prod, overridable via `OUTBOX_MODE`. | Max (fix-w6-outbox.md) |
| **Order numbers via jobs (jobs spine)** | The `jobs` table now owns numbering: `AU-YYYY-NNNN` for orders, `REP-YYYY-NNNN` for repairs, via `number_sequences`; repair numbering moved off its old scheme onto this. | Max (fix-w6-jobs-spine.md) |
| **Media `customer_visible` flag** | Drives which photos a Kundeninfo/status-report may show without an explicit tick (see the ticked-photos-win decision above); landed in `4e85439`. | Anna, Max (fix-w6-media.md) |
| **Legacy list fallback keyed on `offset` (confirmed applied uniformly)** | Every new paged filter/sort param (`sort`, `status`, `created_from`, `q`, …) is accepted-but-silently-ignored when the caller doesn't supply `offset` (legacy plain-list mode); only sending `offset` opts into the new Page-envelope behavior with full validation (422 on an unknown sort field). Now confirmed applied uniformly across orders/repairs/quotes/materials/time-entries/notifications/customers. | Max (fix-w3-sort-paging.md, extends the W3-08 decision above) |
| **No speculative migrations** | Several items were deliberately left un-fixed rather than add a migration outside a task's stated scope: `AlloyType` enum extension, `attach_status_report` kept request-only/not persisted, the workshop care-text column, `job_id` columns staying nullable. | Max (cross-cutting; multiple reports) |
| **python-jose → PyJWT was a pure exception-type swap** | `JWTError` → `jwt.InvalidTokenError` only, no logic change, to preserve the existing catch-all behavior. | Max (informational; fix-w7-hygiene-backend.md) |
| **hex-ratchet baseline never force-updated by individual worktree agents** | `node scripts/hex-ratchet.mjs --update` was deliberately skipped by every worktree agent to avoid cross-branch conflicts; the orchestrator locks it in periodically instead (`c9523b9` at 1082, `69d966c` after the page migrations, down to 612 by the final pass). | Max (informational; cross-cutting) |

## (c) Open follow-ups

Collected from every report's "Open items" section. Severity is a guess, not
a re-triage; suggested wave follows the master plan's existing item where one
owns the area, otherwise the most plausible new home. Items resolved by later
work in this same pass are marked so and removed from the active list below
that point; see the changelog above for exactly which commit closed them.

**Wave 1 residue (still open after all waves in this pass):**

| Item | Source report | Severity guess | Suggested wave |
|---|---|---|---|
| `cap_drop: [ALL]` (+ minimal `cap_add`) not added to any compose service — needs a live container runtime to boot-test | fix-w1-01-02-deploy.md | L | W5-03 |
| Image digest pinning (sha256) instead of exact tags | fix-w1-01-02-deploy.md | L | deliberate, separate process |
| BE-25: quotes still build lines from a separate, cost-based, hardcoded-rate path; no shared `LineItemBuilder` | fix-w1-money-path.md | M | W3-11 |
| `QuoteService.calculate_totals` still uses float + `round()`, unlike the Decimal `InvoiceService.calculate_totals` | fix-w1-money-path.md | M | W3-11 (still in progress) |
| Existing orders from earlier quote conversions may hold gross values in `Order.price` under the new NET semantics — needs a one-off data review before go-live | fix-w1-money-path.md | H | pre-go-live data migration |
| Invoice `tax_rate` defaults to 19% even when a converted quote used a different rate | fix-w1-money-path.md | M | W2-04 (not addressed there) |
| `total_fine_gold_g` mixed-metal breakdown — **partially fixed**: `e7f6913` added a computed per-metal breakdown to the read response; still no schema/migration change, no Ankaufsabschlag % field | fix-w1-altgold.md, fix-w7-backlog.md (DOM-20 remainder) | M | W2-16 (still needs a schema migration) |
| BE-21: monitor still shares one DB session across its 4 scans — one error aborts the rest of that tick | fix-w1-email-loop.md | M | W1-12 follow-up, unowned |
| No per-order customer-email opt-out column (Art. 21 opt-out via consent rows exists instead, W6-02) | fix-w1-email-loop.md | M | superseded by W6-02's approach |
| SEND_FAILED automated mail retries once per day forever while SMTP stays misconfigured | fix-w1-email-loop.md | L | unowned |
| `api/routers/materials.py`'s photo-upload path still not wired through the EXIF-stripping/bomb-protection hardening | fix-w1-18-images.md | M | W1-18 follow-up |
| F-3: the label print script is still blocked by CSP (deliberately not relaxed) | fix-w1-security-config.md | M | needs a CSP-hash-friendly print approach |
| slowapi rate-limit storage still in-memory per worker (no Redis `storage_uri`) | fix-w1-security-config.md | M | W1-03 follow-up |
| No email notice to the old address when a user's email/password changes | fix-w1-security-config.md | L | W1-19 follow-up |
| `update_invoice` still allows notes/due_date edits on SENT/OVERDUE invoices | fix-w1b-migrations.md | M | W2-04 (not addressed) |
| `ActiveTimerWidget.tsx` still has the fake-pause pattern, but is dead/orphaned code | fix-w1-14-bench-session.md | L | W3-01 dead-code cleanup |
| `MainLayout.tsx` calls `timeTrackingApi.stop()` directly, bypassing `TimeTrackingContext` | fix-w1-frontend-flows.md | L | cleanup when the file is next touched |
| Time booking on repairs needs `TimeEntry.repair_job_id` | fix-w1-frontend-flows.md | M | W6-04 (jobs spine, still open) |
| `db/repositories/customer.py::update_consent()` targets attributes that no longer exist (dead code) | fix-w1-gdpr-erasure-consent.md | L | W3-09 (still open) |
| Repair `item_description`/`diagnosis_notes` still shown to VIEWER (front-desk needs them) | fix-w1-viewer-leaks.md | M | product decision |
| `ANONYMIZATION_SALT` has no length/entropy floor | adversarial-w1.md | M | whoever owns SEC-02 next |
| `get_client_ip`: malformed hop / IPv4-mapped-IPv6 edge cases | adversarial-w1.md | L | backlog |

**Wave 2 through Wave 7 open items:**

| Item | Source report | Severity guess | Suggested wave |
|---|---|---|---|
| Scanner deep links `?edit=location`, `?action=print-label`, `?action=consume-material` unhandled on the order page | fix-w2-01-photos.md | M | not stated |
| No client-side photo downscale; >8MB rejected | fix-w2-01-photos.md | L | not stated |
| PhotoCompare styles live in `repairs.css`; move to a component stylesheet | fix-w2-01-photos.md | L | Wave 4 |
| PDF-manual "mark delivered" for a repair update doesn't stamp `RepairJob.customer_notified_at` | fix-w2-02-repair-updates.md | M | not stated |
| `RepairCustomerUpdatePanel` has no PDF-download/mark-delivered fallback when SMTP is down | fix-w2-02-repair-updates.md | M | not stated |
| DOM-15c receivables/overdue-invoices card not built | fix-w2-03-dashboard.md | M | not stated |
| Old `DeadlinesWidget` unmounted but still exported (dead code) | fix-w2-03-dashboard.md | L | Wave 4 cleanup |
| `days_overdue` Berlin-day calc could be off by one day for legacy naive-UTC deadlines | fix-w2-03-dashboard.md | M | not stated |
| Concurrent "Versenden" clicks could send two quote emails (no CAS before send) | fix-w2-05-quote-send.md | M | not stated |
| Quote without an order: delivery record has `order_id=NULL`, invisible in Kundeninfo | fix-w2-05-quote-send.md | M | not stated |
| Approval evidence stored as text in `quote.notes`, not a dedicated column | fix-w2-05-quote-send.md | L | not stated |
| Approve/decline link in customer email not built | fix-w2-05-quote-send.md | M | W6-07 |
| Gemstones/weight not carried into order on quote conversion | fix-w2-05-quote-send.md | M | W2-06 |
| Legacy/custom metal types (333, 900 gold) missing from the alloy/color picker | fix-w2-06-14-16-11.md | M | needs a MetalType enum value |
| New orders can't add gemstones until after creation | fix-w2-06-14-16-11.md | M | not stated |
| TimerWidget server-side pause/resume (D-15) — **backend fixed** (`5242fc0`, fix-w2x-open-items.md); still open: the "frozen ticker while paused" UI polish not built, emoji icons (⏸️▶️⏹️) remain against the playbook's ban, `InterruptionRead` still lacks `resumed_at` | fix-w2-06-14-16-11.md, fix-w2x-open-items.md | M | not stated |
| GDPR Art.15 export of scrap-gold ID fields — **fixed** (`86e6e78`: export now includes `id_document_type/number/issuing_authority/id_checked_at` + a retention-schedule row, fix-w2x-open-items.md); still open: no admin export UI | fix-w2-06-14-16-11.md, fix-w2x-open-items.md | L | GDPR/customer service |
| Handover care text hardcoded (not workshop-editable) | fix-w2-06-14-16-11.md | L | needs a WorkshopSettings column |
| `quote_service.convert_quote` still creates orders with `status=CONFIRMED` directly, bypassing the transition table | fix-w2-07-lifecycle.md | M | not stated |
| `customer_portal.py`/`scanner_service` label/status maps lack on_hold/cancelled | fix-w2-07-lifecycle.md | M | not stated |
| Legacy `order_status_history` table + dead `db/repositories/order.py` writer remain | fix-w2-07-lifecycle.md | L | W3-09 |
| Order-lifecycle migration not exercised on PostgreSQL | fix-w2-07-lifecycle.md | H | before deploy |
| Status label map duplicated across multiple pages with stale labels | fix-w2-08-order-page.md | M | Wave 4 `src/design/status.ts` |
| `PRIMARY_NEXT_STATUS` choices are a product guess | fix-w2-08-order-page.md | Decision | needs Anne/@goldsmith check |
| `AlloyType` enum still missing bare 935 (Ag935) and Palladium values — hallmark **vocabulary** recognition for these marks landed (`aac9bcc`, fix-w2x-open-items.md), but the enum extension itself was skipped (needs a migration), so `ScrapGoldItem.alloy` still can't persist them | fix-w2-09-hallmark.md, fix-w2x-open-items.md | M | W2-16 owner |
| D-12 Auftragsnummer not built; counter service ready for WG/REP adoption | fix-w2-10-04-customers-invoices.md | L | not stated |
| Storno reversal in DATEV/Lexoffice export booked under the original's date | fix-w2-10-04-customers-invoices.md | M | accounting_export_service |
| `InvoicesPage.tsx` has no Storno button/badge yet | fix-w2-10-04-customers-invoices.md | M | not stated |
| CSV customer import still requires an email column | fix-w2-10-04-customers-invoices.md | M | not stated |
| `templates/invoice.html` preview template not updated to the new §14 layout | fix-w2-10-04-customers-invoices.md | M | not stated |
| One VAT rate per invoice; mixed-rate invoices unsupported | fix-w2-10-04-customers-invoices.md | L | known model limitation |
| Repair intake signature persistence not built, needs a migration | fix-w2-12-repair-intake.md | M | migration owner |
| Stone-liability clause + pickup note in the Annahmeschein PDF are draft wording | fix-w2-12-repair-intake.md | H | legal/workshop-owner review |
| Consultations missing from customer Verlauf despite DOM-38 mentioning them | fix-w2-12-repair-intake.md | M | small follow-up |
| Customer-activity UNION verified on SQLite only, not against PostgreSQL | fix-w2-12-repair-intake.md | M | pre-deploy verification |
| Remaining WS hardening: reject `?token=` query auth, check `is_active`, Origin check, lifespan-managed task cancellation | fix-w2-13-realtime.md | M | W3-10 |
| Unrouted realtime channels: `material_updates`, `consultation_updates`, `metal_price_updates`, `anomaly_alerts` (`repair_updates` and a new `job_updates` channel are now routed to staff sockets — fixed by `7fa6f41`, fix-w6-repair-realtime.md) | fix-w2-13-realtime.md | M | W2-13 follow-up / W3-10 |
| Dashboard/Orders/OrderDetail/Repairs pages don't call the new `useRefetchOn` bus yet | fix-w2-13-realtime.md | M | owned by their pages |
| `OrderLegacyFields` kept on `OrderType` until legacy callers migrate | fix-w3-api-types.md | M | W3 follow-up |
| Input types (Create/Update) for materials, metal inventory, calendar, estimator, time-stats still hand-written | fix-w3-api-types.md | M | W3 extension |
| Frontend not migrated to send `offset`/read `code` for `Page[T]`/`DomainError` | fix-w3-backend-contract.md | M | next wave |
| Customer-name search decrypts all active customers per `q` (O(N)) | fix-w3-backend-contract.md | M/H | future DB migration wave |
| Customers/invoices lists not paginated; activities/comments/users/calendar not paged at all | fix-w3-backend-contract.md | M | future wave |
| 63 router except-blocks not yet migrated to `DomainError` | fix-w3-backend-contract.md | L | gradual cleanup |
| `ActiveTimerWidget` div→button visual delta (global button reset CSS) not verified in a browser | fix-w3-eslint.md | M | W3 visual QA |
| Backend theme default #d97706 not AA — **closed by W7 hygiene**, `7c30827` | fix-w4-01-tokens.md | — | resolved |
| `@axe-core/playwright` not installed; `a11y-smoke.spec.ts` skipped, no automated axe run | fix-w4-01-tokens.md | M | W4 (after a dependency bump) |
| ~20 umlaut strings (DES-17) in `.tsx` files — **partially closed by live-verification**, remainder in CustomerFormModal, Toast, CommentsTab, ScrapGoldTab, ScanOverlay, QuickActionModalV2, UserSettingsPage, `schema.d.ts` | fix-w4-01-tokens.md, fix-live2.md | L | Wave 3/4 (frontend copy) |
| `--color-warning-600`/`-500` still fail AA | fix-w4-01-tokens.md | M | W4 continuation |
| Hardcoded `#d97706`/`#f59e0b` remain in `order-detail.css`/`dashboard.css` | fix-w4-01-tokens.md | H | "phase 3" |
| Legacy z-index literals not remapped to the new `--z-*` scale | fix-w4-01-tokens.md | M | "phase 3" |
| Focus ring shipped at 2px vs the playbook's 3px, unreconciled | fix-w4-01-tokens.md | L | needs a decision |
| `StatusBadge` not wired into `DataTable` | fix-w4-02-primitives.md | M | W4 continuation |
| Icon set is an inline stand-in; adopting a library needs a `package.json` change | fix-w4-02-primitives.md | L | future |
| `ConfirmDialog`/`useConfirm` not migrated onto the new Modal | fix-w4-02-primitives.md | L | migration item |
| `docs/architecture/likec4/package-lock.json` still vulnerable (separate Node project) | fix-w5-deps.md | M | separate cleanup |
| Frontend coverage has no enforced threshold yet | fix-w5-deps.md | L | pair with W5-02 |
| PG/live restore drill not performed | fix-w5-gdpr-ops.md | H | pre-go-live |
| Erasure-ledger gap: post-backup erasures lost if the DB is lost before the next backup | fix-w5-gdpr-ops.md | M | needs a `customer_service.py` hook |
| `restore.sh` lacks `ON_ERROR_STOP` on the psql pipe | fix-w5-gdpr-ops.md | M | hardening |
| systemd cleanup service still defaults to `podman-compose.yml` (dev) | fix-w5-gdpr-ops.md | M | GDPR-16 remainder, W5-03 |
| `backup-sync.sh` URL-only auth; `./uploads` not backed up | fix-w5-gdpr-ops.md | M | GDPR-06 remainder |
| Retention sweep not extended to inactive customers/consultations/quotes/notifications/audit logs | fix-w5-gdpr-ops.md | M | RETENTION_SCHEDULE.md §4 |
| `GDPR_EXPORT` permission not added; export still gated on `CUSTOMER_DELETE` | fix-w5-gdpr-ops.md | L | permissions.py |
| GDPR-14 (analytics.py vs. employee notice) needs Anne's decision | fix-w5-gdpr-ops.md | M | product/legal decision |
| GDPR-15 TLS enforcement on every SMTP port | fix-w5-gdpr-ops.md | H | W5-09 |
| D-13 (wishes/source_material in export) pending lawyer confirmation | fix-w5-gdpr-ops.md | M | legal sign-off |
| Retention periods and DPO/AVV structure pending Steuerberater/Datenschutzberater sign-off | fix-w5-gdpr-ops.md | M | legal sign-off |
| e2e-nightly.yml never had a live CI run | fix-w5-ops-ci.md | M | verify post-merge |
| Ruff baseline (994 errors) kept non-blocking by design | fix-w5-ops-ci.md | L | burn-down ticket |
| ARCH-16 C4/likec4 model not updated (tool fails to parse) | fix-w5-w7-remainder.md | M | fix likec4 first |
| ARCH-16 no ADRs for jose/estimator/no-portal decisions | fix-w5-w7-remainder.md | L | optional doc debt |
| OPS-03 mypy widen-without-shrink gate not implemented | fix-w5-w7-remainder.md | M | dedicated design pass |
| OPS-10 move `test_filter_by_tag` to `tests/integration/` | fix-w5-w7-remainder.md | L | test hygiene |
| W5-04 realtime WS contract test not added | fix-w5-w7-remainder.md | M | dedicated pass |
| W5-06 encrypt remaining sensitive columns not done | fix-w5-w7-remainder.md | H | dedicated pass |
| W5-12 one-shot migrate service + Sentry/GlitchTip wiring not implemented | fix-w5-w7-remainder.md | M | dedicated pass |
| W7-01/02/03/05 (workshop model, aftercare, offline queue, audit decorator) not implemented | fix-w5-w7-remainder.md | M | separate feature waves |
| W7-04 feature flags not implemented; unused `boto3` confirmed dead, not removed | fix-w5-w7-remainder.md | L | cleanup ticket |
| W7-06 frontend hygiene not implemented; `frontend/.yarn/install-state.gz` still committed | fix-w5-w7-remainder.md | L | frontend cleanup |
| Retry of a failed `quote_sent` via the generic send endpoint mis-derives kind, would wrongly refuse prices | fix-w6-customer-messages.md, fix-w6b-comms.md | M | still open |
| E7: no recipient confirmation/masked-address step before the first photo mail | fix-w6-customer-messages.md, fix-w6b-comms.md | H | frontend UI change |
| PHOTO_USE consent purpose overloaded; privacy-notice wording not aligned | fix-w6-customer-messages.md | M | consent model change |
| No privacy line on the customer-update PDF | fix-w6-customer-messages.md | L | pdf_service.py |
| No invoice email path yet in the outbox | fix-w6-outbox.md | L | dev-discipline note |
| Queued outbox state shown as delivered=True/"Versendet" until the worker actually sends | fix-w6-outbox.md | M | needs a design/status.ts update |
| Outbox delivery is at-least-once; possible resend after a lease expires on crash | fix-w6-outbox.md | M | idempotency hardening |
| No retention/cleanup job yet for sent outbox rows | fix-w6-outbox.md | M | needs a scheduled job |
| E8: TLS not enforced on every SMTP port; no signed AVV with the SMTP provider | fix-w6b-comms.md, fix-w5-gdpr-ops.md | H | W5-09 |
| E17: Art. 30 entry + DSFA screening not added to the VVT doc | fix-w6b-comms.md | M | VVT doc edit |
| `attach_status_report` not persisted (no DB column/migration) | fix-w6c-status-report.md | L | future migration |
| Repair photos have no consent/selection precedent; latest 6 shown unconditionally | fix-w6c-status-report.md | M | product decision |
| Repair timeline — a real per-job timeline endpoint now exists (`GET /jobs/{job_id}/timeline`, `e407eb6`, ARCH-02 part 3), but the Repair Verlauf UI still synthesizes its own timeline instead of switching to it | fix-w6c-status-report.md, fix-w4-page-repairs.md | M | wire Verlauf onto `/jobs/{job_id}/timeline` |
| `docs/DEPLOYMENT.md`/`DEPLOYMENT_LOCAL.md` show stale sample credentials | fix-w7-hygiene-backend.md | L | doc fix |
| Route remaining out-of-scope components through `<StatusBadge>` (CostChangeSection, KundeninfoTab, RepairCustomerUpdatePanel, HandoffTab, hallmarks.ts, ScrapGoldTab, CustomerDetailPage) | fix-live-frontend.md | M | Wave 3/4 frontend consistency |
| Delete unused old badge CSS (`.quote-status-badge*`, `.invoice-status-badge*`, `.consultation-status-badge*`) | fix-live-frontend.md | L | Wave 4 cleanup |
| Quotes list "Kunde" column shows raw `#id`, not a name; `ConsumeMetalModal.tsx`/`InvoicesPage.tsx` still call `customersApi.getAll({limit:500})`; quotes/invoices still have no realtime channel; `/invoices/` still has no Page envelope (legacy skip/limit) | fix-live-frontend.md, fix-live2.md (LV2-06), fix-w4-page-quotes-invoices.md | M | Wave 3/4 (backend join + frontend) |
| `layout.css` retains old 768px/480px media queries alongside the new 600/1024 breakpoints | fix-live-frontend.md | L | Wave 3 cleanup |
| `convert_quote` race: loser gets 409 or 422 depending on `FOR UPDATE` lock timing — inconsistent status code | fix-live-backend.md | M | product/API decision |
| LV-12 remaining sub-44px controls: header "System" button, invoices status select, invoices PDF button | fix-live2.md | L | Wave 3 frontend |
| LV2-05: order-detail tab strip at 390px has no gap/scroll cue | fix-live2.md | L | Wave 3, needs live browser verification |
| LV-19 at 1280: AKTIONEN column still clipped, FAB still overlaps a row | fix-live2.md | L | Wave 3, needs re-verification |
| Wire `tests/integration/test_pg_concurrency.py` into the required CI pipeline | fix-live-backend.md | M | Wave 3 CI |

**Since checkpoint 2 (new open items from the ~25 later fix branches):**

| Item | Source report | Severity guess | Suggested wave |
|---|---|---|---|
| `TimerWidget.tsx:62` `runningEntry.start_time + 'Z'` unconditional — will double-apply the tz offset on an already-Z-suffixed value | fix-w3-outbox-migration.md | M | owned by another agent |
| Naive-datetime grace period still accepted end-to-end (~200 `datetime.utcnow()` calls remain in tests); remove next release | fix-w3-numeric-tz.md | L | next release |
| BE-14 "sum of *rounded* line totals" not applied — needs a product/Steuerberater decision | fix-w3-numeric-tz.md | M | product/Steuerberater decision |
| `cli/gdpr_replay_erasures.parse_since` still returns naive UTC | fix-w3-numeric-tz.md | L | cleanup |
| Bench (W4-03) residue: no footer/nav-hiding or user-menu toggle for bench mode; `ScanOverlay` not on the `src/ui` Sheet; time-entry list lost free-text/activity/duration-sort filters (no server param); `TimeEntryFormModal` still parses/submits naive UTC; `status.ts` has no "Läuft" `StatusKind`; `orderEntriesQuery` has no consumer yet | fix-w4-page-bench.md | M | Wave 4 continuation |
| Nav/admin/order-form (W4-03) residue: stones on a new order not editable same-step; stone-deletion UX needs a product call; Scan FAB not yet in the phone tab-bar centre; Altgold has no standalone route; `orders.css` has dead rules; `adminKeys` outside shared `queryKeys.ts`; `SystemStatusPanel` health labels not in `status.ts`; `ScanAdoptionDashboard.tsx` ~20 colour literals; tab bar "Mehr" slot needs a button item | fix-w4-page-admin-nav-form.md | M | Wave 4 continuation |
| Group-E (W4-03) residue: CSS leaks into out-of-scope pages (`.detail-item`, `.btn-pdf-download`, `.btn-retry`); `useMetalTypes` module cache not migrated to a query; materials sort/low-stock filter page-local only; scrap-gold manual gold-price input read-only (no API field); `StyleNoGoStep` keeps a plain `<label>` | fix-w4-page-group-e.md | M | Wave 4 continuation |
| Portal `status_label` via StatusBadge triggers an unknown-key console warning; `RegisterPage` exists with no route | fix-w4-page-group-f.md | L | cleanup |
| Repairs-UI (W4-03) residue: `repairKeys` outside shared `queryKeys.ts`; status-step gating uses `canCreateRepairs` pending a real `canEditRepairs`; `IntakeChecklist` only partly on primitives; inconsistent dirty-dialog prompts (intake "Abbrechen" vs. Escape/close) | fix-w4-page-repairs.md | M | Wave 4 continuation |
| ARCH-09 follow-ups: convert models to `Mapped[]` module-by-module; remove the `core.permissions → api.deps` edge then widen import-linter contract 2; add `lint-imports` to CI; fix pre-existing PG drift (`scan_logs` partitions/types/index); `scripts/seed_data.py` imports a nonexistent `DataRetentionPolicy` | fix-w6-models-split.md | M/L | dedicated cleanup |
| Jobs spine (ARCH-02): `job_id` columns stay nullable (make NOT NULL once `count_missing()`=0 in prod); quote-delivery records get no `job_id` | fix-w6-jobs-spine.md | M | pre-prod hardening |
| Werkstatt board: only input-free repair transitions (diagnose/approve/complete still need the detail page), no drag-and-drop, 8 requests/load (one per column); startup job-backfill logs and continues on failure rather than stopping startup | fix-w6-jobs-followups.md | M | Wave 6 continuation |
| `job_updates` publish fires inside the caller's open transaction, not strictly post-commit (callers out of scope) — documented compromise | fix-w6-repair-realtime.md | M | documented compromise |
| Media: no orphan sweep (soft-delete doesn't cascade to `media_assets`, polymorphic/no FK); `customer_service` scrub only clears legacy `notes`; PDF/email/scanner/thumbnail readers still read legacy photo tables (dual-write not retired) | fix-w6-media.md | M | dedicated pass |
| Media restore not erasure-replay-aware (a restored archive can resurrect a file for an already-erased customer) — documented known gap, not fixed; `compute_sha256()` duplicated in `backup.sh`/`restore.sh` instead of the shared lib | fix-w6-restore-media.md | M | dedicated pass |
| `test_migration_w210_w204.py::test_chain_is_linear_w207_w210_w204` failed once pre-merge, passed isolated post-merge — possible ordering flake, not investigated (migrations out of scope) | fix-w6b-comms.md | L | investigate ordering |
| Full ~4000-test backend suite not re-run after the W2X final merge (targeted slice only) — recommended before merging to `main` | fix-w2x-open-items.md | H | pre-merge-to-main verification |
| `scrap_gold_service.py`'s `_price_for_item`/`_recalculate_totals` indexes the raw 3-metal spot-price dict; will `KeyError` (not the typed `MetalPriceError` contract) if `AlloyType` ever gains palladium | fix-w2x-open-items.md | M | Wave 2 continuation |

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
poetry run ruff check goldsmith_erp/   # non-blocking baseline, 994 errors expected
cd ..

# Adversarial round only:
poetry run pytest -q tests/adversarial/ -rxX
# Expect: passed + xfailed, 0 failed, 0 unrouted.

# PostgreSQL-dependent paths (migrations, partial indexes, FOR UPDATE,
# tz-aware columns, the two-session concurrency suite) — set up a real PG
# instance (the live-verification passes used a throwaway Postgres 15
# container on 127.0.0.1:5434, Redis on 127.0.0.1:6391):
export TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test
export MIGRATION_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/goldsmith_test
poetry run pytest -q tests/integration/<file>
poetry run pytest -q tests/integration/test_pg_concurrency.py
poetry run alembic upgrade head && poetry run alembic downgrade -1 && poetry run alembic upgrade head

# Exact PG/Redis env-var form used by the live-verification and worktree
# integration runs (port/creds/db throwaway, matches the live containers):
export TEST_DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5434/goldsmith_test
export REDIS_URL=redis://127.0.0.1:6391/<n>            # n varies (0/1/5/…) per parallel worktree
export MIGRATION_DATABASE_URL=postgresql://user:pass@127.0.0.1:5434/goldsmith    # or a scratch DB name
export MIGRATION_TEST_DATABASE_URL=...                  # used by test_migration_h9_roundtrip specifically
pytest tests/integration -x --maxfail=10                # the live-verification passes' own PG-suite invocation

# Frontend:
cd frontend
yarn lint                          # ESLint 9; 0 errors project-wide as of the final pass (was 5, all OrderFormModal.tsx)
yarn eslint .
yarn lint:fix
yarn vitest run                    # full suite
yarn vitest run <path>              # a single file
yarn vitest run --reporter=dot
npx tsc --noEmit
yarn tsc --noEmit -p tsconfig.json
node node_modules/vite/bin/vite.js build   # `yarn build` itself still exits
                                             # 127 in a fresh checkout — FE-25,
                                             # unresolved; this is the documented
                                             # workaround every fix agent used
cd ..

# Generated-types drift gate and combined local gates:
make types-check                   # fails if frontend/src/api/generated/schema.d.ts drifts from the live OpenAPI spec
make types                         # PYTHON=<venv python> make types — regenerates openapi.json + schema.d.ts
make lint-local                    # local equivalent of the CI lint job (backend + frontend); this is CLAUDE.md's
                                    # own invocation of lint-imports too, see below
make test-local                    # local equivalent of the CI test job
make install-timers                # installs the GDPR/retention/health-watchdog systemd timers
node scripts/hex-ratchet.mjs                 # check the hex-literal count against baseline
node scripts/hex-ratchet.mjs --update        # only the orchestrator runs this (see Decisions) — not individual agents

# lint-imports (import-linter; config: .importlinter at repo root):
lint-imports
PYTHONPATH=src poetry run lint-imports
# In a worktree, `poetry run lint-imports` has been observed to try to create a NEW venv instead of
# reusing the pinned one — call the pinned venv's binary directly with an explicit --config instead:
/path/to/goldsmith-erp-<hash>-py3.11/bin/lint-imports --config <worktree>/.importlinter

# Worker entrypoint (transactional outbox, ARCH-04/05/12):
python -m goldsmith_erp.worker
python -m goldsmith_erp.worker --once
python -m goldsmith_erp.worker --healthcheck
```

Every fix agent ran from a git worktree with no `.env` file, so `Settings()`
needs the four env vars above set explicitly or it refuses to boot
(`ENCRYPTION_KEY must be set in production`) — this is expected, not a bug.

## (e) Checkpoint for Max

Waves 1, 2, 3, 5 and 6 are now substantially complete (jobs spine, media,
transactional outbox, quote-email routing, customer status report PDF all
landed since the last checkpoint). Wave 4's page-migration playbook (W4-03)
is now done for every page group (order detail, quotes/invoices, groups E and
F, repairs, bench UI, nav/admin/order form). Wave 7 is still mostly backlog
except for the hygiene work that landed opportunistically (W7-06's 8/8
explicit candidates, backend hygiene). **Final verified state on the pushed
head:** backend 4408 tests passed, frontend 1092 tests passed, `yarn lint` 0
errors, hex-literal ratchet 2113 → 612, `make types-check` and `lint-imports`
both clean; a third live pass confirmed a fresh-database migration to head, a
downgrade/upgrade round trip, a successful seed, and a 952-passed PostgreSQL
integration suite (its screenshot portion was interrupted, not a failure).
Before treating this as a release candidate:

1. **Run `/code-review ultra` on PR #51** (the review vehicle for `audit/2026-09-fixes` vs. `main`) now that Waves 1–3, 5, 6 and the Wave 4 page-migration playbook are all substantially complete. This is user-triggered — the orchestrator that produced this document cannot run it.
2. **Sign off on the Decisions table** (section (b)) with the named people. It now covers the original Wave 1 decisions (NET price semantics, Altgold VAT treatment, invoice retention periods, allergy consent wording) plus the newer cross-cutting ones added this pass: Kundeninfo "ticked photos win", repair costs billed net, the outbox inline-vs-worker default, order numbers via the jobs spine, the media `customer_visible` flag, and the legacy-list-fallback-on-`offset` API contract (now confirmed applied uniformly) — plus the still-open fact that Auftragsnummer and repair-intake signature capture were both explicitly *not* built despite being named as "yes" decisions (D-12) or expected features.
3. **Get the outstanding adviser sign-offs** named throughout the Decisions table and the GDPR ops item: Steuerberater (DATEV account mapping, Altgold VAT treatment, invoice/Altgold retention periods, BE-14 rounding), lawyer/Anna (allergy-consent wording, D-13, GDPR-14/15), and Datenschutzberater (the PHOTO_USE-consent-vs-privacy-notice tension in customer messaging). None of these are code changes — they block go-live regardless of test status.
4. **Run a live restore drill** for the encrypted-backup path (`backup.sh`/`restore.sh`, now including the media archive) — still never exercised end-to-end against a real environment.
5. **Do a screenshot review of the migrated pages** (W4-03: order detail, quotes/invoices, group E, group F, repairs, bench UI, nav/admin/order form) — the playbook's own screenshot loop (1280×800 / 390×844) was never run in any worktree, since no live stack was available to the page-migration agents.
6. Treat the **H-severity open follow-ups** as blockers for any production cutover, not backlog: the pre-go-live `Order.price` data review for pre-NET-semantics orders, the order-lifecycle migration never run on PostgreSQL, E7/E8 (recipient confirmation and SMTP TLS) in customer messaging, W5-06 (column encryption), and the restore drill in item 4 above.
7. The full findings register and master fix plan now distinguish `fixed`, `partial: <what's left>`, and `open` — re-run this same method (reports first, commits second, never invent a status) after any further wave lands.
8. A fix-item report (`fix-w7-hygiene-backend.md`) documented declining a mid-task message purporting to be "the coordinator" asking it to expand scope — worth a quick human read of that report as a sanity check on the multi-agent process itself, not because anything appears to have gone wrong.
