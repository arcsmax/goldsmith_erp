# Master Fix Plan: audit 2026-09-25

- **Baseline:** `main` @ `73fff19`. Green: 1805 backend tests pass (6 skipped, 1 xfailed), 485 frontend tests pass; mypy (under a 96-module baseline), black, isort, bandit and `tsc --noEmit` exit 0. Backend line coverage 68%.
- **Inputs:** the eight reviews in this folder, the three verifier reports (62 confirmed, 1 partial, 0 refuted), and [FINDINGS-REGISTER.md](FINDINGS-REGISTER.md) (212 findings).
- **Output of this plan:** 83 fix items in 7 waves. Every finding in the register maps to exactly one wave; a few findings are split across two items and the register names both.
- **Companion documents:** [00-SUMMARY.md](00-SUMMARY.md) (verdict and decisions), `docs/design/UI-UX-PLAYBOOK.md` (design rules and the migration order Wave 4 follows), [PROGRESS.md](PROGRESS.md) (dated changelog, decisions taken, open follow-ups, how to verify locally).
- **Integration branch:** `audit/2026-09-fixes` (created off `main` @ `73fff19`, ~21 fix branches merged in as of 2026-09-25). **Wave 1 is complete except the items marked `partial` below** (W1-04, W1-05, W1-07, W1-08, W1-10, W1-12, W1-14, W1-15, W1-18); every other Wave 1 item is `done`. Wave 2 has landed only for W2-13 (partial) and W2-15 (done); W2-01, W2-02, W2-03, W2-05 and W2-07 have agents still running (`in progress`); the rest of Wave 2 has not started. Wave 5 has W5-01, W5-02 and W5-03 `in progress`; the rest of Wave 5 has not started. Waves 3, 4, 6 and 7 have not started except for a few findings fixed as side effects of Wave 1/2 work (tracked in the findings register, not below, since this section only covers W1/W2/W5 status per the plan's own scope).

---

## 0. How to use this plan

**Branching model.**
1. Create the integration branch once: `git switch -c audit/2026-09-fixes main && git push -u origin audit/2026-09-fixes`.
2. Each fix item is done by one agent in its own worktree, on a branch named `fix/<item-id>-<slug>` (for example `fix/w1-06-invoice-guards`) cut from the current tip of `audit/2026-09-fixes`.
3. The item is merged into `audit/2026-09-fixes` (squash or rebase, the owner's choice) only after its acceptance command exits 0 and its review is APPROVED. `main` receives the integration branch at the checkpoints in section 5, not item by item.
4. Items marked "serialize" in section 2 are never in flight at the same time as another item that touches the same file. CLAUDE.md rule: **never parallelize migrations, `main.py`, `db/models.py`, `types.ts`, `package.json`**. Alembic migrations are created one at a time on the integration tip, so the chain stays linear with a single head.

**Per item, the agent must:**
1. Read the source findings in the review files (IDs in the item row) and the packet (section 3 for Wave 1).
2. Write the tests first (TDD). Run them and record that they fail for the right reason.
3. Implement the minimum that makes them pass, following CLAUDE.md: async services taking `AsyncSession` first, Pydantic validation on all input, `selectinload()` for relationships, `@require_permission` on every new endpoint, audit logging for new models and financial reads, no PII in logs.
4. End with the item's acceptance command and **paste the command and its exit code** into the PR description. An item without a recorded exit code is not done.
5. Run the standard gates for what it touched:
   - Backend: `poetry run pytest -q` (from the repo root; running from `src/` collects 0 tests because `testpaths=["tests"]`), then `cd src && poetry run mypy goldsmith_erp/ --ignore-missing-imports && poetry run black --check goldsmith_erp/ && poetry run isort --check-only goldsmith_erp/ && poetry run bandit -r goldsmith_erp/ -c ../pyproject.toml`.
   - PostgreSQL paths (migrations, partial indexes, `FOR UPDATE`, tz binding): `TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test poetry run pytest -q tests/integration/<file>`, plus an upgrade/downgrade/upgrade round trip (`poetry run alembic upgrade head && poetry run alembic downgrade -1 && poetry run alembic upgrade head`) against a scratch PG database. SQLite cannot run this migration chain (03 §commands).
   - Frontend: `cd frontend && yarn vitest run <path>` then `npx tsc --noEmit`. Build with `node node_modules/vite/bin/vite.js build` until FE-25 (`yarn build` exits 127 in this checkout) is resolved.
6. **Adversarial test round** for every item tagged `[money]`, `[auth]` or `[gdpr]`: a second agent that did not write the code tries to break it (wrong role, boundary amounts, concurrent requests, aware vs naive datetimes, erasure then restore) and adds any failing case as a test. The item merges only when that round finds nothing new or its findings are fixed.
7. Commit with conventional commits (`fix:`, `feat:`, `refactor:`, `test:`, `docs:`, `chore:`), one logical change per commit, and the message body names the finding IDs (for example `fix: reject status changes via PUT /invoices (BE-05)`).
8. When the item lands, update [FINDINGS-REGISTER.md](FINDINGS-REGISTER.md): set `status` to `fixed (<short sha>)` on every row whose fix item is this item. Split findings (two items named) become `fixed` only when both items have landed.

**Hand-off prompt template** (the orchestrator fills the angle brackets and sends it to a fresh agent in its own worktree):

```
You are implementing fix item <W?-??> "<title>" for Goldsmith ERP.
Repo: <worktree path>, branch fix/<item-id>-<slug> cut from audit/2026-09-fixes.
Read first: docs/review/2026-09-25/MASTER-FIX-PLAN.md (section 0 and the row or packet
for <item-id>), the findings <IDs> in docs/review/2026-09-25/<report files>, and CLAUDE.md.
Assumptions you may rely on: <A-n / D-nn defaults from section 6>.
Write the listed tests first and show that they fail. Then implement. Stay inside the
in-scope files; if you must touch another file, stop and ask.
Finish by running the acceptance and verify commands and report each command with its
exit code, the list of files changed, and anything you could not do.
Do not merge. Do not edit the findings register; the orchestrator does that.
```

**Adversarial round checklists** (the second agent writes a failing test for anything it can break):
- `[money]`: amounts at 0.00, 0.005, 0.01 and very large values; VAT rates 19, 7 and 0; gross vs net on every path (quote, order, invoice, Altgold, DATEV); two concurrent requests on the same document; retries of the same request (idempotency); a user role that should not be allowed to change money; rounding of the sum vs the sum of rounded lines.
- `[auth]`: every role (ADMIN, GOLDSMITH, VIEWER, inactive user, revoked token, no cookie) against every new or changed route; object ownership (another user's entry); privilege change through a generic update endpoint (the BE-05 pattern); proxy headers from an untrusted peer.
- `[gdpr]`: data in logs (caplog search for a sentinel name or email); data in exports (Art. 15) and after erasure (Art. 17); what survives in files, caches and backups; role projection of every response field; consent missing, withdrawn, or of the wrong purpose.

**Where decisions are needed**, the plan states the assumption it proceeds on and the alternative (section 6). An agent that finds the assumption contradicted by code or by the owner stops and reports; it does not pick a third option.

---

## 1. Wave definitions

| Wave | Name | Rule | Findings | Items |
|---|---|---|---|---|
| 1 | Stop the bleeding | CRITICAL and HIGH correctness, security and legal findings with S or M effort, plus lower-severity findings that share their files | 60 | 20 |
| 2 | Make the product work for the goal | The domain top-15 (05 §F) and the frontend flow items: photos, repair updates, dashboard, §14 invoice, quote sending, data carry-through, lifecycle and statuses, hallmarks, gemstones, handover, live updates | 43 | 16 |
| 3 | Platform | Frontend architecture (shell, generated types, TanStack Query, behaviour primitives, forms, ESLint) and backend contract (DomainError, `Page[T]`, server-side lists, lifespan and single-run monitor, Numeric and tz-aware migration) | 23 | 11 |
| 4 | Design system | Every DES item, in the playbook migration order: tokens, contrast, focus and status coverage, then primitives, page migrations, deleting duplicate stylesheets, dark mode | 30 | 10 |
| 5 | Operations, CI, compliance docs | OPS items, encrypted backups and erasure-ledger replay, retention, Art. 15 export, processors, documentation | 30 | 13 |
| 6 | Target architecture | Outbox and worker, CustomerMessage, media assets, jobs spine, model modularisation, feedback channel phase 1 and the optional token status page with its GDPR preconditions (07 §E, E1 to E18) | 10 | 7 |
| 7 | Backlog | MEDIUM product gaps outside the top 15, and LOW hygiene | 16 | 6 |

**Deviations from the wave policy, with reasons:**
- GDPR-10 is fixed in Wave 1 (W1-20) together with SEC-05: same file (`middleware/logging.py`), same fix.
- GDPR-13 is fixed in Wave 1 (W1-12): it is in `notification_service.py`, which W1-12 rewrites to stop the customer-email loop.
- OPS-15 (document `AUTH_REVOCATION_FAIL_CLOSED`) and SEC-F2 (nginx body size) ride with W1-02 because W1-02 owns `.env.example` and `frontend/nginx.conf`.
- HIGH findings outside Wave 1 are there because the policy places them in a later wave or because they are L effort: ARCH-01/BE-06, FE-05, FE-08, FE-13, DOM-H gaps (Wave 2, product); ARCH-03, ARCH-04, BE-14, FE-06 (Wave 3, platform; BE-14 is L); OPS-06, GDPR-05 to GDPR-08 (Wave 5); ARCH-02, ARCH-05, DOM-29 (Wave 6, L or dependent on the portal decision); DES HIGH items (Wave 4).
- OPS-06 stays in Wave 5 per policy. Its only critical alert (anyio 4.11.0, fix 4.14.2) is a one-line bump; section 6 D-17 asks the owner whether to pull it into Wave 1.
- ARCH-04 is split: the advisory lock and lifespan are W3-10; the durable outbox is W6-01. Wave 1 does not depend on either, because W1-12 makes reminder dedup race-proof with a unique key.

---

## 2. Fix items per wave

Legend: `[money]`, `[auth]`, `[gdpr]` tag items that need the adversarial round. "Serialize" names the shared file. Effort S (under a day), M (1 to 3 days), L (more than 3 days).

### Wave 1: Stop the bleeding

| Item | Title | Findings | Files likely touched | Effort | Depends on | Parallel-safe with / serialize | Acceptance | Implementation note |
|---|---|---|---|---|---|---|---|---|
| W1-01 `[auth]` | Reject placeholder secrets; bind dev stack to loopback | SEC-02, SEC-08 | `src/goldsmith_erp/core/config.py`, `podman-compose.yml`, `docker-compose.yml`, `README.md`, `tests/unit/test_config.py` | S | none | serialize: `core/config.py` (W1-03 after) | `poetry run pytest -q tests/unit/test_config.py` exit 0 | `model_validator(mode="after")` rejects the `.env.example` placeholder for SECRET_KEY and ANONYMIZATION_SALT when `DEBUG=False` (the field validator cannot see DEBUG). Verifier showed the salt placeholder boots with no warning at all. Publish dev Redis/backend on `127.0.0.1` only; README states the dev stack must never hold real data. |
| W1-02 `[auth]` | Bootable, hardened production config | SEC-F1, SEC-03, SEC-06, SEC-F2, OPS-15 | `setup.sh`, `.env.example`, `podman-compose.prod.yml`, `frontend/nginx.conf`, `deploy/Caddyfile`, `src/goldsmith_erp/models/material.py`, `src/goldsmith_erp/api/routers/theme.py` | M | none | parallel with all Wave 1 code items; serialize: `podman-compose.prod.yml` (W1-03 after) | scratch `bash setup.sh` then `Settings()` boots from the generated `.env.production` (exit 0); `poetry run pytest -q tests/unit/test_url_validation.py` exit 0 | setup.sh writes `ANONYMIZATION_SALT`, drops `ACCESS_TOKEN_EXPIRE_MINUTES=10080`; `.env.example` 30 min and documents `AUTH_REVOCATION_FAIL_CLOSED`; Redis `noeviction` so the revocation list cannot be evicted; nginx `add_header ... always` CSP with the inline theme-script hash, X-Frame-Options, nosniff, Referrer-Policy, HSTS, `client_max_body_size 10m`; `webshop_url`/`logo_url` must match `^https?://`. |
| W1-03 `[auth]` | Real client IP for rate limits; portal behind a flag; login timing | SEC-04, SEC-10, SEC-17 | `api/routers/auth.py`, `api/routers/customer_portal.py`, `middleware/rate_limiting.py`, `middleware/auth_required.py`, `core/config.py`, `main.py`, `podman-compose.prod.yml` (uvicorn flags) | S | W1-01, W1-02 | serialize: `main.py`, `core/config.py` | `poetry run pytest -q tests/unit/test_rate_limit_keys.py tests/integration/test_portal.py tests/unit/test_auth_security.py` exit 0 | `--proxy-headers --forwarded-allow-ips=<compose subnet>`; key functions use `get_real_ip`; slowapi `storage_uri=settings.REDIS_URL`; `PORTAL_ENABLED=False` default unmounts the portal router and its public-path whitelist; unknown-email login verifies against a dummy bcrypt hash. |
| W1-04 `[auth]` `[gdpr]` | Role projection sweep: financial and design data | SEC-01, SEC-09, GDPR-03, GDPR-04, GDPR-09 (gating and audit part), SEC-15 | `core/permissions.py`, `api/routers/{analytics,repairs,materials,metal_inventory,customers,photos,orders,valuations}.py`, `models/{repair,material,metal_inventory,order}.py`, `middleware/audit_logging.py` | M | none | serialize: `api/routers/customers.py` (W1-05, W1-10 after) | `poetry run pytest -q tests/integration/test_viewer_response_denylist.py tests/integration/test_order_viewer_projection.py tests/integration/test_financial_audit.py` exit 0 | Add `FINANCIAL_VIEW` and `DESIGN_VIEW` (ADMIN, GOLDSMITH); remove REPORTS_VIEW from VIEWER; reuse the `_FINANCIAL_FIELDS` projection pattern from `orders.py` for repairs, materials (also nested `OrderRead.materials[].unit_price`), metal purchases, customer stats/top; strip `description`/`special_instructions` for non-design roles; gate photo routes with DESIGN_VIEW; valuation PDF with `VALUATION_EXPORT`; register quotes, repairs, metal-inventory, metal-prices, analytics in `_RESOURCE_ROUTES`. |
| W1-05 `[gdpr]` | Consent store; allergies behind explicit consent | GDPR-02, GDPR-11, DOM-07 | `db/models.py`, new Alembic migration, `models/customer.py`, `services/customer_service.py`, `api/routers/customers.py`, `frontend/src/components/CustomerFormModal.tsx`, `frontend/src/api/customers.ts`, `frontend/src/types.ts` | M | W1-04 | serialize: `db/models.py`, migration, `types.ts`, `customers.py` | `poetry run pytest -q tests/unit/test_customer_consent.py tests/integration/test_customer_consent_api.py` and `cd frontend && yarn vitest run src/components/CustomerFormModal.test.tsx` exit 0 | `customer_consents` (customer_id, purpose, granted_at, withdrawn_at, method, wording_version, evidence). Writing `allergies` or health no-gos requires an active `health_allergy` consent; reads limited to ADMIN/GOLDSMITH. Consents are included in Art. 15 export and scrubbed on erasure. Birthday use gated on `birthday_greetings`. |
| W1-06 `[money]` `[auth]` | Invoice status only via actions; tz-safe dates | BE-05, BE-04 | `models/invoice.py`, `models/validators.py`, `services/invoice_service.py`, `api/routers/invoices.py` (new `/send`), `frontend/src/pages/InvoicesPage.tsx` (call sites), `tests/unit/test_invoice_service.py` | S | none | serialize: `services/invoice_service.py` (W1-07 after) | `poetry run pytest -q tests/unit/test_invoice_service.py tests/integration/test_invoice_status_authz.py` exit 0 | Remove `status` from `InvoiceUpdate` (mirrors `quote_service.py:586-591`). Add `POST /invoices/{id}/send` (DRAFT to SENT, INVOICE_EDIT) because the existing `test_draft_to_sent_via_update` relies on PUT for that. A shared `UtcNaiveDatetime` annotated type (pattern from `models/repair.py:20-31`) normalises aware input. |
| W1-07 `[money]` | Invoice amounts from the agreed price; safe quote conversion | BE-01, BE-02, BE-17, BE-25 | `services/quote_service.py`, `services/invoice_service.py`, new `services/line_item_builder.py`, `docs/adr/0001-order-price-semantics.md` | M | W1-06 | serialize: `invoice_service.py`, `quote_service.py` (W1-08, W2-05 after) | `poetry run pytest -q tests/integration/test_life_of_a_ring.py tests/unit/test_invoice_amounts.py tests/unit/test_quote_convert.py` exit 0 | Assumption A1 (section 6 D-01): `Order.price` is the gross Endpreis. Invoice lines come from the converted quote's lines, else from `order.price` split into net and VAT so `invoice.total == order.price`, else cost x (1 + margin). Convert confirms the linked order instead of creating a new one, enforces the same customer, rejects after `valid_until`, locks with `with_for_update`, and creates unlinked orders as DRAFT. One `LineItemBuilder` reads `settings.DEFAULT_HOURLY_RATE`. |
| W1-08 `[money]` | Altgold: correct valuation, immutable after signing, credit after tax | BE-03, BE-11, DOM-19, DOM-20 | `db/models.py`, migration, `models/scrap_gold.py`, `services/scrap_gold_service.py`, `api/routers/scrap_gold.py`, `services/invoice_service.py`, `models/invoice.py`, `services/pdf_service.py`, `frontend/src/components/scrap-gold/ScrapGoldTab.tsx`, `frontend/src/api/scrap-gold.ts`, `frontend/src/types.ts` | M | W1-07 | serialize: `db/models.py`, migration, `types.ts`, `invoice_service.py` | `poetry run pytest -q tests/unit/test_scrap_gold_valuation.py tests/unit/test_invoice_scrap_gold_credit.py` and `cd frontend && yarn vitest run src/components/scrap-gold` exit 0 | Assumption A3 (D-02): the credit is a post-tax deduction (Zahlbetrag = gross total minus Ankaufswert) stored in its own invoice field, not a negative net line. One alloy enum shared by order, scrap and hallmark; unknown alloys 422 (no silent 0.0); per-metal fine grams each at its own price; configurable Ankaufsabschlag %; 409 on any change after SIGNED; `calculate_and_update` never demotes status; `UNIQUE(scrap_gold.order_id)`. |
| W1-09 `[money]` | DATEV/lexoffice export: only issued invoices, account per VAT rate | BE-13 | `services/accounting_export_service.py`, `api/routers/invoices.py` (export handler), `core/config.py` (account map) | S | none | parallel with W1-06/07/08; serialize: `core/config.py` with W1-01/W1-03 | `poetry run pytest -q tests/unit/test_accounting_export.py` exit 0 | Default filter SENT/PAID/OVERDUE; account chosen from a `tax_rate` map in settings (default `19 -> 8400`; the export refuses a rate with no mapped account until the Steuerberater supplies it); stornos as reversal bookings; created date computed per call. No test file exists today for this service (06 §D). |
| W1-10 `[money]` `[gdpr]` | Immutable invoice snapshot; erasure keeps statutory records | GDPR-01, BE-23 | `db/models.py`, migration with backfill, `services/invoice_service.py`, `api/routers/invoices.py` (PDF), `services/pdf_service.py`, `services/customer_service.py` (`SCRUBBABLE_FIELDS`), `services/file_erasure_service.py`, `api/routers/customers.py` (gdpr-erase response) | M | W1-08, W1-05 | serialize: `db/models.py`, migration, `invoice_service.py`, `customers.py` | `TEST_DATABASE_URL=... poetry run pytest -q tests/integration/test_invoice_snapshot.py tests/integration/test_gdpr_erasure_keeps_statutory_records.py tests/unit/test_gdpr_customer_erasure.py` exit 0 | Assumption A4 (D-06): JSON snapshot (recipient, seller, lines, totals, service date) at creation, frozen PDF plus SHA-256 at SENT, write-once. Remove invoice, line-item, accepted-quote and Altgold columns from `SCRUBBABLE_FIELDS`; mark them restricted (ADMIN-only access, Art. 18) with deletion scheduled at the end of the retention period; keep Altgold receipt PDFs and signatures. Erasure response cites Art. 17(3)(b) for retained categories. |
| W1-11 `[money]` | Metal consumption accumulates; AVERAGE draws across batches | BE-07, BE-08 | `services/metal_inventory_service.py`, `services/cost_calculation_service.py` | S | none | parallel with invoice chain (do not touch `invoice_service.py`) | `poetry run pytest -q tests/unit/test_metal_inventory_service.py` and on PG `tests/integration/test_concurrent_metal_consumption.py` exit 0 | Order material cost and weight become `SUM` over `material_usage` rows (or increment inside the locked transaction). AVERAGE draws physically FIFO across batches while pricing at the weighted average. Cost calculation uses recorded usage when present and previews only unconsumed estimates. |
| W1-12 `[gdpr]` | Stop the customer-email loop; one message per event | BE-09, DOM-10, BE-21, GDPR-13, VER-01, VER-02 | `services/notification_service.py`, `services/system_monitor.py`, `services/email_service.py`, `services/repair_service.py`, `db/models.py`, migration (dedupe key), `templates/email/*.html` | M | none | serialize: `db/models.py`, migration | `poetry run pytest -q tests/unit/test_notification_dedup.py tests/unit/test_repair_ready_notifications.py` and on PG `tests/integration/test_reminder_single_email.py` exit 0 | Dedup on (order, type, Europe/Berlin day) with a UNIQUE dedupe key, regardless of `is_read`. Customer email is sent once per order event, never once per staff row, and is recorded as a CustomerUpdate row visible in Kundeninfo (assumption A5, D-07). Pass the real fitting date. Build customer emails only from customer-facing fields. Monitor uses a fresh session per step. `_notify_admins_repair_ready` filters ADMIN/GOLDSMITH and goes through `create_notification` so it publishes. |
| W1-13 | Customer portal route outside the staff providers | FE-01 | `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/pages/CustomerPortalPage.test.tsx`, new `frontend/e2e/portal-unauthenticated.spec.ts` | S | none | parallel with W1-14, W1-15 | `cd frontend && yarn vitest run src/pages/CustomerPortalPage.test.tsx src/api` and `npx playwright test e2e/portal-unauthenticated.spec.ts` exit 0 | Mount `/portal` before `<AuthProvider>`; the interceptor never hard-redirects on public paths. When the backend portal is disabled (W1-03), the page shows "Das Kundenportal ist derzeit nicht aktiviert." instead of an error. |
| W1-14 `[gdpr]` | Honest bench session: per-user lifecycle, no fake pause, no PII cache | FE-07, FE-10, FE-11, FE-19, FE-09 | `frontend/src/contexts/TimeTrackingContext.tsx`, `frontend/src/contexts/AuthContext.tsx`, `frontend/src/components/TimerWidget.tsx`, `frontend/src/components/OfflineIndicator.tsx`, `frontend/vite.config.ts` | S | none | parallel with W1-13, W1-15 | `cd frontend && yarn vitest run src/contexts src/components/TimerWidget.test.tsx src/components/OfflineIndicator.test.tsx` exit 0; built `dist/sw.js` contains no `/api/v1/orders` or `/api/v1/materials` runtime route | Key initialisation on `user?.id`; logout stops polling, clears `running_time_entry`, `scanner_last_activity_id`, `user`, and calls `caches.delete` for API caches. Remove the Pause button (server-side pause is W2-14). Route all stops through the context. Offline copy: "Offline: Änderungen werden nicht gespeichert"; submit buttons disabled offline. Activities `NetworkFirst`. |
| W1-15 | QR bench flow works on a fresh device; entity-type aware actions | FE-02, FE-03, FE-04 | `frontend/src/components/scanner/ScanOverlay.tsx`, `frontend/src/components/scanner/ActionHandlers.ts` (path per repo), `QuickActionModalV2.tsx`, `frontend/src/test/{ActionHandlers,QuickActionModalV2,Slice11PrimaryScenario,ScanOverlay}.test.*` | M | none | parallel with W1-13, W1-14 | `cd frontend && yarn vitest run src/test/ActionHandlers.test.ts src/test/QuickActionModalV2.test.tsx src/test/Slice11PrimaryScenario.test.tsx src/test/ScanOverlay.test.tsx` exit 0 | Activity step in QuickAction (top 5 from `activitiesApi.getMostUsed` as big buttons). Remove the localStorage pre-seed from tests. Switch on `entity_type` in every handler; hide `start_timer` for repairs. Filter action IDs with no handler; fix routes for metal purchases and materials. Order deep-link params are read in W2-01. |
| W1-16 `[money]` | Estimator cost consistent with the shown median | BE-10 | `src/goldsmith_erp/ml/labor_estimator.py`, `services/estimator_service.py` | S | none | parallel-safe | `poetry run pytest -q tests/unit/test_labor_estimator.py tests/unit/test_estimator_service.py` exit 0 | Assumption A6 (D-09): price at `hours_p50 x blended rate`; suggested activities are zero-filled across the matched set and include only activities in at least 50% of orders; assert the suggested hours sum to about `hours_p50`. |
| W1-17 | One running timer per user; sane time edits; owner checks | BE-12, BE-18, SEC-13 | migration (partial unique index), `services/time_tracking_service.py`, `models/time_entry.py`, `api/routers/time_tracking.py` | S | none | serialize: migration | `poetry run pytest -q tests/unit/test_time_tracking_service.py tests/integration/test_time_tracking_permissions.py` and on PG `tests/integration/test_one_running_timer.py` exit 0 | `CREATE UNIQUE INDEX uq_time_entries_one_running ON time_entries(user_id) WHERE end_time IS NULL` (plus SQLite equivalent); IntegrityError maps to 409; `.first()` defensively. `TimeEntryUpdate` validates end > start and at most 24 h; rejects explicit `duration_minutes` with an end time; a PUT that sets `end_time` on a running entry goes through `stop_time_entry`. Owner or TIME_VIEW_ALL/ADMIN on stop, PUT, interruptions. |
| W1-18 `[gdpr]` | Escaped labels, bounded image decoding, EXIF stripped | SEC-07, SEC-18, GDPR-19 | `services/label_service.py`, `middleware/security_headers.py` (CSP hash for the print script), `services/image_validation.py`, `services/photo_service.py`, `services/repair_photo_service.py`, `services/consultation_photo_service.py`, `core/config.py` (label name setting) | S | none | serialize: `core/config.py` | `poetry run pytest -q tests/unit/test_label_service.py tests/unit/test_image_validation.py` exit 0 | Render labels through a Jinja env with `autoescape=True` or `html.escape` every value; allow the print script by CSP hash (no `'unsafe-inline'`, no `main.py` change). `Image.MAX_IMAGE_PIXELS = 40_000_000`, DecompressionBombWarning is an error, decoding in a thread pool. Strip EXIF from the stored original. Labels print initials unless a setting enables full names. |
| W1-19 `[auth]` | Credential changes need the current password; roles assignable by ADMIN | SEC-11, SEC-F6 | `api/routers/users.py`, `models/user.py`, `services/user_service.py`, `services/email_service.py`, `frontend/src/pages/UsersPage.tsx`, `frontend/src/api/users.ts` | S | none | parallel-safe | `poetry run pytest -q tests/integration/test_users_me_reauth.py tests/integration/test_role_assignment.py` exit 0 | `current_password` required for any email or password change (bcrypt verify), audit row, notice to the old address. ADMIN-only role field on the admin update endpoint, audit-logged, cannot demote the last admin. UsersPage gets a role select. |
| W1-20 `[gdpr]` | No PII or tokens in request logs | SEC-05, GDPR-10 | `src/goldsmith_erp/middleware/logging.py`, `tests/unit/test_logging_redaction.py` | S | none | parallel-safe | `poetry run pytest -q tests/unit/test_logging_redaction.py` exit 0 | Log `request.url.path` plus an allow-list of query keys (for example `limit`, `offset`, `status`); mask `/portal/status/{token}` as `/portal/status/***`. |

**Status (as of 2026-09-25, integration branch `audit/2026-09-fixes`).** The table has no room for a Status column, so it is recorded here, one line per item; see [PROGRESS.md](PROGRESS.md) for the evidence behind each line.

- **W1-01** — done. SEC-02, SEC-08 (`948ddf5`; SEC-02's placeholder-bypass loophole found by the adversarial round closed by `e121bfb`).
- **W1-02** — done. SEC-F1, SEC-03, SEC-06, SEC-F2, OPS-15 (`29fab2f`, `4518e2f`, `948ddf5`).
- **W1-03** — done. SEC-04, SEC-10, SEC-17 (`b315d25`, `8940316`, `ec46dd6`).
- **W1-04** — partial (financial-read audit logging for repairs, materials and metal-inventory reads not added; SEC-15 stays open). SEC-01, SEC-09, GDPR-03, GDPR-04, GDPR-09's gating done (`fd15807`, `90fe1b5`, `083b1f9`).
- **W1-05** — partial (create-with-allergies for a brand-new customer isn't fully wired — the consent can't be granted before the customer has an id; photo_use/marketing/email_contact consents are recorded but nothing enforces them yet). GDPR-02, GDPR-11, DOM-07's capture UI done (`996703f`, `f976482`).
- **W1-06** — done. BE-05, BE-04 (`41c1a4f`).
- **W1-07** — partial (BE-25's duplicate, cost-based quote line builder was not consolidated into the planned shared `LineItemBuilder`; the adversarial round found a zero-price quote conversion, a concurrent double-conversion race and an unrechecked customer-reassignment gap, all routed to W2-05). BE-01, BE-02 done (`6cecd9e`, `41c1a4f`).
- **W1-08** — partial (DOM-20's per-metal gram breakdown, `total_fine_gold_g` still aggregates across metals, needs a schema change; out of this item's scope). BE-03, BE-11, DOM-19 done (`41c1a4f`, `33ddd44`, `17adb24`, `9639f64`).
- **W1-09** — done. BE-13 (`4e7b77f`); 7%/0% VAT-rate DATEV accounts still await the Steuerberater's mapping (D-02), and storno detection is a conservative heuristic until W1-10's `issued_at`/`cancelled_at` data exists.
- **W1-10** — partial (§14 UStG seller fields deferred to W2-04; Art. 15 export of the snapshot deferred to W5-08; the retention sweep itself is W5-07). GDPR-01, BE-23's live-customer-render bug fixed (`996703f`, `1230e8f`).
- **W1-11** — done. BE-07, BE-08 (`d07b769`); the PG-only concurrency test was not executed live this session (same locking code, unchanged).
- **W1-12** — partial (BE-21's shared-session-per-monitor-scan not fixed; no per-order opt-out; the adversarial round's C1.2 finding — a second completion after reopening an order sends no second mail — is routed to W2-02). BE-09, DOM-10, GDPR-13, VER-01, VER-02 done (`4fb66d7`, `22612fb`, `9af6d05`).
- **W1-13** — done. FE-01 (`405bf6c`).
- **W1-14** — partial (FE-09's "disable submit buttons while offline" half needs per-form wiring across pages out of this item's scope). FE-07, FE-10, FE-11, FE-19 done (`775c3c0`, `4208877`, `1d57dc8`).
- **W1-15** — partial (FE-04's unhandled quick-action IDs and unread `?action=`/`?edit=` deep-link params are not done — overlaps W2-01). FE-02, FE-03 done (`3cf39de`, `d1c82a3`).
- **W1-16** — done. BE-10 (`27ea4f4`).
- **W1-17** — done. BE-12, BE-18, SEC-13 (`d5f4b22`); the PG two-session race test was not written.
- **W1-18** — partial (F-3's label print-script CSP block is still in place, deliberately not relaxed; the "labels print initials unless a setting enables full names" behaviour was not implemented; `api/routers/materials.py`'s separate photo-upload path was not hardened). SEC-18, GDPR-19's EXIF stripping done (`77c7a35`).
- **W1-19** — done. SEC-11, SEC-F6 (`467bc3b`, `61dc5a3`); the adversarial round's admin-self-edit reauthentication bypass (B3) closed by `e121bfb`.
- **W1-20** — done. SEC-05, GDPR-10 (`b315d25`, `4518e2f`, `54c0815`).

**Wave 1 exit criteria (before CP-1):** all 20 items merged; the adversarial rounds for the 17 tagged items closed; `poetry run pytest -q`, the PG integration job, `migration-smoke`, Vitest, `tsc` and the Playwright specs green on the integration tip; register rows for Wave 1 set to fixed; a scratch production install from `setup.sh` boots and serves the SPA with security headers; `EMAIL_NOTIFICATIONS_ENABLED=true` on the demo stack for one simulated day produces one pickup email per order.

### Wave 2: Make the product work for the goal

| Item | Title | Findings | Files likely touched | Effort | Depends on | Parallel-safe with / serialize | Acceptance | Implementation note |
|---|---|---|---|---|---|---|---|---|
| W2-01 | Order photo upload and scanner deep links | FE-13, DOM-01 (and FE-04 deep-link part) | `frontend/src/api/photos.ts`, `frontend/src/pages/OrderDetailPage.tsx`, `frontend/src/components/PhotoCompare.tsx`, `frontend/src/pages/CustomerDetailPage.tsx`, `api/routers/orders.py` (`first_photo_id` in list) | M | W1-02 (body size), W1-04 (DESIGN_VIEW), W1-15 | serialize: `OrderDetailPage.tsx` (W2-08 after) | `cd frontend && yarn vitest run src/test/OrderDetailPage.test.tsx` exit 0: upload posts to `POST /orders/{id}/photos`; `?action=take-photo` opens the camera input; thumbnails use `/photos/{id}/thumbnail` | Copy the repair upload (`capture="environment"`). Stable IDs instead of `Math.random()`. Implement `?action=` and `?edit=` on OrderDetailPage (open tab or modal). Fix the CustomerDetailPage URL and N+1. Domain DoD: scanner "Foto" to Fotos tab to Kundeninfo in 3 taps. |
| W2-02 | Repairs get customer updates; truthful notified timestamp | DOM-12 (and VFD new issue 3) | `api/routers/customer_updates.py` or `api/routers/repairs.py`, `services/customer_update_service.py`, `services/repair_service.py`, `frontend/src/pages/RepairDetailPage.tsx` | S | W1-12 | serialize: `repair_service.py` with W2-12 | `poetry run pytest -q tests/integration/test_repair_updates.py` exit 0: READY creates a ready_for_pickup draft; `customer_notified_at == sent_at` only after a real send | Add `/repairs/{id}/updates` (the service already supports it). One tap sends the draft. Remove the unconditional `customer_notified_at: now`. |
| W2-03 | "Heute" dashboard: overdue first, customer-pending lanes, repairs included | FE-05, DOM-14, DOM-15, DOM-15b, DOM-15c | new `api/routers/dashboard.py`, new `services/dashboard_service.py`, `main.py` (router mount), `frontend/src/pages/DashboardPage.tsx`, `frontend/src/components/dashboard/*` | M | W2-07 (statuses), W2-02 | serialize: `main.py` | `poetry run pytest -q tests/integration/test_dashboard_summary.py` (150 seeded orders; counts exceed 100) and `cd frontend && yarn vitest run src/pages/DashboardPage.test.tsx` (`buildTodoList`: overdue is urgent and first; load failure shows an error with retry) exit 0 | Server-side summary: counts plus top N per bucket (Überfällig, Heute, Wartet auf Kunde, Abholbereit, offene Rechnungen) spanning orders and repairs; each row links to its next action. ADMIN sees the same work lanes (Anne's likely role). |
| W2-04 `[money]` | §14 UStG invoice, workshop settings, Storno, safe numbering | DOM-24, DOM-24b, BE-16 | `db/models.py`, migration (workshop settings, per-year counters, storno link), `services/invoice_service.py`, `services/pdf_service.py`, `api/routers/invoices.py`, `frontend/src/pages/AdminSystemPage.tsx` | M | W1-10 | serialize: `db/models.py`, migration, `invoice_service.py` | `poetry run pytest -q tests/unit/test_invoice_pdf_fields.py` (PDF has seller address, St-Nr or USt-IdNr, Leistungsdatum, number) and on PG `tests/integration/test_invoice_numbering.py` (concurrent creates get distinct numbers; RE-2026-10000 follows 9999; Berlin year boundary) exit 0 | Workshop settings (address, tax number, bank, Kleinunternehmer flag) feed the W1-10 seller snapshot. Counter table with `SELECT ... FOR UPDATE`, year in Europe/Berlin, partial unique `invoices(order_id) WHERE status <> 'cancelled'`. Issued invoices locked; "Stornieren" creates a Stornorechnung with its own number and a link. Same counter for RE/KV/WG/REP and an Auftragsnummer if D-12 says yes. |
| W2-05 `[money]` | Quote Versenden sends; consultation to quote to order carries data | DOM-11, DOM-11b, DOM-11d, DOM-03, FE-18 | `services/quote_service.py`, `api/routers/quotes.py`, `services/email_service.py`, `services/consultation_service.py`, `frontend/src/pages/QuotesPage.tsx`, consultation convert UI | M | W1-07 | serialize: `quote_service.py` | `poetry run pytest -q tests/integration/test_quote_send.py tests/unit/test_consultation_convert.py` exit 0: consultation with occasion date, ring size and "585 Gelbgold" converts with deadline, ring size, alloy, order_type and photos | Versenden emails the PDF via `EmailService.send_quote` when SMTP is set, else records PDF_MANUAL. Quote lines copy into the order Soll. Approval requires a response method (in person/signature, email, phone). QuotesPage reads `?order_id&customer_id` and opens the modal pre-filled. |
| W2-06 | Order intake: order type, single alloy picker, gemstones | DOM-04, DOM-05, DOM-06, DOM-09 | `frontend/src/components/orders/OrderFormModal.tsx`, new `api/routers/gemstones.py`, new `services/gemstone_service.py`, `main.py`, `db/models.py` (Gemstone: Fassungsart, customer stone), migration, `frontend/src/types.ts`, `services/pdf_service.py` | M | W2-05 | serialize: `main.py`, `db/models.py`, migration, `types.ts` | `cd frontend && yarn vitest run src/components/orders/OrderFormModal.test.tsx` ("Ohrring" does not demand ring size; `order_type` saved; one "Legierung & Farbe" picker sets both fields) and `poetry run pytest -q tests/integration/test_gemstones.py` exit 0 | Ring size driven by `order_type == ring`. Picker values like "585 Gelbgold", "750 Weissgold", "Pd 950". Stones: type, count, ct, colour/clarity, shape, Fassungsart (Zargen, Krappen, Kanal, Pavee, Spann, Unsichtbar), Kundenstein flag; printed on quote, invoice, valuation. |
| W2-07 | Order lifecycle: transition table, history, on-hold and cancelled | ARCH-01, BE-06, DOM-13, DOM-46 | new `services/order_workflow.py`, `services/order_service.py`, `services/scanner_service.py` (advance_status), `db/models.py` (enum, hold reason, resume date), data migration (NEW mapping), `api/routers/orders.py` (`GET /orders/{id}/timeline`) | M | W1-07 | serialize: `db/models.py`, migration | `poetry run pytest -q tests/unit/test_order_workflow.py tests/integration/test_order_timeline.py` exit 0: DELIVERED to IN_PROGRESS is 409; every transition writes an `OrderStatusHistory` row in the same transaction; on_hold leaves deadline alarms | `ALLOWED_TRANSITIONS: dict[OrderStatusEnum, set[OrderStatusEnum]]` (pattern from `repair_service.py:99-113`). Add `on_hold` (reason, expected resume date) and `cancelled`. Migrate `NEW` (reversible, dry-run on a prod dump). One backend source for German status labels. The full lifecycle vs production-stage split waits for W6-04. |
| W2-08 | Order page: 5 tabs, "Weiter" button, real timeline, milestone prompts | DOM-16, DOM-17, DOM-18, DOM-30 | `frontend/src/pages/OrderDetailPage.tsx`, `frontend/src/components/orders/*`, `frontend/src/api/orders.ts` | M | W2-07, W2-01 | serialize: `OrderDetailPage.tsx` | `cd frontend && yarn vitest run src/test/OrderDetailPage.test.tsx` exit 0: 5 tabs with `role="tab"`; Weiter shows only allowed next statuses; moving to fertig offers a pre-filled update with the latest photos | Tabs Überblick, Arbeit, Fotos, Kunde, Geld. Timeline renders status history, handoffs, customer updates and photos. Domain DoD: a tester with gloves on a 10" tablet advances an order and finds its history in under 10 s. |
| W2-09 | Hallmarks: vocabulary from alloy, soft gate, reachable from the order page | DOM-22, DOM-23, DOM-44 | `models/order.py` (`_validate_punzierung_marks`), `services/order_service.py` (guard), `frontend/src/components/qc/PunzierungsCheckModal.tsx`, `OrderDetailPage.tsx` | S | W2-07, W2-08 | serialize: `order_service.py`, `OrderDetailPage.tsx` | `poetry run pytest -q tests/integration/test_punzierung_bypass_enumeration.py tests/unit/test_order_service.py` and `cd frontend && yarn vitest run src/test/PunzierungsCheckModal.test.tsx` exit 0: a 333 order completes with "Feingehalt 333" or "nicht punziert: <Grund>"; a 409 opens the modal | Allowed Feingehalt mark derived from the order's alloy (333, 375, 585, 750, 900, 925, 935, 999, Ag800, Pt950, Pd). Drop `OrderHallmark` from UI plans (D-10). |
| W2-10 | Customers without email | DOM-02 | `db/models.py`, migration (email nullable, partial unique `email_hash WHERE NOT NULL`), `models/customer.py`, `services/customer_service.py`, `services/customer_update_service.py`, `frontend/src/components/CustomerFormModal.tsx`, `frontend/src/types.ts` | M | W1-05 | serialize: `db/models.py`, migration, `types.ts` | `poetry run pytest -q tests/unit/test_customer_service.py tests/integration/test_customer_pii_encryption.py` exit 0: phone-only customer created; updates fall back to PDF_MANUAL | Uniqueness only when an email is present. Blind index unchanged for present emails. |
| W2-11 | Handover report PDF and valuation button | DOM-34, DOM-35 | `services/pdf_service.py` (handover template), `api/routers/orders.py` (handover PDF), `frontend/src/api/valuations.ts`, `OrderDetailPage.tsx` | S | W2-08 | serialize: `OrderDetailPage.tsx`, `pdf_service.py` with W2-04 | `poetry run pytest -q tests/unit/test_pdf_handover.py tests/integration/test_valuations.py` exit 0 | Handover sheet: photo, metal, stones, care text by metal and stone, warranty. "Wertgutachten erstellen" on delivered orders (ADMIN export per W1-04). This is also the Option 2 "Werkstattbericht" from 05 §D. |
| W2-12 | Repair intake at the counter; customer 360 | FE-17, DOM-08, DOM-38 | `frontend/src/pages/RepairsPage.tsx`, `frontend/src/pages/RepairDetailPage.tsx`, `frontend/src/pages/CustomerDetailPage.tsx`, `services/repair_service.py`, `services/pdf_service.py` (Annahmeschein), migration (repair signature) | M | W2-02 | serialize: `repair_service.py`, migration, `pdf_service.py` | `cd frontend && yarn vitest run src/pages/RepairsPage.test.tsx src/pages/CustomerDetailPage.test.tsx` and `poetry run pytest -q tests/integration/test_repairs.py` exit 0 | Reuse `CustomerTypeahead` with inline "Neuer Kunde"; navigate to the new repair; SignatureCanvas and an Annahmeschein PDF (bag number, condition photos, estimate, stone liability clause); customer page lists repairs, consultations, quotes and updates, invoices filtered server-side by `customer_id`. |
| W2-13 | Live updates reach the screens | FE-08, BE-20 | `main.py`, `core/pubsub.py`, `frontend/src/hooks/useWebSocket.ts`, new `frontend/src/contexts/WebSocketProvider.tsx`, `TimeTrackingContext.tsx`, `NotificationBell.tsx` | M | W1-14 | serialize: `main.py` | `poetry run pytest -q tests/integration/test_ws_fanout.py` (publish on `time_tracking_updates` and `order_updates` reaches the user socket) and `cd frontend && yarn vitest run src/contexts` exit 0 | One authenticated socket per user; backend fans `time_tracking_updates` and `order_updates` into it. `publish_event` returns a bool; Redis pool gets connect and read timeouts; the socket closes if its subscriber dies. Messages are invalidation hints for W3-03. |
| W2-14 `[money]` | Interruptions reduce time; actual hours recomputed | BE-19 | `services/time_tracking_service.py`, `services/ml_data_service.py`, `services/order_service.py`, migration (`Interruption.resumed_at`), `frontend/src/components/TimerWidget.tsx` (server pause, optional) | M | W1-17, W1-14 | serialize: migration | `poetry run pytest -q tests/unit/test_time_tracking_service.py tests/integration/test_order_completion_accuracy.py` exit 0: a 3 h entry with a 45 min interruption counts 2.25 h; rework after completion updates `actual_hours` | Resume scan closes the interruption; recompute on every stop or edit. If the owner wants Pause back (D-15), implement it here as an interruption. |
| W2-15 `[money]` | Metal price feed correct and visible | BE-22, DOM-11c | `services/metal_price_service.py`, `services/metal_inventory_service.py`, `frontend/src/components/estimator/EstimatorPanel.tsx` | S | none | parallel-safe | `poetry run pytest -q tests/unit/test_metal_price_service.py` and `cd frontend && yarn vitest run src/components/estimator` exit 0 | Raise when EUR is missing (fallback chain takes over); apply fineness per metal (Pt950 = 0.95 x XPT); do not truncate `price_per_gram` to cents (Numeric in W3-11). Show "Kurs vom <Datum>, Quelle"; red warning on hardcoded defaults. |
| W2-16 `[gdpr]` `[money]` | Altgold Ankaufsbuch and optional ID capture | DOM-21 | `db/models.py`, migration (encrypted ID fields), `models/scrap_gold.py`, `frontend/src/components/scrap-gold/ScrapGoldTab.tsx`, export | M | W1-08, W1-05 | serialize: `db/models.py`, migration | `poetry run pytest -q tests/integration/test_scrap_gold_ankaufsbuch.py` exit 0: above the configured cash threshold ID fields are required; values stored as EncryptedString; export lists purchases | ID type, number (EncryptedString), checked-by; threshold from settings (D-16); 5-year retention per GDPR-01; included in Art. 15 export. |

**Status (as of 2026-09-25).** Only W2-13, W2-15 and (as fix-item metadata) the still-running items below have any evidence; everything else in Wave 2 is unstarted.

- **W2-01** (order photo upload, deep links) — in progress; the fix agent is still running, no report yet.
- **W2-02** (repair customer updates) — in progress; the fix agent is still running, no report yet.
- **W2-03** ("Heute" dashboard) — in progress; the fix agent is still running, no report yet.
- **W2-04** (§14 invoice, Storno, numbering) — open.
- **W2-05** (quote Versenden, data carry-through) — in progress; the fix agent is still running, no report yet. It also inherits the adversarial round's BE-17 gaps (zero-price conversion, concurrent double-conversion, customer-reassignment) from W1-07.
- **W2-06** (order intake: type, alloy, gemstones) — open.
- **W2-07** (order lifecycle, statuses, history) — in progress; the fix agent is still running, no report yet.
- **W2-08** (order page tabs, timeline) — open.
- **W2-09** (hallmarks) — open.
- **W2-10** (customers without email) — open.
- **W2-11** (handover PDF, valuation button) — open.
- **W2-12** (repair intake, customer 360) — open.
- **W2-13** (live updates) — partial. The hub, notifications and time-tracking realtime wiring landed (`c8065f8`, `faa106e`), closing FE-08, BE-20 (partly) and, as a side effect, the adversarial round's CRITICAL D.1 `/ws/orders` price leak. Still open: Dashboard/Orders/OrderDetail/Repairs pages don't yet call `useRefetchOn`, and `repair_updates`, `material_updates`, `consultation_updates`, `metal_price_updates` and `anomaly_alerts` have no subscriber.
- **W2-14** (interruptions reduce time) — open.
- **W2-15** (metal price feed) — done. BE-22, DOM-11c (`60a8289`); minor open item: the estimator's alloy-override input has no debounce.
- **W2-16** (Altgold Ankaufsbuch) — open.

**Wave 2 exit criteria (before CP-2):** each domain top-15 definition of done in 05 §F is demonstrated on the demo stack on a tablet (photo in 3 taps, overdue first, one pickup mail, §14 fields on the PDF, conversion without retyping, on-hold lane, 333 order completable); new endpoints carry `@require_permission`, audit logging and `selectinload`; register rows for Wave 2 set to fixed.

### Wave 3: Platform

| Item | Title | Findings | Files likely touched | Effort | Depends on | Parallel-safe with / serialize | Acceptance | Implementation note |
|---|---|---|---|---|---|---|---|---|
| W3-01 | Public/private shell split; ErrorBoundary that recovers; dead code out | FE-14, FE-22 | `frontend/src/App.tsx`, `frontend/src/components/ErrorBoundary.tsx`, `frontend/vite.config.ts`, `ActiveTimerWidget.tsx`, `OrderList.tsx`, `RegisterPage.tsx` | S | W1-13 | parallel with W3-07..W3-11 | `cd frontend && yarn vitest run src/components/ErrorBoundary.test.tsx` exit 0: chunk-load error reloads once; page boundary resets on `location.key` | `PublicShell` (portal, login) and `PrivateShell` with per-user providers keyed on `user.id`. Lazy `TimeReportsSection`; `sourcemap: 'hidden'`. |
| W3-02 | Generated OpenAPI types with a CI drift gate | ARCH-07, FE-12 | new `scripts/export_openapi.py`, `frontend/src/api/schema.d.ts`, `frontend/src/types.ts`, `frontend/package.json`, `.github/workflows/ci.yml` | M | Wave 2 done | serialize: `types.ts`, `package.json`, `ci.yml` | CI step `python scripts/export_openapi.py && npx openapi-typescript ... && git diff --exit-code frontend/src/api/schema.d.ts` exit 0; `npx tsc --noEmit` exit 0 | Alias `types.ts` to generated types module by module, starting with User and Order enums (fixes the lowercase role casing; `MetalInventoryPage` admin check works). Lint test: every handler has `response_model`. |
| W3-03 | TanStack Query as the data layer | ARCH-06, FE-20 | `frontend/package.json`, `frontend/src/main.tsx`, Dashboard, Orders, TimeTracking pages first, `WebSocketProvider` | M | W3-02, W2-13 | serialize: `package.json` | `cd frontend && yarn vitest run` exit 0; dashboard issues one `/orders` request, not four | WebSocket hints call `queryClient.invalidateQueries`; refetch on reconnect. No Zustand/Redux. |
| W3-04 | Behaviour primitives: Modal, Tabs, PageState, labels | FE-23, FE-24 | new `frontend/src/ui/{Modal,Tabs,PageState}.tsx`, `frontend/src/lib/labels.ts` | M | W3-01 | parallel with W3-02 | `cd frontend && yarn vitest run src/ui` exit 0: Modal traps focus, Esc closes, confirms on dirty close; Tabs are an ARIA tablist | One status-label source (pattern `components/consultation/labels.ts`); `useMemo` instead of effect-synced state; clickable rows become links or buttons. W4-03 styles these, it does not rebuild them. |
| W3-05 | Forms: one approach; split god pages | FE-16 | `OrderFormModal.tsx`, `CustomerFormModal.tsx`, `QuotesPage.tsx`, `InvoicesPage.tsx`, `AdminSystemPage.tsx`, `RepairDetailPage.tsx`, `frontend/package.json` | L | W3-04 | serialize: `package.json` | `cd frontend && yarn vitest run` exit 0; no `err.message` shown raw (grep) | `react-hook-form` plus `@hookform/resolvers/zod` on the big forms; promote `extractErrorInfo` to `getErrorMessage()`; field arrays for line items. Split along existing sub-component seams (04 §F.7). |
| W3-06 | ESLint with react-hooks and jsx-a11y in CI | FE-15, OPS-13 | new `frontend/eslint.config.js`, `frontend/package.json`, `.github/workflows/ci.yml` | S | W3-02 | serialize: `package.json`, `ci.yml` | `cd frontend && yarn lint` exit 0 against a recorded baseline | rules-of-hooks error, exhaustive-deps warn; baseline the existing violations and gate new ones. Closes issue #33. |
| W3-07 | DomainError with codes and one handler | ARCH-08 (error part) | new `core/errors.py`, `main.py`, services that raise `HTTPException` (`order_service.py`, `time_tracking_service.py`, `metal_inventory_service.py`) | M | Wave 2 done | serialize: `main.py` | `poetry run pytest -q` exit 0; new `tests/unit/test_domain_errors.py` asserts `{"detail", "code"}` | Keep `detail` so the frontend keeps working; add `code`. Replace the 63 hand-mapped `except` blocks gradually. |
| W3-08 | `Page[T]`, capped limits, server-side list and search | FE-06, SEC-16, BE-26 (and ARCH-08 pagination) | `models/common.py`, list routers (orders, customers, repairs, materials, activities, comments, users, time_tracking, calendar), `frontend/src/api/*`, `OrdersPage.tsx`, `tests/conftest.py` (tmp_path DBs) | M | W3-07, W3-03 | serialize with W3-07 on routers | `poetry run pytest -q tests/integration/test_pagination.py` (`limit` above 500 is 422; 150 orders page correctly) exit 0 | `Query(100, ge=1, le=500)`; filters and search on the server; `CustomerTypeahead` generalised to `<EntityTypeahead>` in order, quote and timer pickers. Test DBs written to `tmp_path`. |
| W3-09 | Delete dead layers; routers stop running SQL | ARCH-03, BE-24 | `src/goldsmith_erp/db/repositories/`, `src/goldsmith_erp/api/routers.py`, repository hygiene tests, router SQL moved into services, import-linter config | M | W3-07 | parallel with W3-01..W3-06 | `poetry run pytest -q` exit 0; import-linter contract forbidding `sqlalchemy` in `api/routers/**` passes | Decision "services own queries" (01 ARCH-03). Delete the hygiene tests together with the code. |
| W3-10 `[auth]` | Lifespan, single-run monitor, one Redis subscriber per process, WS auth | ARCH-04 (lock part), ARCH-11, SEC-12, SEC-F5 | `main.py`, `services/system_monitor.py`, `core/pubsub.py`, `api/routers/admin_email.py` | M | W2-13 | serialize: `main.py` | `poetry run pytest -q tests/integration/test_websocket_auth.py tests/unit/test_system_monitor.py` exit 0: revoked or inactive user is refused; `?token=` rejected; two app instances run the monitor once | `lifespan` creates and cancels tasks; `pg_try_advisory_lock` leader election; 30 s ping; Origin check. SMTP config persisted (DB) and read by all workers. |
| W3-11 `[money]` | Money as Numeric and Decimal; tz-aware timestamps | BE-14, BE-15 | `db/models.py` (70 Float money columns, about 98 naive DateTime), migration, all money services and schemas, `datetime.utcnow()` call sites | L | W1-07, W1-08, W2-04 | serialize: `db/models.py`, migration (run alone) | on PG `poetry run pytest -q` and `tests/integration/` exit 0; `tests/unit/test_money_rounding.py`: 3 lines of 1.005 subtotal 3.00 (not 3.01) with ROUND_HALF_UP; `_round_price` replaced | `Numeric(12,2)` money, `Numeric(12,4)` price per gram, `Numeric(10,3)` grams; sum rounded line totals; `DateTime(timezone=True)` with one normalising input type. Rehearse on a prod dump first. |

**Wave 3 exit criteria:** `schema.d.ts` generated in CI with a drift gate; Dashboard, Orders and TimeTracking on TanStack Query; no list endpoint without a capped `limit`; ESLint in CI; one registered exception handler emitting `code`; `db/repositories/` deleted; the monitor runs once per deployment; all money columns Numeric and timestamps tz-aware, rehearsed on a production dump.

### Wave 4: Design system

Order and rules follow `docs/design/UI-UX-PLAYBOOK.md` section 9 (phases 1 to 5) and its definition of done (section 10). Every item ends with the playbook's screenshot loop at 390, 768 and 1280 px and the axe smoke test.

| Item | Title | Findings | Files likely touched | Effort | Depends on | Parallel-safe with / serialize | Acceptance | Implementation note |
|---|---|---|---|---|---|---|---|---|
| W4-01 | Playbook phase 1: tokens, contrast, focus, copy | DES-01, DES-02, DES-08, DES-09, DES-10, DES-17, DES-27, DES-29 | `frontend/src/styles/brand-tokens.css`, `frontend/src/index.css`, `OfflineIndicator.tsx`, `frontend/src/hooks/useTheme.ts`, `AdminSystemPage.tsx` (theme form), copy strings | M | Wave 3 done | serialize: `brand-tokens.css` | `npx playwright test e2e/a11y-smoke.spec.ts` (axe on login, dashboard, orders, order detail: zero serious or critical) exit 0; hex ratchet recorded in CI | Primary `#b45309` (5.02:1), global `:focus-visible` in a dark colour, danger `#b91c1c`, offline banner above the header via `--z-banner`, semantic tokens and scales, aliases for the 41 undefined properties, umlaut fixes, theme form rejects white-on-primary below 4.5:1, hover lifts only under `(hover:hover)`. Recount hex values (verifier found 1,563/219, report 1,580/223). |
| W4-02 | Status system and deadline chip | DES-03, DES-04 | `frontend/src/design/status.ts` (from W3-04 labels), `frontend/src/ui/StatusBadge.tsx`, `frontend/src/ui/DeadlineChip.tsx`, `orders.css`, `dashboard.css`, `repairs.css` | M | W4-01, W3-04, W2-07 (new statuses) | parallel with W4-03 | `cd frontend && yarn vitest run src/ui` exit 0: every order, repair, quote and invoice status renders icon plus label | One map status to label, icon, tone; tones as `--status-*` tokens; chip shapes ● ok, ▲ soon, ■ overdue with text "in 2 Tagen". |
| W4-03 | Playbook phase 2: primitives, icons, type | DES-06, DES-07, DES-18, DES-19, DES-21, DES-22 | new `frontend/src/ui/{Button,IconButton,Field,DataTable,ListCard,Card,EmptyState,PageHeader,TabBar}.tsx`, styling of W3-04 Modal/Tabs/PageState, font files, SVG icon set | L | W4-01, W3-04 | parallel with W4-02 | `cd frontend && yarn vitest run src/ui` exit 0: IconButton requires `label`; Button min 44 px, `lg` 56 px; form Modal ignores backdrop taps | Self-hosted font with tabular numerals (typeface per D-14); one SVG set (Lucide suggested) plus 4 custom domain icons later. Dev-only demo route shows all states. |
| W4-04 | Shell: grouped nav, tab bar, Heute home, Werkbank-Modus, one scanner | DES-11, DES-12, DES-14, DES-24, DES-28 | `frontend/src/layouts/MainLayout.tsx`, `layout.css`, `App.tsx`, `ScannerContext.tsx`, `ScannerPage.tsx` | M | W4-03, W2-03 | serialize: `MainLayout.tsx` | screenshots at 390/768/1280 show no header overflow; `yarn vitest run` exit 0 | Groups Werkstatt / Kunden / Büro / Admin plus "Einstellungen"; bottom tab bar at 1024 px or less (Heute, Aufträge, Scan, Zeit, Mehr); Werkbank-Modus scales type and targets to 56 px; ScanFab plus overlay is the only scanner, `/scanner` becomes history and manual entry. Ships with the Dashboard page PR (playbook phase 3). |
| W4-05 | Migrate Orders list and Order detail | DES-15, DES-16 | `OrdersPage.tsx`, `OrderDetailPage.tsx`, `orders.css`, `order-detail.css` | M | W4-04 | serialize: `OrderDetailPage.tsx` | page stylesheet has zero hex values; `yarn vitest run` exit 0 | ListCard/DataTable with thumbnail, customer, title, deadline chip, status; rows are links; delete moves into the detail page or a menu; CSS line-clamp instead of "...". |
| W4-06 | Migrate Scanner, Time tracking, Customers | DES-05 (supporting) | `ScannerPage.tsx`, `TimeTrackingPage.tsx`, `CustomersPage.tsx`, `CustomerDetailPage.tsx`, their CSS | M | W4-04 | parallel with W4-05 | zero hex values in those stylesheets; `yarn vitest run` exit 0 | One page per PR (playbook phase 3). |
| W4-07 | Migrate the remaining pages | DES-23 | Repairs, Quotes, Invoices, Consultations, Materials, Metal inventory, Scrap gold, Calendar, Users, Admin pages and CSS | L | W4-04 | parallel per page (one PR each) | hex ratchet drops each PR; inline `style={{` count falls to justified exceptions | Invoices, AdminSystem and MetalTypeManager first (most inline styles). |
| W4-08 | Customer-facing surfaces: portal, emails, PDFs | DES-26 | `CustomerPortalPage.tsx`, `portal.css`, email templates, PDF styles | M | W4-07, W6-07 if the portal ships | parallel-safe | portal footer contrast at least 4.5:1; workshop name and logo from theme settings | Align portal tokens with the app; show the latest approved photo and date prominently when W6-07 exists. |
| W4-09 | Playbook phase 4: delete duplicates, decide Tailwind, clean base CSS | DES-05, DES-20, DES-25, DES-30 | all page CSS, `utilities.css`, `index.css`, `OrderList.tsx`, stylelint config, `frontend/package.json` | M | W4-05..W4-07 | serialize: `package.json` | `grep` finds no `.btn*`, `.modal*`, `.status-badge*`, `.form-group` outside `src/ui`; stylelint `color-no-hex` passes | Tailwind per D-14 (design report recommends removing it; the playbook keeps `@theme` pending Max). |
| W4-10 | Playbook phase 5: dark or high-contrast mode | DES-13 | `brand-tokens.css`, `ThemeContext.tsx`, `ThemeToggle.tsx`, `index.html` | M | W4-09 | parallel-safe | contrast checks pass in both themes; screenshots light and dark at both widths | Decide dark mode vs "Werkstatt hoher Kontrast" first (D-14); otherwise remove `index.html:4-11` and the three partial dark blocks. |

**Wave 4 exit criteria:** the playbook section 10 definition of done holds for every migrated page; axe smoke test green; hex count outside the token file is zero or listed as justified exceptions; no duplicate `.btn*`, `.modal*`, `.status-badge*` or `.form-group` definitions outside `src/ui`.

### Wave 5: Operations, CI, compliance docs

| Item | Title | Findings | Files likely touched | Effort | Depends on | Parallel-safe with / serialize | Acceptance | Implementation note |
|---|---|---|---|---|---|---|---|---|
| W5-01 | Dependency backlog | OPS-06 (and 02 §D) | `pyproject.toml`, `poetry.lock`, `frontend/package.json`, `frontend/yarn.lock`, `core/security.py`, `api/routers/auth.py`, `api/deps.py`, `main.py` | M | none (can start any time) | serialize: `package.json`, `poetry.lock`, `main.py` | `poetry run pip-audit` and `cd frontend && yarn npm audit --severity high --recursive` report no runtime-reachable high/critical; full suites exit 0 | anyio to 4.14.2 (the only critical), cryptography to 50, react-router-dom to 7.18.2 or later; replace python-jose with pyjwt (removes ecdsa); plan passlib exit; delete or ignore the likec4 docs lockfile (4 highs). |
| W5-02 | CI pipeline: E2E, frontend coverage, audits, ruff, caching, mypy ratchet | OPS-01, OPS-02, OPS-03, OPS-04, OPS-10, OPS-11, OPS-12 | `.github/workflows/ci.yml`, `bundle-size-gate.yml`, `frontend/package.json`, `frontend/vitest.config.ts`, `pyproject.toml`, `tests/unit/test_customer_service.py` | M | W5-01 | serialize: `ci.yml`, `package.json` | CI run green with the new jobs; `yarn vitest run --coverage` exit 0 | Nightly `schedule:` (or the PR job) runs goldsmith-workflow, goldsmith-full, consultation-wizard, estimator-quote-flow; `@vitest/coverage-v8` with thresholds; advisory `security-audit` job; `ruff check`; `cache: poetry`/`cache: yarn`; fail when a mypy override widens; move `test_filter_by_tag` to `tests/integration/`. |
| W5-03 | Make targets and timer installer | OPS-05, OPS-07, GDPR-16 | `Makefile`, `setup.sh`, `deploy/systemd/*.service`, `api/routers/health.py` | S | W1-02 | serialize: `setup.sh` | `make install-timers` then `systemctl --user list-timers 'goldsmith-*'` lists all three; `make test-local` exit 0 | Units default to `podman-compose.prod.yml`; `make prod-status` shows timers; health reports last successful cleanup. |
| W5-04 | Real-time contract test | OPS-09 | `tests/integration/test_ws_delivery.py`, `tests/conftest.py` | S | W3-10 | parallel-safe | `poetry run pytest -q tests/integration/test_ws_delivery.py` exit 0 | Publish an event through the real subscribe/forward path (fake or CI Redis) and assert the client receives the JSON. |
| W5-05 `[gdpr]` | Encrypted backups, key escrow, erasure ledger replay, working alerts | GDPR-06, GDPR-07, SEC-F4, SEC-F7 | `scripts/backup.sh`, `scripts/backup-sync.sh`, `scripts/restore.sh`, `scripts/` erasure ledger, `services/customer_service.py` (ledger append), `api/routers/health.py`, `Containerfile`, `docs/technical/GDPR_ERASURE_RETENTION.md` | M | W1-10 | parallel-safe | restore drill: erase customer, restore an older dump, run `restore.sh`, customer is re-erased (scripted test exit 0) | `age -r <pubkey>`, `chmod 600`, back up `./uploads` and `caddy_data`; authenticated EU upload; ledger outside DB and dump rotation replayed before go-live; fix `BACKUP_CLOUD_URL` vs `CLOUD_SYNC_URL`; notify endpoints reachable. Printed keys in Anne's safe; quarterly restore test. |
| W5-06 `[gdpr]` | Encrypt remaining sensitive columns; rotation path | SEC-14, GDPR-18 (and GDPR-09 encryption part) | `db/models.py`, migration, `db/types.py`, `core/encryption.py`, `scripts/rotate-secrets.sh`, docs | M | W3-11 | serialize: `db/models.py`, migration | `poetry run pytest -q tests/unit/test_encrypted_string.py tests/integration/test_customer_pii_encryption.py` exit 0; all-rows-ciphertext check passes before `tolerate_plaintext=False` | Signatures, `Customer.notes`, `birthday`, `CustomerUpdate.body`, `repair_jobs.estimated_value`; MultiFernet plan with a separate `BLIND_INDEX_KEY`; drop `appraised_value_hmac` if unused. |
| W5-07 `[gdpr]` | Retention schedule and executing sweep | GDPR-08 | `jobs/retention_sweep.py`, `deploy/systemd/goldsmith-retention-sweep.service`, Art. 30 record | M | W1-10, W5-03 | parallel-safe | `poetry run pytest -q tests/unit/test_retention_sweep.py tests/integration/test_retention_sweep.py` exit 0 | Per-table schedule (D-08); covers inactive customers, consultations, quotes, updates, photos, notifications, audit logs; `RETENTION_EXECUTE=1` only after Anna and Henrik sign off. |
| W5-08 `[gdpr]` | Complete Art. 15 export | GDPR-05 | `api/routers/customers.py`, `services/customer_service.py`, `core/permissions.py` (GDPR_EXPORT) | M | W1-05, W1-10 | serialize: `customers.py`, `permissions.py` | `poetry run pytest -q tests/integration/test_gdpr_endpoints.py` exit 0: export contains invoices, quotes, valuations, Altgold, repairs, updates, cost changes, consents, photo list and a `meta` block | Write a `gdpr_requests(request_type='export')` row; include customer-supplied facts (`wishes`, `source_material`) per D-13. |
| W5-09 `[gdpr]` | Employee analytics and processors | GDPR-14, GDPR-15 | `api/routers/analytics.py`, `services/email_service.py`, docs | S | W1-04 | parallel-safe | `poetry run pytest -q tests/unit/test_email_tls.py` exit 0 (plaintext SMTP refused) | Aggregate accuracy analytics (group of 3 or more) or document it; enforce TLS on every port; AVVs with mail and backup hosts. |
| W5-10 `[gdpr]` | Compliance documents | GDPR-17 (and 07 §F) | `docs/superpowers/plans/qr-barcode-workflow/VERZEICHNIS-VERARBEITUNGSTAETIGKEITEN.md`, new TOMs, Art. 13 notice, AVV list, breach runbook, `docs/GDPR_COMPLIANCE.md` | S | none | parallel-safe | document review by Anne (and a lawyer where marked "verify") | Controller is Anne's business; no conflicted DPO; add V1.0 entries and the unrecorded activities; breach register; key-management runbook; refresh `PII-SCRUB-AUDIT.md`. |
| W5-11 | Engineering docs, ADRs, operator warnings | ARCH-16, OPS-08, SEC-F8, SEC-F10 | `docs/adr/`, `docs/DEPLOYMENT.md`, `docs/technical/infrastructure/PRODUCTION_DEPLOYMENT.md`, C4 model, `CLAUDE.md` | S | none | parallel-safe | links checked; no doc references migrations that do not exist | Archive `ARCHITECTURE_REVIEW.md`; ADRs (single box, cookie auth, price semantics, services own queries); app rollback procedure; do not co-host web apps; rotate demo accounts; refresh stale CLAUDE.md guidance (01 §F.7). |
| W5-12 | Observability and a one-shot migrate service | ARCH-12, ARCH-14 | `podman-compose.prod.yml`, `main.py` or `core/logging.py` (Sentry/GlitchTip init), `frontend/src/components/ErrorBoundary.tsx` | S | W3-10 | serialize: `main.py`, `podman-compose.prod.yml` | staged error appears in the tracker with PII scrubbed; failed migration does not crash-loop the API | Self-hosted GlitchTip preferred (D-18); journald log driver; `migrate` service runs `scripts/backup.sh` first, `depends_on: service_completed_successfully`. |
| W5-13 | Repository hygiene | OPS-14 | `.claude/worktrees/`, `alembic_backup/` | S | none | parallel-safe | `git worktree list` shows only active worktrees | Diff each stale worktree for uncommitted work before `git worktree remove`. |

**Status (as of 2026-09-25).** No Wave 5 item has landed; three have agents running.

- **W5-01** (dependency backlog) — in progress; the fix agent is still running, no report yet.
- **W5-02** (CI pipeline: E2E, coverage, audits, ruff, caching, mypy ratchet) — in progress; the fix agent is still running, no report yet.
- **W5-03** (make targets and timer installer) — in progress; the fix agent is still running, no report yet.
- **W5-04** through **W5-13** — open; no evidence any of them has started.

**Wave 5 exit criteria:** no runtime-reachable high or critical advisory; CI runs all E2E specs, frontend coverage, dependency audits and ruff; timers installed by one command and visible in `make prod-status`; an encrypted backup restored in a drill with the erasure ledger replayed; retention sweep signed off; Art. 30 record, TOMs, Art. 13 notice, AVV list and breach runbook exist.

### Wave 6: Target architecture

| Item | Title | Findings | Files likely touched | Effort | Depends on | Parallel-safe with / serialize | Acceptance | Implementation note |
|---|---|---|---|---|---|---|---|---|
| W6-01 | Transactional outbox and worker process | ARCH-04 (outbox part) | new `outbox_messages` table, migration, `goldsmith_erp/worker.py`, `podman-compose.prod.yml`, `services/email_service.py` | M | W3-10, W3-11 | serialize: `db/models.py`, migration, compose | integration test: business change and outbox row commit together; worker sends once with `SKIP LOCKED`; retries with backoff | dedupe_key UNIQUE; admin page of failed deliveries; old and new email paths behind a flag for one week. |
| W6-02 | CustomerMessage module | ARCH-05 | new `domains/comms/`, `notification_service.py`, `customer_update_service.py` | M | W6-01 | serialize: `db/models.py`, migration | no staff notification path sends customer email (grep plus test); every customer message has consent check, rendered snapshot and delivery status | Produced by timeline events or explicitly by the goldsmith; folds in the V1.2 customer-update flow as the manual producer. |
| W6-03 | media_assets and MediaStore | ARCH-10 | new table, migration, `photo_service.py`, `repair_photo_service.py`, `consultation_photo_service.py`, `CustomerUpdate.photo_ids` | L | W6-01 | serialize: `db/models.py`, migration | three photo tables migrated with compatibility views; thumbnails generated in the worker | `customer_visible` flag; sha256; local FS behind an interface (S3/MinIO later); backups include media. |
| W6-04 | Jobs spine (Order and Repair) | ARCH-02 | new `jobs` table, migration, invoices, updates, media and events reference `job_id`, repair invoicing | L | W6-02, W6-03, W2-07 | serialize: everything in `db/models.py` | a repair can be invoiced; timeline and dashboard read from `jobs` | Highest-risk migration; add, backfill, move one feature at a time. |
| W6-05 | Modularise models and services | ARCH-09 | `goldsmith_erp/domains/*`, `db/models/__init__.py` re-export, import-linter contracts | L | W6-04 | serialize: `db/models.py` (the whole item) | `alembic check` shows no drift; mypy override count falls | Convert to `Mapped[]` per package as it moves. |
| W6-06 `[gdpr]` | Feedback channel phase 1: email digest with photos and PDF report | DOM-32 (and 05 §D options 1 and 2; 07 §E E1, E2, E4, E6, E7, E8, E15, E16, E17) | `customer_update_service.py`, email templates, `pdf_service.py`, consent checks | M | W6-02, W1-05, W2-11, W5-10 | parallel with W6-03 | a milestone produces one mail with 1 to 3 selected, EXIF-stripped photos; opt-out and privacy link in the footer; recipient confirmation before the first photo mail; every send audited | Satisfaction mail after pickup only with consent or the §7(3) UWG route and an opt-out (07 §E). |
| W6-07 `[gdpr]` `[auth]` | Optional token status page with one-click decisions | DOM-29, DOM-31, FE-21, GDPR-12, GDPR-20 (and 07 §E E9 to E13, E18) | `customer_portal.py`, `CustomerPortalPage.tsx`, `/portal/:token` route, Caddy path restriction, templates | L | W6-06, D-03 = yes | serialize: `main.py` | security review passes E9 to E13: 128-bit or longer tokens stored hashed, expiry and revocation, `no-referrer`, `noindex`, only `/api/v1/portal/*` exposed; DSFA screening written | Build only if D-03 is yes. Generic item label, pipeline step, date, explicitly shared photos; approve/decline logged as evidence; real workshop contact details; "Anfrage zu meinen Daten" form. |

**Wave 6 exit criteria:** no staff-notification path sends customer email; every customer message has a consent check, a rendered snapshot and a delivery status; photos live in `media_assets`; repairs can be invoiced through the jobs spine; if D-03 was yes, the token page passed E9 to E13 and a DSFA screening is written.

### Wave 7: Backlog

| Item | Title | Findings | Files likely touched | Effort | Depends on | Parallel-safe with / serialize | Acceptance | Implementation note |
|---|---|---|---|---|---|---|---|---|
| W7-01 | Workshop model: assignee, apprentice role, multi-piece, QC checklist | DOM-25, DOM-26, DOM-27 | `db/models.py`, migration, `core/permissions.py`, `OrderDetailPage.tsx`, `DashboardPage.tsx` | L | W6-04 | serialize: `db/models.py`, migration | "Meine Stücke" filter; wedding-ring pair with two sizes and engravings; 6-item QC checklist stored | APPRENTICE role without price visibility only if D-04 says so; use `OrderItem`. |
| W7-02 | Aftercare reminders and deposits | DOM-36, DOM-37 | scheduler rules, `invoice_service.py`, `pdf_service.py` | M | W6-02, W2-04 | serialize: `invoice_service.py` | reminder after 12 months only with consent; Anzahlungsrechnung deducted on the final invoice | Confirm §14 UStG deposit invoice format with the Steuerberater. |
| W7-03 | Offline queue for bench actions | DOM-39 | `frontend/src/lib/network-transport.ts`, `vite.config.ts` | M | W1-14, W3-03 | parallel-safe | offline timer start/stop replays once online with the existing idempotency keys | Then restore sync wording in the offline banner. |
| W7-04 | Feature flags and bloat reduction | ARCH-13, DOM-28, DOM-33, DOM-40, DOM-41, DOM-42, DOM-43, DOM-45 | `core/config.py`, `/api/v1/features`, `api/routers/{ml,analytics,admin_scan_metrics,theme}.py`, `pyproject.toml`, `seed_data.py`, Lager page | M | W3-08 | serialize: `pyproject.toml`, `core/config.py` | ML and analytics off by default and hidden in the SPA; unused `boto3` removed | Keep `find_similar_orders` if the estimator uses it; one "Lager" page with Metall / Steine / Verbrauch; latest ring size in the customer header from the measurement library; extend seed activities. |
| W7-05 | Audit and redaction attached to data | ARCH-15 | services for sensitive aggregates, Pydantic read models | M | W3-09 | parallel-safe | new endpoints returning financial fields are audited without touching a path table | `@audited_read("financial")` service decorator; sensitive-field markers drive per-role redaction. |
| W7-06 | Prior-audit hygiene without IDs | FE-25 (and the open rows of 01 §A, 03 §A, 04 §A) | `frontend/.yarn/install-state.gz` (do not commit), `models/order.py` (`sanitize_text` keyword blocklist), `db/session.py` (`async_sessionmaker`, `get_db` annotation), `.dict()` calls, blocking `write_bytes` in async handlers, `order_materials` ondelete, `orders.status` index, unbounded String columns, notification scanner N+1, `metal_inventory.py` `detail=str(e)`, `health.py` exception text, remaining `window.prompt`/`confirm`, QrCameraScanner and TimerWidget hook issues, unmemoised context values, scan sounds not precached, LoginPage 429 message, deep link `from` lost at login | M | W3-06 | parallel per sub-item | each sub-item has its own test; `yarn install` fixes `yarn build` locally | Batch into small PRs by file. |

---

## 3. Wave 1 hand-off packets

Each packet is self-contained: an agent with no chat context can start from it. Common rules for all packets: read the cited findings first; TDD (tests below are written before code and must fail first); the "Verify" commands must all exit 0, and the agent pastes them with exit codes into the PR; the general gates in section 0 step 5 also apply. "Stop" means stop and report to the orchestrator without guessing.


**Assumptions used by the Wave 1 packets** (each maps to a decision in section 6):

| ID | Assumption | Decision | Items |
|---|---|---|---|
| A1 | `Order.price` is the gross Endpreis; the invoice fallback splits it into net and VAT so the total equals the price | D-01 | W1-07 |
| A2 | Only issued invoices (SENT, PAID, OVERDUE) are exported; revenue accounts beyond 8400 come from the Steuerberater | D-02 | W1-09 |
| A3 | The Altgold credit is deducted after VAT, with its own Ankaufbeleg; Ankaufsabschlag defaults to 0% | D-02 | W1-08 |
| A4 | Invoice snapshot: JSON at creation, frozen PDF plus SHA-256 at SENT; retention 8/6/5 years | D-06 | W1-10 |
| A5 | Reminder emails to customers are sent at most once per event and recorded as a CustomerUpdate row | D-07 | W1-12 |
| A6 | The estimator prices labor at `hours_p50 x blended rate` | D-09 | W1-16 |
| A7 | Allergies need explicit consent (wording `v0-draft`); withdrawing it clears the field | D-05 | W1-05 |
| A8 | Invoice lines come from the converted quote, else the order price, else cost x (1 + margin) | D-01 | W1-07 |
| A9 | The public portal router is off by default until W6-07 | D-03 | W1-03, W1-13 |
| A10 | VIEWER stays as a role; no VIEWER accounts are created until W1-04 lands | D-04 | W1-04 |

### W1-01 Reject placeholder secrets; bind dev stack to loopback `[auth]`
- **Objective:** the backend cannot start with a publicly known signing key or salt in production, and the dev stack no longer exposes Redis and plain HTTP to the LAN (SEC-02, SEC-08).
- **In scope:** `src/goldsmith_erp/core/config.py`, `podman-compose.yml`, `docker-compose.yml`, `README.md` (dev-stack warning), `tests/unit/test_config.py`.
- **Out of scope:** `setup.sh` and `.env.example` (W1-02); key rotation (W5-06).
- **Tests first** (`tests/unit/test_config.py`):
  - `test_placeholder_secret_key_rejected_when_debug_false`: `Settings(SECRET_KEY="CHANGE_THIS_TO_A_SECURE_RANDOM_STRING_AT_LEAST_32_CHARS", DEBUG=False, ENCRYPTION_KEY=<valid>, COOKIE_SECURE=True)` raises `ValidationError` naming SECRET_KEY.
  - `test_placeholder_anonymization_salt_rejected_when_debug_false`: same for ANONYMIZATION_SALT (today it boots with no warning at all, per the verifier).
  - `test_placeholder_secret_key_allowed_with_warning_when_debug_true`: boots and logs a warning (caplog).
  - `tests/unit/test_compose_bindings.py::test_dev_redis_and_backend_bound_to_loopback`: parse both compose files with `yaml.safe_load`; the published ports of `redis` and `backend` start with `127.0.0.1:`.
- **Verify:** `poetry run pytest -q tests/unit/test_config.py tests/unit/test_compose_bindings.py`; `cd src && poetry run mypy goldsmith_erp/core/config.py --ignore-missing-imports`; `poetry run pytest -q` (full suite; other tests build `Settings`).
- **Stop if:** the `model_validator(mode="after")` breaks existing `Settings` fixtures in more than a handful of tests, or any deployed environment is known to run with the placeholder (then rotation must be planned first, W5-06).

### W1-02 Bootable, hardened production config `[auth]`
- **Objective:** the documented `setup.sh` path produces an `.env.production` that boots with safe defaults, and the SPA document gets security headers (SEC-F1, SEC-03, SEC-06, SEC-F2, OPS-15).
- **In scope:** `setup.sh`, `.env.example`, `podman-compose.prod.yml` (Redis `maxmemory-policy noeviction`), `frontend/nginx.conf`, `deploy/Caddyfile`, `src/goldsmith_erp/models/material.py` (`webshop_url`), `src/goldsmith_erp/api/routers/theme.py` (`logo_url`).
- **Out of scope:** uvicorn proxy flags and limiter code (W1-03); timer installation (W5-03); `CLOUD_SYNC_URL` vs `BACKUP_CLOUD_URL` (W5-05).
- **Tests first:**
  - `tests/unit/test_env_files.py`: `.env.example` has `ACCESS_TOKEN_EXPIRE_MINUTES=30` (or omits it), contains a documented `AUTH_REVOCATION_FAIL_CLOSED` line and an `ANONYMIZATION_SALT` line; `setup.sh` contains no `10080` and writes `ANONYMIZATION_SALT`.
  - `tests/unit/test_url_validation.py`: `MaterialCreate(webshop_url="javascript:alert(1)")` raises; `https://example.com/x` passes; same for the theme `logo_url`.
- **Verify:** `poetry run pytest -q tests/unit/test_env_files.py tests/unit/test_url_validation.py`; scratch run in a throwaway checkout: `bash setup.sh` (non-interactive answers), then `cd src && poetry run python -c "from goldsmith_erp.core.config import Settings; Settings(_env_file='../.env.production')"` exit 0; `podman run --rm -v "$PWD/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t` exit 0; after `make prod-start` on a scratch box, `curl -skI https://localhost/ | grep -i -e content-security-policy -e x-frame-options -e strict-transport-security` prints three headers.
- **Notes:** compute the CSP `sha256-` hash of the inline theme script in `frontend/index.html`; never add `'unsafe-inline'`. `client_max_body_size 10m` covers 8 MB photos and 10 MB materials.
- **Stop if:** the CSP blocks app load in the browser console after the hash is added, or `setup.sh` cannot be run non-interactively (then report the exact prompts).

### W1-03 Real client IP for rate limits; portal behind a flag; login timing `[auth]`
- **Objective:** limits apply per real client, the public portal is off unless enabled, and login does not reveal whether an email exists (SEC-04, SEC-10, SEC-17).
- **In scope:** `api/routers/auth.py`, `api/routers/customer_portal.py`, `middleware/rate_limiting.py`, `middleware/auth_required.py`, `core/config.py` (`PORTAL_ENABLED: bool = False`), `main.py` (limiter `storage_uri`, conditional portal mount), `podman-compose.prod.yml` (`--proxy-headers --forwarded-allow-ips=<compose subnet>`).
- **Out of scope:** portal hardening and token page (W6-07); limits on other mutating endpoints (later).
- **Tests first:**
  - `tests/unit/test_rate_limit_keys.py`: with the peer inside the trusted proxy subnet and `X-Forwarded-For: 192.168.1.50`, the key is `192.168.1.50`; with an untrusted peer the header is ignored.
  - `tests/integration/test_portal.py::test_portal_disabled_returns_404`: `PORTAL_ENABLED=False`, `POST /api/v1/portal/lookup` returns 404 and the path is not in the public whitelist; existing portal tests run with `PORTAL_ENABLED=True`.
  - `tests/unit/test_auth_security.py::test_unknown_email_runs_dummy_bcrypt`: patch the verify function; it is called exactly once for an unknown email.
- **Verify:** `poetry run pytest -q tests/unit/test_rate_limit_keys.py tests/integration/test_portal.py tests/unit/test_auth_security.py`; `cd src && poetry run mypy goldsmith_erp/main.py goldsmith_erp/api/routers/auth.py --ignore-missing-imports`.
- **Assumption:** D-03 default (portal off until W6-07). Alternative: keep it on for LAN use; then only the rate-limit half of this item applies.
- **Stop if:** Redis-backed slowapi storage needs a new dependency (`limits[redis]`): that touches `pyproject.toml`, which must be serialized; report before adding.

### W1-04 Role projection sweep: financial and design data `[auth]` `[gdpr]`
- **Objective:** VIEWER never receives prices, costs, revenue, insurance values, design descriptions or design photos, and financial reads on quotes, repairs, metal inventory, metal prices and analytics are audited (SEC-01, SEC-09, GDPR-03, GDPR-04, GDPR-09 gating, SEC-15).
- **In scope:** `core/permissions.py` (new `FINANCIAL_VIEW`, `DESIGN_VIEW` for ADMIN and GOLDSMITH; REPORTS_VIEW removed from VIEWER); routers `analytics.py`, `repairs.py`, `materials.py`, `metal_inventory.py`, `customers.py` (`/top`, `/{id}/stats`), `photos.py`, `orders.py` (strip `description`, `special_instructions`, nested `materials[].unit_price`), `valuations.py` (PDF uses `VALUATION_EXPORT`); read models in `models/{repair,material,metal_inventory,order}.py`; `middleware/audit_logging.py` (`_RESOURCE_ROUTES`).
- **Out of scope:** encrypting `repair_jobs.estimated_value` (W5-06); an APPRENTICE role (W7-01).
- **Tests first:**
  - `tests/integration/test_viewer_response_denylist.py`: seed one of each entity; for every GET route in `app.routes` reachable by VIEWER, the JSON (walked recursively) contains none of `price, total_price, material_cost, unit_price, price_total, price_per_gram, remaining_value, cost_at_time, price_per_gram_at_time, total_value, average_price_per_gram, total_spent, estimated_cost, actual_cost, estimated_value, hourly_rate`, and order/repair payloads contain no `description`/`special_instructions`; `GET /photos/{id}/file` and `/thumbnail` return 403 for VIEWER.
  - Same file: GOLDSMITH still receives those fields (regression guard).
  - `tests/integration/test_valuations.py::test_pdf_export_admin_only`: GOLDSMITH 403, ADMIN 200.
  - `tests/integration/test_financial_audit.py`: `GET /repairs/{id}` and `GET /metal-inventory/purchases` write a financial audit row.
- **Verify:** `poetry run pytest -q tests/integration/test_viewer_response_denylist.py tests/integration/test_order_viewer_projection.py tests/integration/test_viewer_allow_list_regression.py tests/integration/test_valuations.py tests/integration/test_financial_audit.py` (the existing order projection test must still pass 7/7).
- **Assumption:** D-04 default (VIEWER stays; until this lands, create no VIEWER accounts).
- **Stop if:** walking all routes needs fixtures for more than about 30 entity types; cover the routes listed in 02 §B plus photos, and report the remainder.

### W1-05 Consent store; allergies behind explicit consent `[gdpr]`
- **Objective:** health data (allergies, health-related no-gos) is stored only with provable explicit consent and read only by ADMIN and GOLDSMITH; consent exists as data for every later channel (GDPR-02, GDPR-11, DOM-07).
- **In scope:** `db/models.py` (`CustomerConsent`), one Alembic migration, `models/customer.py`, `services/customer_service.py` (consent create/withdraw; include in export; scrub on erasure), `api/routers/customers.py` (consent endpoints with `@require_permission`; allergies projection), `frontend/src/components/CustomerFormModal.tsx` (three checkboxes: Fotos für Updates, Marketing/Geburtstag, Allergie-Angaben), `frontend/src/api/customers.ts`, `frontend/src/types.ts`.
- **Out of scope:** email opt-out links and suppression list (W6-06); portfolio photo consent use (W6-06).
- **Tests first:**
  - `tests/unit/test_customer_consent.py`: writing `allergies` without an active `health_allergy` consent raises a 422-mapped error; with consent it is stored; withdrawing the consent clears `allergies` (assumption A7) and writes an audit row; consent rows keep `wording_version`, `method`, `granted_at`.
  - `tests/integration/test_customer_consent_api.py`: VIEWER `GET /customers/{id}` has no `allergies` key; GOLDSMITH has it.
  - `tests/unit/test_gdpr_customer_erasure.py`: consents appear in the export and are scrubbed on erasure.
  - `frontend/src/components/CustomerFormModal.test.tsx`: the allergy field is disabled until the consent box is ticked.
- **Verify:** the tests above; `TEST_DATABASE_URL=... poetry run pytest -q tests/integration/test_customer_consent_api.py`; migration round trip on PG; `cd frontend && npx tsc --noEmit`.
- **Assumption A7 (D-05):** allergies require explicit consent with wording version `v0-draft` until a lawyer approves the text. Alternative: store only a material restriction ("kein Nickel verwenden") with no health reason.
- **Stop if:** existing rows already hold allergies (check a prod dump): a data-handling decision is needed before the write guard ships.

### W1-06 Invoice status only via actions; tz-safe dates `[money]` `[auth]`
- **Objective:** no role can change an invoice's status through PUT, and aware datetimes from the frontend no longer crash invoice creation (BE-05, BE-04).
- **In scope:** `models/invoice.py`, `models/validators.py` (new `UtcNaiveDatetime`), `services/invoice_service.py` (`update_invoice`), `api/routers/invoices.py` (new `POST /invoices/{id}/send`, `@require_permission(Permission.INVOICE_EDIT)`), `frontend/src/pages/InvoicesPage.tsx` and `frontend/src/api/invoices.ts` call sites that set status via PUT.
- **Out of scope:** issued-invoice locking and Storno (W2-04); all other datetime schemas (W3-11).
- **Tests first:**
  - `tests/unit/test_invoice_service.py::test_update_ignores_or_rejects_status`: `InvoiceUpdate(status="cancelled")` raises `ValidationError` (field removed, `extra="forbid"`).
  - `tests/integration/test_invoice_status_authz.py::test_goldsmith_cannot_cancel_paid_invoice_via_put`: GOLDSMITH `PUT /invoices/{id}` with `{"status":"cancelled"}` on a PAID invoice returns 422 and the invoice stays PAID (the verifier reproduced the bypass in a scratch test; port that test).
  - `tests/integration/test_invoice_status_authz.py::test_send_action_moves_draft_to_sent`: replaces `test_draft_to_sent_via_update`.
  - `tests/unit/test_invoice_service.py::test_create_accepts_aware_due_date`: `InvoiceCreate(due_date="2026-10-30T10:00:00Z")` validates and stores naive UTC; a past aware date gives a validation error, not `TypeError`.
- **Verify:** `poetry run pytest -q tests/unit/test_invoice_service.py tests/integration/test_invoice_status_authz.py`; `cd src && poetry run mypy goldsmith_erp/services/invoice_service.py goldsmith_erp/models/invoice.py --ignore-missing-imports`; `cd frontend && yarn vitest run src/pages/InvoicesPage.test.tsx`.
- **Stop if:** another client (scripts, imports) sets status via PUT; list them.

### W1-07 Invoice amounts from the agreed price; safe quote conversion `[money]`
- **Objective:** the customer is billed exactly what was agreed, once, on the right order (BE-01, BE-02, BE-17, BE-25).
- **In scope:** `services/quote_service.py` (`convert_quote`, `approve_quote`), `services/invoice_service.py` (line building), new `services/line_item_builder.py`, `docs/adr/0001-order-price-semantics.md`.
- **Out of scope:** copying quote lines into the order Soll and the quote email (W2-05); Numeric migration (W3-11); Altgold (W1-08).
- **Assumption A1 (D-01):** `Order.price` is the gross Endpreis (VAT included). This matches `cost_calculation_service.py:135-141,433-434` and consumer price display rules. With no quote and no breakdown, the invoice has one line with net `round(price / (1 + rate), 2)` and VAT `price - net`, so `invoice.total == order.price`. Alternative: `Order.price` is net; then convert stores `quote.subtotal` and the ADR says so. Either way the ADR records it and closes issue #28.
- **Assumption A8:** line source priority is (1) the converted quote's lines, (2) `order.price`, (3) cost breakdown x (1 + `profit_margin_percent`). The breakdown remains internal Soll/Ist.
- **Tests first:**
  - `tests/integration/test_life_of_a_ring.py`: quote net 1,000.00 + 190.00 VAT, approve, convert, complete, invoice: total 1,190.00 (today 1,416.10, reproduced by the verifier).
  - `tests/unit/test_invoice_amounts.py`: order with `price=1332.99` and a breakdown gives `invoice.total == 1332.99` (today 952.00); order with no price and no quote bills cost x 1.40; `DEFAULT_HOURLY_RATE=85` in settings is used when `hourly_rate` is NULL.
  - `tests/unit/test_quote_convert.py`: quote with `order_id=65` confirms order 65 and creates no new order; `order.customer_id != quote.customer_id` is rejected at create; convert after `valid_until` is rejected; an unlinked quote creates a DRAFT order; two concurrent converts create one order (PG).
- **Verify:** `poetry run pytest -q tests/integration/test_life_of_a_ring.py tests/unit/test_invoice_amounts.py tests/unit/test_quote_convert.py tests/unit/test_invoice_service.py tests/unit/test_quote_line_items.py`; on PG `TEST_DATABASE_URL=... poetry run pytest -q tests/unit/test_quote_convert.py -k concurrent`.
- **Stop if:** Anne or Max answers D-01 differently from A1 (switch to the alternative, same tests with net figures); existing tests assert cost-based invoices (update them with a note naming BE-02).

### W1-08 Altgold: correct valuation, immutable after signing, credit after tax `[money]`
- **Objective:** Altgold can be added from the UI, is valued per metal, cannot change after the customer signs, and is credited without shrinking the VAT base (BE-03, BE-11, DOM-19, DOM-20).
- **In scope:** `db/models.py` (per-metal fine grams and prices on ScrapGold, `Invoice.scrap_gold_credit_eur`, `UNIQUE(scrap_gold.order_id)`), one migration, `models/scrap_gold.py` (alloy enum), `services/scrap_gold_service.py`, `api/routers/scrap_gold.py`, `services/invoice_service.py` (replace `_build_scrap_gold_line_item`), `models/invoice.py`, `services/pdf_service.py` (invoice and receipt show "abzüglich Altgold-Ankauf"), `frontend/src/components/scrap-gold/ScrapGoldTab.tsx`, `frontend/src/api/scrap-gold.ts`, `frontend/src/types.ts`.
- **Out of scope:** ID capture and Ankaufsbuch (W2-16); Numeric (W3-11).
- **Assumption A3 (D-02):** Zahlbetrag = gross invoice total minus Ankaufswert, with a separate Ankaufbeleg; VAT on the full sale. Alternative only if the Steuerberater rules otherwise. Ankaufsabschlag default 0% in settings until Anne sets it.
- **Tests first:**
  - `tests/unit/test_scrap_gold_valuation.py`: 15 g 585 plus 8 g 750 gives 14.775 g Au; 10 g ag925 gives 9.25 g Ag valued at the silver price; alloy `"925"` or an int returns 422 (never 0.0); `add_item` or `remove_item` after SIGNED returns 409; `calculate_and_update` on a SIGNED record keeps SIGNED.
  - `tests/unit/test_invoice_scrap_gold_credit.py`: order with SIGNED scrap gold worth 702.00 creates an invoice (today a 500); VAT is computed on the full sale; `amount_due == total - 702.00`.
  - `tests/integration/test_scrap_gold_permissions.py`: a second scrap-gold record for the same order returns 409.
  - `frontend/src/components/scrap-gold/ScrapGoldTab.test.tsx`: the add-item request sends `alloy: "585"` (string code).
- **Verify:** `poetry run pytest -q tests/unit/test_scrap_gold_valuation.py tests/unit/test_invoice_scrap_gold_credit.py tests/integration/test_scrap_gold_permissions.py`; migration round trip on PG; `cd frontend && yarn vitest run src/components/scrap-gold && npx tsc --noEmit`.
- **Stop if:** the Steuerberater's answer differs from A3; existing records mix metals (report counts before migrating, and re-check past receipts as 05 §G.3 advises).

### W1-09 DATEV/lexoffice export correctness `[money]`
- **Objective:** the accountant receives only issued invoices, each on the account for its VAT rate (BE-13).
- **In scope:** `services/accounting_export_service.py`, the export handler in `api/routers/invoices.py`, `core/config.py` (`DATEV_REVENUE_ACCOUNTS: dict[float, str]`).
- **Tests first** (`tests/unit/test_accounting_export.py`, new; no test exists for this service today): DRAFT and CANCELLED are excluded by default; a 7% invoice uses the 7% account; a rate with no mapped account raises a clear error; a cancelled previously exported invoice is emitted as a reversal booking; the created date is computed per call (freeze time twice, two different values).
- **Verify:** `poetry run pytest -q tests/unit/test_accounting_export.py`; `cd src && poetry run mypy goldsmith_erp/services/accounting_export_service.py --ignore-missing-imports`.
- **Assumption:** only `19 -> "8400"` is known from the code; other accounts come from the Steuerberater (D-02).
- **Stop if:** reversal booking format is unclear for lexoffice; ship DATEV first and report.

### W1-10 Immutable invoice snapshot; erasure keeps statutory records `[money]` `[gdpr]`
- **Objective:** an issued invoice never changes after the fact, and a GDPR erasure no longer destroys records that tax and AML law require (GDPR-01, BE-23).
- **In scope:** `db/models.py` (Invoice: `recipient_snapshot` JSON, `seller_snapshot` JSON, `service_date`, `issued_at`, `issued_pdf_path`, `issued_pdf_sha256`; `restricted_until` on invoices, accepted quotes and scrap gold), one migration with a backfill from current customer data, `services/invoice_service.py`, `api/routers/invoices.py` (PDF from snapshot, stored PDF after SENT), `services/pdf_service.py`, `services/customer_service.py` (`SCRUBBABLE_FIELDS`), `services/file_erasure_service.py`, `api/routers/customers.py` (erase response).
- **Out of scope:** §14 seller fields from workshop settings (W2-04 fills `seller_snapshot`); backup ledger (W5-05); retention sweep execution (W5-07).
- **Assumption A4 (D-06):** JSON snapshot at creation; frozen PDF and SHA-256 at SENT; write-once. Retention defaults: invoices and Buchungsbelege 8 years (BEG IV, verify), Altgold ID/receipt records 5 years (GwG §8 Abs. 4), accepted quotes 6 years (§257 HGB). Alternative: snapshot at SENT only.
- **Tests first:**
  - `tests/integration/test_invoice_snapshot.py`: create invoice, change the customer's address, the PDF shows the old address; after SENT the PDF bytes hash to `issued_pdf_sha256`; after `anonymize_customer` the invoice PDF still shows the original name.
  - `tests/integration/test_gdpr_erasure_keeps_statutory_records.py`: erase a customer with an invoice, an accepted quote and a SIGNED Altgold record: invoice notes and line descriptions unchanged, signatures present, receipt PDF file exists, contact fields scrubbed, response lists retained categories with "Art. 17(3)(b)".
  - Update `tests/unit/test_gdpr_customer_erasure.py` and `tests/integration/test_gdpr_erasure_with_files.py` where they assert the old over-deletion.
- **Verify:** the tests above on SQLite and on PG (`TEST_DATABASE_URL=...`); migration round trip on PG; `cd src && poetry run mypy goldsmith_erp/services/customer_service.py goldsmith_erp/services/invoice_service.py --ignore-missing-imports`.
- **Stop if:** the backfill finds invoices whose customer is already anonymized (report the count; they cannot be restored and need a note in the Art. 30 record).

### W1-11 Metal consumption accumulates; AVERAGE draws across batches `[money]`
- **Objective:** material cost and weight on an order reflect every consumption, and AVERAGE costing works across batches (BE-07, BE-08).
- **In scope:** `services/metal_inventory_service.py`, `services/cost_calculation_service.py`.
- **Tests first** (`tests/unit/test_metal_inventory_service.py`): consume 12 g 750 (780.00) then 1.5 g (97.50): `material_cost_calculated == 877.50`, `actual_weight_g == 13.5`; AVERAGE with batch A 10 g and batch B 100 g, consume 50 g: succeeds, A remaining 0, B remaining 60, price at the weighted average; cost preview with recorded usage does not allocate from remaining stock.
- **Verify:** `poetry run pytest -q tests/unit/test_metal_inventory_service.py tests/unit/test_cost_calculation_service.py`; PG `TEST_DATABASE_URL=... poetry run pytest -q tests/integration/test_concurrent_metal_consumption.py` (these tests are skipped on SQLite).
- **Stop if:** reversal of a usage is needed to correct history (not in scope; report).

### W1-12 Stop the customer-email loop; one message per event `[gdpr]`
- **Objective:** enabling `EMAIL_NOTIFICATIONS_ENABLED` sends each customer exactly one message per real event, with customer-facing text only, and repair notifications respect roles (BE-09, DOM-10, BE-21, GDPR-13, VER-01, VER-02).
- **In scope:** `services/notification_service.py`, `services/system_monitor.py`, `services/email_service.py`, `services/repair_service.py` (`_notify_admins_repair_ready`), `db/models.py` plus migration (dedupe key UNIQUE on notifications), email templates.
- **Out of scope:** the outbox and CustomerMessage module (W6-01, W6-02); repair customer updates UI (W2-02); advisory-lock leader election (W3-10).
- **Assumption A5 (D-07):** until W6-02, a reminder's customer email is recorded as a CustomerUpdate row (visible in Kundeninfo) and sent at most once per order event; staff notifications never email customers themselves.
- **Tests first:**
  - `tests/unit/test_notification_dedup.py`: 3 staff users, order COMPLETED 4 days ago, `check_pickup_reminders` run 3 times with notifications marked read in between: exactly 1 customer email (mock `EmailService`) and at most 1 staff notification per user per day; fitting reminder email contains the real fitting date, not the staff message.
  - `tests/unit/test_notification_dedup.py::test_customer_email_never_contains_internal_message`: REPAIR_RECEIVED email body does not contain `notification.message`.
  - `tests/unit/test_repair_ready_notifications.py`: only ADMIN and GOLDSMITH receive the repair-ready notification; `_publish_notification` is called.
  - `tests/unit/test_system_monitor.py`: an exception in `check_low_stock_alerts` does not stop `pickup_reminders` in the same cycle.
  - `tests/integration/test_reminder_single_email.py` (PG): two concurrent scanner runs produce one notification per key and one email.
- **Verify:** the tests above; PG run for the integration test; migration round trip.
- **Stop if:** V1.2 behaviour depends on the implicit customer email for a type not listed in `_CUSTOMER_EMAIL_TYPES`.

### W1-13 Customer portal route outside the staff providers
- **Objective:** a customer with no cookie can open `/portal` without being sent to the staff login (FE-01).
- **In scope:** `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/pages/CustomerPortalPage.test.tsx`, new `frontend/e2e/portal-unauthenticated.spec.ts`.
- **Out of scope:** portal content, token route and polish (W6-07); the full PublicShell refactor (W3-01).
- **Tests first:**
  - `CustomerPortalPage.test.tsx`: render the real `<App/>` routes at `/portal` with MSW returning 401 for `/users/me` and `/refresh`: the lookup form is visible after the effects settle, `window.location` is unchanged, and no request to `/users/me`, `/time-tracking/running` or `/activities` is made.
  - `src/api/client.test.ts`: a 401 on `/refresh` while `pathname` starts with `/portal` does not redirect.
  - `e2e/portal-unauthenticated.spec.ts`: fresh context, open `/portal`, expect the lookup form after 2 s and the URL still `/portal`.
- **Verify:** `cd frontend && yarn vitest run src/pages/CustomerPortalPage.test.tsx src/api/client.test.ts && npx tsc --noEmit && npx playwright test e2e/portal-unauthenticated.spec.ts`.
- **Stop if:** another public route exists that needs the same treatment (list it).

### W1-14 Honest bench session `[gdpr]`
- **Objective:** the timer shows the truth for the logged-in user, nothing personal survives logout on a shared tablet, and the UI no longer promises pause or offline sync it does not do (FE-07, FE-10, FE-11, FE-19, FE-09).
- **In scope:** `frontend/src/contexts/TimeTrackingContext.tsx`, `frontend/src/contexts/AuthContext.tsx`, `frontend/src/components/TimerWidget.tsx`, `frontend/src/components/OfflineIndicator.tsx`, `frontend/vite.config.ts`.
- **Out of scope:** server-side pause (W2-14); offline queue (W7-03); banner z-index (W4-01).
- **Tests first:**
  - `src/contexts/TimeTrackingContext.test.tsx` (new): mount logged out, log in, a running entry from MSW is shown; log out: no `/time-tracking/running` call during the next 30 s of fake time; `localStorage` has no `running_time_entry`, `scanner_last_activity_id` or `user`; `caches.delete` was called for the API cache names.
  - `src/components/TimerWidget.test.tsx`: no "Pause" control; stopping via the widget stops context polling.
  - `src/components/OfflineIndicator.test.tsx`: offline text is "Offline: Änderungen werden nicht gespeichert".
- **Verify:** `cd frontend && yarn vitest run src/contexts src/components/TimerWidget.test.tsx src/components/OfflineIndicator.test.tsx && npx tsc --noEmit && node node_modules/vite/bin/vite.js build && ! grep -q "api/v1/orders" dist/sw.js` (the last command exits 0 when the route is gone).
- **Stop if:** removing Pause conflicts with an owner decision (D-15).

### W1-15 QR bench flow works on a fresh device
- **Objective:** scanning a label and tapping "Timer starten" works on a device that has never started a timer, and repair scans never touch an order (FE-02, FE-03, FE-04).
- **In scope:** `ScanOverlay.tsx`, `ActionHandlers.ts`, `QuickActionModalV2.tsx`, scanner route map, `frontend/src/test/{ActionHandlers.test.ts,QuickActionModalV2.test.tsx,Slice11PrimaryScenario.test.tsx,ScanOverlay.test.tsx}`.
- **Out of scope:** reading `?action=` on OrderDetailPage (W2-01); time entries on repairs (W6-04).
- **Tests first:**
  - `ActionHandlers.test.ts` with an empty `localStorage`: choosing an activity in the quick-action step then "Timer starten" posts `/time-tracking/start` with that `activity_id`.
  - Same file: for a repair entity, take-photo navigates to the repair (not `/orders/{id}`), print-label uses the repair label route, and no `start_timer` action is offered.
  - `QuickActionModalV2.test.tsx`: a backend action with no handler (for example `add_note`) renders no button; `open_entity` for a metal purchase goes to an existing route.
  - Remove the `scanner_last_activity_id` pre-seed from `ActionHandlers.test.ts` and `Slice11PrimaryScenario.test.tsx`; both must still pass.
- **Verify:** `cd frontend && yarn vitest run src/test/ActionHandlers.test.ts src/test/QuickActionModalV2.test.tsx src/test/Slice11PrimaryScenario.test.tsx src/test/ScanOverlay.test.tsx && npx tsc --noEmit`.
- **Stop if:** `activitiesApi.getMostUsed` is not user-scoped on the backend (then use the last-used activity from the server and report).

### W1-16 Estimator cost consistent with the shown median `[money]`
- **Objective:** the labor price the estimator offers matches the hours it shows (BE-10).
- **In scope:** `src/goldsmith_erp/ml/labor_estimator.py`, `src/goldsmith_erp/services/estimator_service.py`.
- **Assumption A6 (D-09):** price at `hours_p50 x blended rate`; suggested activities zero-filled across the matched set, included only when present in at least 50% of orders. Memory notes two pending estimator design decisions for Max; this is one of them.
- **Tests first** (`tests/unit/test_labor_estimator.py`, `tests/unit/test_estimator_service.py`): five rings each Polieren 1.0 h, one also Gravur 2.0 h: `hours_p50 == 1.0`, `labor_cost_p50 == 75.00` at rate 75 (today 225.00), Gravur not suggested; the sum of suggested hours is within 10% of `hours_p50`; P20/P80 scale from the corrected base.
- **Verify:** `poetry run pytest -q tests/unit/test_labor_estimator.py tests/unit/test_estimator_service.py tests/integration/test_estimator_endpoints.py`.
- **Stop if:** Max has already decided the cost basis differently.

### W1-17 One running timer per user; sane time edits; owner checks
- **Objective:** a double tap cannot create two running timers, corrections cannot produce negative time, and one goldsmith cannot edit another's hours (BE-12, BE-18, SEC-13).
- **In scope:** one migration (partial unique index, PG and SQLite forms), `services/time_tracking_service.py`, `models/time_entry.py`, `api/routers/time_tracking.py`.
- **Tests first:**
  - `tests/integration/test_one_running_timer.py` (PG): two concurrent `POST /time-tracking/start` for one user (two sessions, `asyncio.gather`): exactly one entry with `end_time IS NULL`, the other request 409.
  - `tests/unit/test_time_tracking_service.py`: a second sequential start returns 409; `get_running_entry` never raises `MultipleResultsFound`.
  - `tests/unit/test_time_entry_validation.py`: `TimeEntryUpdate` with end before start is 422; longer than 24 h is 422; `duration_minutes` together with `end_time` is 422; PUT with `end_time` on a running entry runs the stop flow.
  - `tests/integration/test_time_tracking_permissions.py`: GOLDSMITH B stopping, editing or interrupting A's entry gets 403; ADMIN succeeds.
- **Verify:** the tests above on SQLite and PG; migration round trip on PG.
- **Stop if:** production data already contains users with two open entries (the migration would fail): report counts and propose closing the older one.

### W1-18 Escaped labels, bounded image decoding, EXIF stripped `[gdpr]`
- **Objective:** printable labels cannot carry injected HTML, image uploads cannot exhaust memory, and stored photos carry no GPS (SEC-07 incl. F-3, SEC-18, GDPR-19 incl. F-9).
- **In scope:** `services/label_service.py`, `middleware/security_headers.py` (CSP hash for the label print script), `services/image_validation.py`, `services/photo_service.py`, `services/repair_photo_service.py`, `services/consultation_photo_service.py`, `core/config.py` (`LABEL_PRINT_FULL_NAME: bool = False`).
- **Tests first:**
  - `tests/unit/test_label_service.py` (new): an order title `<form action=/x><button>Drucken</button></form>` renders as escaped text; the print script is allowed by the CSP hash; customer name prints as initials by default.
  - `tests/unit/test_image_validation.py` (new): a PNG over 40 Mpx is rejected; a JPEG with GPS EXIF is stored without EXIF (`Image.open(path).getexif()` is empty).
- **Verify:** `poetry run pytest -q tests/unit/test_label_service.py tests/unit/test_image_validation.py tests/unit/test_repair_photo_service.py tests/unit/test_consultation_photo_service.py`.
- **Stop if:** the print flow needs a static file mount (that touches `main.py`; serialize and report).

### W1-19 Credential changes need the current password; roles assignable `[auth]`
- **Objective:** an unattended session cannot take over an account, and ADMIN can set roles without SQL (SEC-11, SEC-F6).
- **In scope:** `api/routers/users.py`, `models/user.py`, `services/user_service.py`, `services/email_service.py` (notice to the old address), `frontend/src/pages/UsersPage.tsx`, `frontend/src/api/users.ts`.
- **Tests first:**
  - `tests/integration/test_users_me_reauth.py`: `PUT /users/me` with a new password and no `current_password` is 422; a wrong one is 403; the right one is 200, writes an audit row and triggers one email to the old address (mocked).
  - `tests/integration/test_role_assignment.py`: ADMIN sets `role="goldsmith"` (200, audit row); GOLDSMITH trying it gets 403; demoting the last ADMIN is 409.
- **Verify:** the tests above; `cd frontend && yarn vitest run src/pages && npx tsc --noEmit`.
- **Stop if:** the live DB shows roles were set by SQL outside audit (report; no data change in this item).

### W1-20 No PII or tokens in request logs `[gdpr]`
- **Objective:** request logs contain paths and safe parameters only (SEC-05, GDPR-10).
- **In scope:** `src/goldsmith_erp/middleware/logging.py`.
- **Tests first** (`tests/unit/test_logging_redaction.py`): `GET /api/v1/customers/search?q=Sentinelname` produces log records (caplog) that contain `/customers/search` and not `Sentinelname`; `GET /api/v1/portal/status/abc123` is logged as `/api/v1/portal/status/***`; allow-listed keys (`limit`, `offset`, `status`) still appear.
- **Verify:** `poetry run pytest -q tests/unit/test_logging_redaction.py`; `cd src && poetry run mypy goldsmith_erp/middleware/logging.py --ignore-missing-imports`.
- **Stop if:** another middleware or the access log also logs full URLs (list it; uvicorn access logs may need `--no-access-log` or a filter).

---

## 4. Dependencies and parallelism

### 4.1 Between waves

```
            +-----------------------------+
            | W1 Stop the bleeding (20)   |
            +--------------+--------------+
                           | CP-1 review, merge to main
                           v
            +-----------------------------+        +------------------------------+
            | W2 Product for the goal (16)|        | W5 docs/hygiene items that   |
            +--------------+--------------+        | touch no app code (W5-10,    |
                           | CP-2 review           | W5-11, W5-13) may run from   |
                           v                       | W1 onwards in a docs lane    |
            +-----------------------------+        +------------------------------+
            | W3 Platform (11)            |
            +------+---------------+------+
                   |               |
                   v               v
   +-------------------------+   +--------------------------------+
   | W4 Design system (10)   |   | W5 Ops, CI, compliance (13)    |
   | needs W3-04 primitives, |   | W5-06 needs W3-11; W5-12 needs |
   | W2-03/W2-07 for status  |   | W3-10; W5-01/W5-02 need a quiet|
   +-----------+-------------+   | package.json window            |
               |                 +----------------+---------------+
               +--------------+-------------------+
                              v
            +-----------------------------+
            | W6 Target architecture (7)  |  needs W3-10, W3-11, W5-10 (docs for the channel)
            +--------------+--------------+
                           v
            +-----------------------------+
            | W7 Backlog (6)              |  items start as soon as their own dependencies land
            +-----------------------------+
                           | CP-3 review before the final merge to main
```

W4 and W5 run in parallel lanes after W3 (they share only `package.json`, which is serialized: W5-01 and W5-02 go first, then W4-09).

### 4.2 Serial chains (never run two items of one chain at once)

| Shared resource | Chain (in merge order) |
|---|---|
| Alembic migrations and `db/models.py` | W1-17, W1-12, W1-05, W1-08, W1-10, then W2-07, W2-04, W2-10, W2-06, W2-12, W2-14, W2-16, then W3-11 (alone, all other work paused), then W5-06, W6-01, W6-02, W6-03, W6-04, W6-05, W7-01 |
| `main.py` | W1-03, then W2-13, W2-03, W2-06, then W3-07, W3-10, then W5-01, W5-12, then W6-07 |
| `frontend/src/types.ts` | W1-05, W1-08, then W2-06, W2-10, then W3-02 (after which types are generated) |
| `package.json` (front and back lockfiles) | W3-02, W3-03, W3-05, W3-06, then W5-01, W5-02, then W4-09 |
| `services/invoice_service.py` | W1-06, W1-07, W1-08, W1-10, then W2-04, then W3-11, then W7-02 |
| `api/routers/customers.py` | W1-04, W1-05, W1-10, then W5-08 |
| `core/config.py` (additive fields only) | develop in parallel, merge in order W1-01, W1-03, W1-09, W1-18, each rebased on the previous |
| `podman-compose.prod.yml` | W1-02, W1-03, then W5-12, then W6-01 |
| `OrderDetailPage.tsx` | W2-01, W2-08, W2-09, W2-11, then W4-05 |

### 4.3 Recommended schedule and maximum concurrent agents

| Wave | Max agents at once | Batches (items in a batch run concurrently) |
|---|---|---|
| 1 | 6 | B1: W1-01, W1-06, W1-17, W1-13, W1-14, W1-15. B2: W1-02, W1-04, W1-07 (after W1-06), W1-11, W1-12 (after W1-17 merged), W1-20. B3: W1-03 (after W1-01, W1-02), W1-05 (after W1-04, W1-12), W1-09, W1-16, W1-18, W1-19. B4: W1-08 (after W1-07, W1-05). B5: W1-10 (after W1-08). Adversarial rounds run as soon as each tagged item is green, in a separate agent slot. |
| 2 | 5 | B1: W2-07, W2-01, W2-02, W2-05, W2-15. B2: W2-04, W2-08, W2-13. B3: W2-03, W2-09, W2-10. B4: W2-06, W2-11, W2-12. B5: W2-14, W2-16. |
| 3 | 4 | B1: W3-01, W3-04, W3-07, W3-09. B2: W3-02, W3-10. B3: W3-03, W3-06, W3-08. B4: W3-05. B5: W3-11 alone. |
| 4 | 4 | W4-01, then W4-02 with W4-03, then W4-04, then W4-05, W4-06 and W4-07 page PRs (one page per agent), then W4-08, W4-09, W4-10. |
| 5 | 5 | B1: W5-01, W5-03, W5-05, W5-09, W5-13. B2: W5-02, W5-04, W5-07, W5-08. B3: W5-06, W5-12. W5-10 and W5-11 run in the docs lane from Wave 1. |
| 6 | 2 | W6-01, W6-02, W6-03, W6-04, W6-05 strictly in order; W6-06 alongside W6-03; W6-07 last and only if D-03 is yes. |
| 7 | 3 | Start each item once its dependency lands. |


### 4.4 Wave 1 file-conflict matrix

`X` = the item edits the file. Two items with an `X` in the same row must not be in flight at once unless the row says "merge order".

| File | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `db/models.py` + migration | | | | | X | | | X | | X | | X | | | | | X | | | |
| `main.py` | | | X | | | | | | | | | | | | | | | | | |
| `core/config.py` (merge order) | X | | X | | | | | | X | | | | | | | | | X | | |
| `podman-compose.prod.yml` | | X | X | | | | | | | | | | | | | | | | | |
| `frontend/src/types.ts` | | | | | X | | | X | | | | | | | | | | | | |
| `services/invoice_service.py` | | | | | | X | X | X | | X | | | | | | | | | | |
| `api/routers/invoices.py` | | | | | | X | | | X | X | | | | | | | | | | |
| `api/routers/customers.py` | | | | X | X | | | | | X | | | | | | | | | | |
| `services/customer_service.py` | | | | | X | | | | | X | | | | | | | | | | |
| `services/pdf_service.py` | | | | | | | | X | | X | | | | | | | | | | |
| `services/quote_service.py` | | | | | | | X | | | | | | | | | | | | | |
| `core/permissions.py` | | | | X | | | | | | | | | | | | | | | | |
| `services/repair_service.py` | | | | | | | | | | | | X | | | | | | | | |
| `api/routers/repairs.py` | | | | X | | | | | | | | | | | | | | | | |
| `services/email_service.py` | | | | | | | | | | | | X | | | | | | | X | |
| `frontend/src/App.tsx`, `api/client.ts` | | | | | | | | | | | | | X | | | | | | | |
| `contexts/*`, `TimerWidget.tsx`, `vite.config.ts` | | | | | | | | | | | | | | X | | | | | | |
| scanner components | | | | | | | | | | | | | | | X | | | | | |

Reading the matrix: W1-05, W1-08, W1-10, W1-12 and W1-17 are one serial chain because of migrations; W1-06, W1-07, W1-08 and W1-10 share `invoice_service.py`; W1-04, W1-05 and W1-10 share `customers.py`; W1-12 and W1-19 both touch `email_service.py` in different functions and may run together if they rebase before merge. Everything else in Wave 1 is independent.

---

## 5. Definition of done and review checkpoints

**The programme is done when:**
1. Every row in [FINDINGS-REGISTER.md](FINDINGS-REGISTER.md) is `fixed (<sha>)`, or `accepted` with a one-line reason signed off by the owner (Anne or Max). No CRITICAL or HIGH row is `accepted` without a written risk note.
2. On `audit/2026-09-fixes`: backend suite green on SQLite and the PG integration job; `migration-smoke` green; mypy, black, isort, bandit, ruff green; frontend Vitest, `tsc --noEmit` and ESLint green; all Playwright specs (the existing six plus the new portal, a11y and fresh-device QR specs) green in CI.
3. Coverage does not fall below today's backend 68%; every new module has at least 80% line coverage (CLAUDE.md testing rule); the frontend has a measured baseline and threshold (W5-02).
4. Every decision in section 6 is answered and recorded in an ADR under `docs/adr/` or in the Art. 30 record.
5. A live run on the demo stack passes the "life of a ring": consultation, quote with estimator, Versenden, conversion without retyping, photo from the scanner, status changes with a milestone update, handover PDF, invoice with correct VAT and an Altgold credit, DATEV export; plus the QR timer flow on a fresh device and the portal (if enabled) with no cookie.
6. Compliance documents (W5-10) are reviewed by Anne, and the items marked "verify" are confirmed by the Steuerberater or a lawyer.

**Programme risks and mitigations:**

| Risk | Where | Mitigation |
|---|---|---|
| Money migrations change historic numbers | W1-07, W1-08, W3-11 | Rehearse on a production dump; compare invoice totals before and after; keep issued invoices frozen (W1-10 lands before W3-11) |
| An erasure change deletes or keeps the wrong data | W1-10, W5-05, W5-07 | `[gdpr]` adversarial round; dry-run output reviewed by Anne; restore drill in W5-05 |
| Parallel agents collide on shared files | all waves | Section 4.2 chains and the 4.4 matrix; one migration in flight at a time; rebase before every merge |
| Tests pass while the browser flow fails (as with FE-01 and FE-02) | frontend items | Render tests through the real router and providers; a Playwright spec for every headline flow; no localStorage pre-seeding in tests |
| SQLite-only green hides PostgreSQL failures | migrations, locks, tz | Every `FOR UPDATE`, partial index and tz item runs its test under `TEST_DATABASE_URL` on PG before merge |
| Owner decisions arrive late | section 6 | Items proceed on the stated default and stop only when a default is overturned |

**Checkpoints where the owner runs `/code-review ultra`** (user-triggered cloud review) on the integration branch:

| Checkpoint | When | Scope | Gate |
|---|---|---|---|
| CP-1 | After all 20 Wave 1 items have merged into `audit/2026-09-fixes` | `git diff main...audit/2026-09-fixes` | No CRITICAL or HIGH review finding open; then merge the integration branch into `main` so the security and money fixes ship early |
| CP-2 | After Wave 2 | Diff since CP-1 | Same gate; the owner does a hands-on session with Anne on a tablet (05 §F definitions of done) |
| CP-3 | Before any later merge of the integration branch into `main` (at the latest at programme end) | Diff since the last merge to `main` | Same gate plus the programme definition of done above |

---

## 6. Open decisions and the defaults this plan assumes

Each decision names who should answer it. The plan proceeds on the default; an item whose assumption is overturned stops and is re-planned.

| ID | Decision (question) | Default assumed | Alternative | Who | Affects |
|---|---|---|---|---|---|
| D-01 | Is `Order.price` the gross Endpreis or a net price? | **Implemented 2026-09-25 as NET** (docs/architecture/ADR-2026-09-25-price-semantics.md): `Order.price` excludes VAT, quote conversion writes `quote.subtotal`, cost calculation writes net, the invoice adds 19% on top. Reversible to gross if Anne/Max prefer, but all paths must change together | Net; conversion stores the quote subtotal | Anne, Max (issue #28) | W1-07, W2-05, W3-11 |
| D-02 | How is an Altgold trade-in treated for VAT, and which revenue accounts apply per rate? Is a Kleinunternehmer (§19) or §25a switch needed? | Post-tax deduction with its own Ankaufbeleg; VAT on the full sale; only account 8400 (19%) known; no §19/§25a switch until asked | Netting before VAT if the Steuerberater allows it | Steuerberater | W1-08, W1-09, W2-04 |
| D-03 | Build the internet-reachable token status page? | No for now: email and PDF first (vision decision); portal router off by default; mails carry a signed link that falls back to "reply by email" | Build W6-07 after its GDPR preconditions E9 to E13 | Anne, Max | W1-03, W1-13, W6-07 |
| D-04 | Keep the VIEWER role? Add an APPRENTICE role? Which role does Anne use day to day? | Keep VIEWER, made safe by W1-04; create no VIEWER accounts until W1-04 lands; no APPRENTICE until apprentices get accounts; Anne's home is the "Heute" work view whatever her role | Remove VIEWER; add APPRENTICE now | Anne, Max | W1-04, W2-03, W7-01 |
| D-05 | What consent wording covers allergy notes, and may the reason be stored at all? | Explicit consent per purpose, wording version `v0-draft` until approved; withdrawing consent clears the allergy field | Store only a material restriction ("kein Nickel verwenden"), no health reason | lawyer, Anne | W1-05 |
| D-06 | What is the immutable invoice snapshot, and how long are records kept? | JSON snapshot at creation, frozen PDF plus SHA-256 at SENT; invoices 8 years, accepted quotes 6, Altgold/GwG records 5 | Snapshot at SENT only; 10-year retention | Steuerberater | W1-10, W5-07 |
| D-07 | Until the CustomerMessage module exists, how do reminder emails reach customers? | At most one per order event, recorded as a CustomerUpdate row visible in Kundeninfo; staff notifications never email customers | Turn automatic customer emails off entirely until W6-02 | Max | W1-12 |
| D-08 | Retention schedule per table, and when may the sweep delete for real? | The starting points in GDPR-08; `RETENTION_EXECUTE=1` only after written sign-off | Keep dry-run longer | Anne with a DPO or lawyer | W5-07 |
| D-09 | Estimator cost basis (one of the two pending estimator decisions) | `hours_p50 x blended rate`; activities zero-filled, included at 50% presence | Per-activity medians shown as a breakdown, not summed | Max | W1-16 |
| D-10 | How strict is the hallmark check? | Soft gate: allowed Feingehalt from the alloy, or "nicht punziert (Grund)"; the unused OrderHallmark register is dropped from UI plans | Keep the hard gate with a wider vocabulary | Anne | W2-09 |
| D-11 | May customers exist without an email address? | Yes; unique only when present; updates fall back to PDF | Keep email mandatory | Anne | W2-10 |
| D-12 | Do orders get a human-facing Auftragsnummer before production? | Yes, from the same per-year counter table as invoices (W2-04) | Keep the database ID | Anne | W2-04 |
| D-13 | How far does the Art. 15 design-IP exclusion go? | Disclose customer-supplied facts (`wishes`, `source_material`); withhold only the goldsmith's own design work | Blanket exclusion as today | lawyer | W5-08 |
| D-14 | Design system choices: Tailwind or plain CSS; typeface; dark mode or high-contrast mode | Plain CSS plus tokens (design report I-25; the playbook leaves this to Max); IBM Plex as proposed by the playbook; ask Anne whether the problem is darkness or glare before W4-10 | Keep Tailwind `@theme`; system fonts; build both modes | Max, Anne | W4-01, W4-03, W4-09, W4-10 |
| D-15 | Should the timer have a Pause? | Removed in W1-14; re-added in W2-14 as a server interruption only if Anne wants it | Keep Pause as a local display toggle with an explicit label | Anne | W1-14, W2-14 |
| D-16 | GwG identification for Altgold cash purchases: threshold and fields? | Optional ID fields, required above a configurable cash threshold, default 2,000 EUR (verify §10 Abs. 6a GwG) | Always required | Steuerberater or lawyer | W2-16 |
| D-17 | Pull the one critical dependency bump (anyio) forward into Wave 1? | Policy keeps OPS-06 in Wave 5; the plan recommends allowing a one-line anyio bump early if CI stays green | Wait for W5-01 | Max | W5-01 |
| D-18 | Error tracking: hosted Sentry, self-hosted GlitchTip, or none? | Self-hosted GlitchTip with PII scrubbing (data residency) | Hosted Sentry with an AVV; none | Max | W5-12 |
| D-19 | Who is the controller in the Art. 30 record? | Anne's workshop is the controller; Max, if he operates the system, is her processor with an AVV; no conflicted DPO | Keep Max as controller (not recommended by 07 §H.1) | Anne, Max | W5-10 |
