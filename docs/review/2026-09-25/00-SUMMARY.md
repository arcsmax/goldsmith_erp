# Audit Summary: Goldsmith ERP, September 2026

- **Date:** 2026-09-25
- **Code audited:** `main` @ `73fff19` (last commit 2026-07-26; the repository was dormant for about
  two months before this audit).
- **State of `main`:** green. 1805 backend tests pass (6 skipped, 1 xfailed), 485 frontend tests
  pass; mypy, black, isort, bandit and `tsc --noEmit` exit 0. Backend line coverage is 68%. mypy
  passes under a per-module baseline that suppresses 1,532 errors across 96 modules (06 OPS-03). All
  July 2026 remediation branches were squash-merged.
- **Product goal (owner's words):** "make it easier and faster for a goldsmith to keep track of
  their work and clients, and enable the clients to get better feedback on their jewelry."
- **Documents:** this summary; [FINDINGS-REGISTER.md](FINDINGS-REGISTER.md) (212 findings);
  [MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md) (83 fix items in 7 waves); the eight reviews 01 to 08;
  `docs/design/UI-UX-PLAYBOOK.md`.

---

## Execution status (2026-09-25)

- **Findings:** 107 fixed, 42 partial, 63 open (of 212 total; see [FINDINGS-REGISTER.md](FINDINGS-REGISTER.md)).
- **Waves:** 1 and 2 complete (all items landed, several partial); Wave 3 mostly landed (W3-11's Numeric/tz migration still running); Wave 5 mostly landed; Wave 6's outbox, CustomerMessage and status-report items landed; Wave 4 has its design-token and component-primitive foundation only, no page migrated yet; Wave 7 is backlog except for opportunistic hygiene fixes (see [MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md) section 0).
- **Latest gate:** backend 4125 tests passed, frontend 918 tests passed, `tsc --noEmit` and `mypy` clean; ESLint has 5 errors remaining, all in `OrderFormModal.tsx` — the sole blocker to a fully green `yarn lint`.
- Two live click-through verification passes against the running stack (Playwright screenshots, real Postgres/Redis) found and fixed 21 then 8 further UI/backend issues (LV-01..21, LV2-01..08).
- Integration branch `audit/2026-09-fixes`; **PR #51 (draft)** is the review vehicle — run `/code-review ultra` on it before treating this branch as a release candidate.
- Full changelog, decisions needing sign-off and the open-follow-ups list: [PROGRESS.md](PROGRESS.md).

---

## (a) Verdicts on the owner's four questions

**Is it fit for the goal?** Not yet, but the gap is mostly wiring, not missing features. Most of
Anne's own Ideensammlung is built (05 §B): QR labels and the scanner, the timer with interruptions,
handoffs, the calendar Ampel, Soll/Ist and Arbeitszettel follow a real workshop day, and the
consultation wizard with no-go capture is better than typical DACH tools. What is missing is the
connective tissue that turns this into "faster" and "better feedback". No screen can add a photo to
an order, so the carefully built photo updates for customers have nothing to send (DOM-01/FE-13).
The QR timer dead-ends on every fresh device (FE-02) and repair scans open the order with the same
number (FE-03). The customer portal sends customers to the staff login (FE-01). The dashboard ranks
overdue work lowest and shows "alles erledigt" when loading fails (FE-05/DOM-14), and lists quietly
drop jobs older than the newest 100 (FE-06). Data typed in the consultation is dropped at conversion
and typed again (DOM-03, DOM-11b). The money path is wrong in both directions: a converted quote is
billed with VAT twice (1,190.00 becomes 1,416.10, BE-01), an order with a cost breakdown is billed
at purchase cost without margin (952.00 instead of the agreed 1,332.99, BE-02), and Altgold cannot
be credited at all (BE-03, DOM-19, DOM-20). The moment customer email is switched on, pickup
reminders go out once per staff member per day (DOM-10/BE-09). Waves 1 and 2 of the plan close these
gaps.

**Is the architecture state of the art?** Partly. For a single-workshop business app the deployment
and security primitives are ahead of the norm: rootless Podman, Caddy TLS, non-root containers,
typed settings with production validators, structured JSON logging, backup and restore scripts, a
migration smoke test and a PostgreSQL integration job in CI. The domain core and the frontend data
layer are behind. The architecture scorecard averages about 2.5 of 5 (01 §D). The order lifecycle is
a free-form enum with no transition table, and status history is never written (ARCH-01/BE-06),
which blocks the timeline that customer feedback needs. Order and RepairJob are parallel aggregates,
so every cross-cutting feature is built twice and repairs cannot be invoiced (ARCH-02). A 1,834-line
repository layer is dead code while 32 routers run SQL directly (ARCH-03). `db/models.py` is 3,245
lines with 79 classes (ARCH-09). Background work runs in the web process and is duplicated by
`--workers 2` (ARCH-04). The frontend has no server-state layer and hand-writes 1,285 lines of API
types (ARCH-06, ARCH-07). The recommended target is a modular monolith with a PostgreSQL outbox and
one worker process; the review explicitly rejects microservices, Kubernetes, Celery and a client
state library (01 §E).

**Is it secure?** The foundations are real and verified: deny-by-default auth middleware,
HS256-pinned JWT in HttpOnly SameSite=Strict cookies, token revocation, Fernet encryption with a
blind index on customer PII and valuations, 227 of 243 routes behind an explicit permission plus 2
self-scoped, magic-byte upload validation with path anchoring, and no SQL-injection or XSS sinks
found. No finding gives an unauthenticated remote attacker access in the intended production
deployment (02 §E). It is still not ready for real customer data. The backend boots in production
with the `.env.example` placeholder signing key (live-verified), so anyone on the Wi-Fi can mint an
admin token (SEC-02, CRITICAL). The `setup.sh` install path cannot boot, which pushes operators into
exactly that trap (SEC-F1). A GOLDSMITH account can cancel a paid invoice through the generic edit
endpoint although the role is deliberately denied cancellation (BE-05, CRITICAL). A VIEWER account
reads purchase prices, customer revenue, repair insurance values and design photos (SEC-01, SEC-09,
GDPR-03, GDPR-04). On data protection, erasure destroys invoices and Altgold records that tax and
anti-money-laundering law require the workshop to keep (GDPR-01), and allergy notes are health data
stored without consent and readable by every role (GDPR-02). Wave 1 is days of S and M work, not
weeks.

**What did they miss?** The things the reports flag as easy to overlook, in order of consequence:
1. **The tests are green because they avoid the seams.** Every CRITICAL and HIGH backend finding
   passes CI; no test covers quote to invoice, Altgold to invoice, aware datetimes from the real
   frontend, or concurrent timers (03 §F). The QR flow and the portal pass their unit tests only
   because the tests pre-seed localStorage and render the portal without providers (04 §G).
2. **Switching on customer email is a one-flag risk** (`EMAIL_NOTIFICATIONS_ENABLED=true` triggers
   DOM-10 immediately). Treat DOM-10 as a release blocker for V1.2 going live.
3. **The documented production install does not boot** (SEC-F1), and uploads over 1 MB fail behind
   nginx (SEC-F2). Backup and GDPR-failure alerts never arrive, and off-site sync is silently off
   because of a variable-name mismatch (SEC-F4).
4. **There is no API to assign roles**; new users default to VIEWER, so either roles were set by SQL
   outside the audit trail or VIEWER accounts exist and leak (SEC-F6).
5. **Anne is the data controller, not Max** (07 §H.1), invoice retention is 8 years since BEG IV
   rather than the 10 years in the code (verify), and Altgold cash purchases from 2,000 EUR need GwG
   identification the model cannot store (07 §H.3, DOM-21).
6. **The order "Verlauf" tab shows two timestamps, not a history**; staff may believe history is
   recorded (01 §F.1).
7. **The PWA keeps order prices and customer names in the browser cache after logout** on shared
   tablets (FE-11).
8. **Hallmarking is voluntary in Germany but must be correct if applied**; the current hard gate
   with a narrow vocabulary pushes staff to record a wrong Feingehalt (DOM-22, 05 §G.4).
9. **Anne's likely role (ADMIN) lands on the office KPI dashboard, not the work queue** (04 §G,
   DES-14).
10. **The user guide promises features that do not exist** ("Foto hochladen", "Kunde kann
    Fortschritt sehen", 05 §G.10), and placeholder contact details (`info@goldschmiede.de`, `+49 0
    000 000`) would ship to customers (FE-21).
11. **The verifiers found three things no report had:** repair-ready notifications send the
    customer's name to every active user including VIEWER (VER-01) and skip the live WebSocket
    publish (VER-02); `customer_notified_at` on repairs is written although no one was notified
    (tracked under DOM-12). The backend verifier also showed that BE-05 is an authorization bypass,
    not only a data bug.

---

## (b) Method

- **Audit:** eleven audit agents worked read-only against `main` @ `73fff19` and produced the eight
  reports in this folder: architecture (01), security (02), backend correctness (03), frontend code
  and flows (04), domain and product fit (05), testing, CI and operations (06), GDPR and privacy
  (07), and the design investigation (08). Each report re-checked the previous audits
  (`docs/review/2026-04-23/`, `docs/review/2026-07-26/production-readiness.md`) against the current
  code and records its commands with exit codes.
- **Verification:** three adversarial verification agents re-opened every CRITICAL and HIGH finding
  (and every impact-H domain gap, plus four design claims) at the cited `path:line` and tried to
  refute it. Where a claim was cheap to reproduce they ran it: the double-VAT and missing-margin
  arithmetic, the negative-price `ValidationError`, the aware-datetime `TypeError`, a passing
  scratch pytest that cancels a PAID invoice via PUT, `Settings()` booting with the placeholder key,
  the numeric-alloy 422, the WCAG contrast ratios and the `yarn build` exit codes.

| Verifier | Scope | Confirmed | Partial | Refuted | Severity changes and new items |
|---|---|---|---|---|---|
| Security and GDPR | 02, 07 | 11 | 0 | 0 | SEC-02 HIGH to CRITICAL; ANONYMIZATION_SALT placeholder boots with no warning at all (folded into SEC-02) |
| Backend and architecture | 03, 01 | 19 | 0 | 0 | BE-05 HIGH to CRITICAL (authorization bypass: GOLDSMITH holds INVOICE_EDIT, not INVOICE_DELETE); BE-09 noted as dormant until email is enabled |
| Frontend, domain and design | 04, 05, 08 | 32 | 1 | 0 | FE-13 MEDIUM to HIGH (same defect as DOM-01); DOM-10 called effectively release-blocking; hex count recounted as 1,563/219 vs 1,580/223 (the partial); three new issues (VER-01, VER-02, DOM-12 sharpening) |
| **Total** | | **62** | **1** | **0** | |

- **Corrected severities** override the report severities everywhere in these documents.
- **Not separately verified:** MEDIUM and LOW findings, and the testing/ops report, whose metrics
  were produced by executing the suites.

---

## (c) The 12 findings that matter most

| Rank | ID(s) | What is wrong, in plain words | Why it matters for the goal | Wave |
|---|---|---|---|---|
| 1 | SEC-02 | If the server is set up by copying the example settings file, it runs with a signing key that is published on GitHub, and anyone on the workshop Wi-Fi can log in as Anne. | Every customer record, price and GDPR export is exposed; the documented setup path leads straight here. | 1 |
| 2 | BE-01, BE-02 | Invoices do not match the agreed price: a converted quote is billed with VAT twice (1,190.00 becomes 1,416.10), and an order with a cost breakdown is billed at purchase cost without the margin (952.00 instead of 1,332.99). | Overcharged customers lose trust; undercharged orders lose money on every piece. | 1 |
| 3 | BE-05 | A goldsmith account can cancel an already paid invoice through the edit endpoint and then bill the order again. | Double billing and a GoBD breach, by a role the system says may not cancel invoices. | 1 |
| 4 | GDPR-01, BE-23 | Deleting a customer on request also wipes the invoice texts, signatures and Altgold receipts the tax office requires; old invoices even change when a customer moves. | A tax audit finds incomplete invoices; the workshop breaks tax law while trying to follow GDPR. | 1 |
| 5 | DOM-10, BE-09 | Once email is switched on, a customer whose piece is ready gets one "abholbereit" email per staff member every day, and another each time staff mark the bell as read. | Spam is the opposite of "better feedback"; it embarrasses the workshop in front of its clients. | 1 |
| 6 | FE-01 | The customer portal sends every customer to the staff login page. | The only customer-facing screen cannot be used. | 1 |
| 7 | FE-02, FE-03 | Starting a timer by scanning the job bag fails on every fresh tablet, and scanning a repair opens (or would book time to) a different order with the same number. | The headline bench feature is a dead end; repair scans show another customer's piece. | 1 |
| 8 | GDPR-02 | Allergy notes are health data, stored without the customer's explicit consent and readable by every role. | Special-category data without a legal basis carries the highest fine tier. | 1 |
| 9 | SEC-01, SEC-09, GDPR-03, GDPR-04 | A front-desk (VIEWER) account can read purchase prices, customer revenue, repair insurance values and design photos. | Breaks the project's own privacy rules and weakens trade-secret protection of designs. | 1 |
| 10 | DOM-19, DOM-20, BE-03, BE-11 | Altgold cannot be added from its tab, silver would be valued at the gold price, an Altgold credit crashes invoicing, and a signed receipt can still be changed. | Real money in every trade-in; signed documents must not change. | 1 |
| 11 | DOM-01, FE-13 | There is no way to add a photo to an order, and existing order photos render broken. | Photos are the heart of "better feedback on their jewelry"; the V1.2 photo updates have nothing to send. | 2 |
| 12 | FE-05, DOM-14, FE-06 | The dashboard ranks overdue work lowest and says "alles erledigt" when loading fails; after about 100 orders, lists and pickers silently drop older jobs and customers. | "Keeping track of work" fails exactly when the workshop is busy. | 2 (FE-06 in 3) |

---

## (d) Scorecards

**Architecture: state of the art for a 2026 single-workshop business app** (condensed from 01 §D;
scores 1 to 5):

| Dimension | Score | In one line |
|---|---|---|
| Layering | 2 | Layers exist, but routers run SQL, services raise HTTP errors, repositories are dead code |
| Domain modeling | 2 | 79 rich entities, but the order lifecycle is unguarded and Order/Repair are duplicated |
| API design | 3 | Versioned, Pydantic on 77% of routes, deny-by-default; no page envelope, no error codes, unbounded limits |
| Data fetching (frontend) | 2 | Hand-rolled fetching in 51 files, client-side filtering over truncated lists, no cache |
| Type safety end to end | 2 | Hand-written `types.ts`, untyped ORM columns, mypy baseline; drift caused live bugs |
| Real-time | 2 | Works for timers and the bell only; per-socket subscribe, no lifespan or heartbeat |
| Background jobs | 3 | systemd timers fit well; in-process monitor duplicated per worker; inline SMTP; no outbox |
| Observability | 2 | Good JSON logs and health endpoints; no error tracking or delivery dashboard |
| Deployment | 4 | Rootless Podman, Caddy TLS, non-root, backups, secret validation; migrate-on-boot is the weak point |
| Testability | 3 | Large suites; SQLite by default vs PG-only features; few DI seams |
| Extensibility | 2 | Every feedback feature hits the lifecycle, job duplication, comms coupling and media first |

Mean about 2.5. Adopt: TanStack Query, generated OpenAPI types, a minimal PG outbox, hand-rolled
state machines, env-based feature flags, Sentry or GlitchTip, a modular monolith with import-linter.
Skip: Celery/arq, OpenTelemetry/Prometheus for now. Reject: microservices, Kubernetes, Zustand/Redux
(01 §D).

**Design: top 5 improvements** (08 §A, confirmed by the verifier where noted):
1. Fix the gold contrast: the primary CTA is white on `#d97706` at 3.19:1 (verifier recomputed
   exactly); move to `#b45309` (5.02:1) and make the focus ring dark at 3:1 or better.
2. One status system: a single `<StatusBadge>` from one token map for all 10 order statuses (6 have
   no style today, verified) plus repair, quote and invoice statuses, always icon plus text.
3. Shared primitives replace the global duplicates: Button, IconButton, Modal (focus trap, Escape,
   no backdrop-dismiss on forms), DataTable or ListCard, EmptyState, PageHeader.
4. Consolidate tokens: spacing, type, radius, shadow and z-index scales plus semantic status
   colours; remove the legacy variable families and the 41 undefined custom properties.
5. Workshop-first shell: bottom tab bar on phones and tablets, grouped navigation, no header
   overflow at 390 px, a visible offline banner, and a bench worklist with the deadline Ampel for
   Anne.

Design verdict in one line: good workshop intent (44 px touch tokens, Werkbank-Modus, scan FAB,
German copy) executed as a patchwork admin template (08 §A). The playbook
`docs/design/UI-UX-PLAYBOOK.md` turns this into rules and a five-phase migration, which Wave 4
follows.

---

## (e) What is good and must be preserved

| Strength | Evidence |
|---|---|
| Deny-by-default authentication with HttpOnly SameSite=Strict cookies, pinned HS256, token revocation with `jti` and a Redis blocklist, 30-minute default tokens | 02 §A, §E; `core/security.py:48-58`, `core/token_revocation.py`, `middleware/auth_required.py` |
| Explicit permission on 227 of 243 routes plus 2 self-scoped; no unguarded mutating route | 02 §B |
| Fernet `EncryptedString` with HMAC blind index on customer PII and valuations; encryption fails loudly | 07 §A, §C; `db/models.py:245-262`, `:2414-2423` |
| A tested order projection for VIEWER (7/7 pass) and a scanner allow-list regression test: the right pattern, to be extended rather than replaced | verify-security-gdpr (commands 7, 8) |
| No SQL built from user input, no `dangerouslySetInnerHTML`, email Jinja with autoescape, magic-byte upload validation with path anchoring | 02 §C "Verified clean" |
| Hardened deployment: Caddy TLS, only the proxy published, non-root containers with `no-new-privileges`, typed settings with production validators | 01 §D (Deployment 4), 02 §E |
| CI with branch protection (7 required checks), a PG integration job, and an Alembic upgrade/downgrade/upgrade smoke test | 06 §A, §B |
| Behavioural tests: 1,812 collected backend tests, about 2.1 asserts per test, real persistence, one documented xfail | 06 §D |
| Well-designed systemd timers for GDPR cleanup, retention and a health watchdog, each with failure alerts (they only need an installer) | 06 OPS-07 |
| V1.2 customer-update pipeline: explicit per-send photo selection, EXIF-stripped email variants, SMTP or PDF delivery, audited | 07 §E E5; 05 §C4 |
| §649 BGB cost watch and change request with recorded response method | 05 §C2 (quality 4) |
| Consultation wizard with no-go and style capture | 05 §C1 |
| Bench layer: QR labels, scanner with quick actions, timer with interruptions, atomic `/switch`, handoffs, calendar Ampel, Soll/Ist, Arbeitszettel | 05 §B, §C3 ("the strongest area"); 04 §D(b) |
| Repair and hallmark services already use explicit transition tables; quotes reject status changes via PUT | 03 §C; `services/repair_service.py:99-113`, `quote_service.py:586-591` |
| Colorblind-safe invoice badges, an accessible ConfirmDialog, a 56 px scan FAB | 08 §D "positive exemplars" |

---

## (f) Status of the July 2026 production-readiness findings

The July audit (`docs/review/2026-07-26/production-readiness.md`) listed 27 numbered findings in
Tiers 0 to 2. Its verdict ("not deployable today", "CI red", "no TLS") is stale: the same-day
remediation sprint fixed Tier 0 and most of Tiers 1 and 2 (06 §G).

| Result | Count | Items |
|---|---|---|
| Fixed | 17 | 0.1, 0.2, 0.3, 0.4, 1.1 (with gaps SEC-06, SEC-F1), 1.2, 1.4, 1.5, 1.6, 1.8, 2.4, 2.7, 2.8, 2.9, 2.11, 2.13 (except OPS-15), 2.14 (with residue OPS-08) |
| Partial | 9 | see below |
| Open | 1 | see below |

Still open or partial:

| July item | Now | Tracked as |
|---|---|---|
| 1.3 GDPR hard-delete never runs | Job and timer exist; install is manual; unit points at the dev compose file; disposition over-deletes tax records | GDPR-16 (W5-03), GDPR-01 (W1-10) |
| 1.7 Dependabot backlog | Down from 1 critical + 34 high to 1 critical + 20 high + 14 medium | OPS-06 (W5-01) |
| 2.1 Token revocation | Code fixed; shipped env files still set 7-8 day tokens; WebSocket skips revocation | SEC-03 (W1-02), SEC-12 (W3-10) |
| 2.2 Financial reads unaudited | Partly registered; quotes, repairs, metal inventory, metal prices, analytics still missing | SEC-15 (W1-04) |
| 2.3 Retention enforcement | Sweep exists for 3 tables, dry-run only | GDPR-08 (W5-07) |
| 2.5 Backup vs erasure | Policy documented, but the "re-run after restore" claim is false for later erasures | GDPR-07 (W5-05) |
| 2.6 Out-of-band alerting | Watchdog template exists, not installed; no error tracking | OPS-07 (W5-03), ARCH-12 (W5-12) |
| 2.10 Rate limiting | Buckets by (IP, username), but in production the IP is always the nginx container | SEC-04 (W1-03) |
| 2.15 Art. 30 record | Refreshed to v1.1; V1.0 entries still missing; controller named wrongly | GDPR-17, 07 §F (W5-10) |
| 2.12 Plaintext financial/PII columns (open) | Unchanged | SEC-14 (W5-06) |

Tier 3: `tests/__init__.py`, the WIP test failures, flaky #31 and stale #8 are fixed; the mypy gate
is restructured as a baseline (OPS-03); frontend ESLint (#33) is still open (FE-15, OPS-13).

---

## (g) Risks and decisions that need the owner or a Steuerberater

The fix plan proceeds on the recommended default for each question; an item stops if a default is
overturned. Full table with alternatives and affected items: MASTER-FIX-PLAN section 6.

| ID | Question | Recommended default | Who |
|---|---|---|---|
| D-01 | Is `Order.price` the gross Endpreis or net? | **Implemented 2026-09-25 as NET** (docs/architecture/ADR-2026-09-25-price-semantics.md): `Order.price` excludes VAT, quote conversion writes `quote.subtotal`, cost calculation writes net, the invoice adds 19% on top. Reversible to gross if Anne/Max prefer, but all paths must change together | Anne, Max (issue #28) |
| D-02 | How is an Altgold trade-in treated for VAT, and which revenue accounts apply per VAT rate? | Deduct after VAT with its own Ankaufbeleg; VAT on the full sale; accounts beyond 8400 from the Steuerberater | Steuerberater |
| D-03 | Build the internet-reachable token status page? | Not now: email plus PDF first; portal off by default; mails carry a signed link with a reply-by-email fallback | Anne, Max |
| D-04 | Keep the VIEWER role? Add APPRENTICE? Which role does Anne use daily? | Keep VIEWER once W1-04 makes it safe; create no VIEWER accounts until then; no APPRENTICE yet; "Heute" work view for everyone | Anne, Max |
| D-05 | What consent wording covers allergy notes, and may the health reason be stored? | Explicit consent per purpose (draft wording until approved) | lawyer, Anne |
| D-06 | What is the immutable invoice snapshot, and how long are records kept? | JSON snapshot at creation, frozen PDF plus SHA-256 at SENT; 8 years invoices, 6 accepted quotes, 5 Altgold/GwG | Steuerberater |
| D-07 | Until a customer-message module exists, how do reminder emails reach customers? | At most once per event, recorded as a Kundeninfo entry; staff notifications never email customers | Max |
| D-08 | Which retention period per table, and when may the sweep delete for real? | Starting points in GDPR-08; execute only after written sign-off | Anne with a DPO or lawyer |
| D-09 | Estimator cost basis? | Hours median times blended rate | Max |
| D-10 | How strict is the hallmark check? | Soft gate: Feingehalt from the alloy, or "nicht punziert (Grund)" | Anne |
| D-11 | May customers exist without an email address? | Yes | Anne |
| D-12 | Should orders get a human-facing Auftragsnummer before production? | Yes, from the per-year counter | Anne |
| D-13 | How far does the design-IP exclusion in the Art. 15 export go? | Disclose what the customer told you; withhold only your design work | lawyer |
| D-14 | Tailwind or plain CSS; which typeface; dark mode or high-contrast mode? | Plain CSS plus tokens; IBM Plex as the playbook proposes; ask Anne about glare vs darkness | Max, Anne |
| D-15 | Should the timer have a Pause? | Remove the fake one now; re-add as a real interruption only if wanted | Anne |
| D-16 | GwG identification for Altgold cash purchases: threshold and fields? | Optional fields, required above 2,000 EUR cash (verify) | Steuerberater or lawyer |
| D-17 | Pull the single critical dependency bump (anyio) into Wave 1? | Recommended yes as a one-line bump if CI stays green (policy places it in Wave 5) | Max |
| D-18 | Error tracking: hosted Sentry, self-hosted GlitchTip, or none? | Self-hosted GlitchTip with PII scrubbing | Max |
| D-19 | Who is the controller in the Art. 30 record? | Anne's workshop; Max is her processor if he operates the system | Anne, Max |

**Programme risks:** money migrations can change historic numbers (rehearse on a production dump;
freeze issued invoices first); erasure changes can delete or keep the wrong data (adversarial rounds
and a restore drill); parallel agents can collide on shared files (serial chains in the plan); tests
can stay green while browser flows fail, as happened with FE-01 and FE-02 (test through the real
router, Playwright for every headline flow).

---

## (h) Where to find everything

| Document | Purpose |
|---|---|
| [README.md](README.md) | Index and reading order for this folder |
| [FINDINGS-REGISTER.md](FINDINGS-REGISTER.md) | One row per finding (212), corrected severity, wave, status, fix item. Update it as items land |
| [MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md) | How to execute: branching, TDD, adversarial rounds, 83 items in 7 waves, Wave 1 hand-off packets, dependencies, checkpoints, decisions |
| [01-architecture.md](01-architecture.md) | Layering, domain model, target architecture and phases |
| [02-security.md](02-security.md) | Route inventory, security findings, dependency audit |
| [03-backend-correctness.md](03-backend-correctness.md) | Money path, time tracking, data-model assessment |
| [04-frontend-code-and-flows.md](04-frontend-code-and-flows.md) | Frontend findings, page table, the five flow traces |
| [05-domain-product-fit.md](05-domain-product-fit.md) | Jobs to be done, capability inventory, top-15 recommendations, customer-feedback options |
| [06-testing-ci-ops.md](06-testing-ci-ops.md) | Test metrics, CI, operations checklist |
| [07-gdpr-privacy.md](07-gdpr-privacy.md) | Privacy-rule matrix, encryption coverage, feedback-channel preconditions E1 to E18 |
| [08-design-investigation.md](08-design-investigation.md) | Tokens, components, accessibility, the I-01 to I-30 plan |
| `docs/design/UI-UX-PLAYBOOK.md` | Design rules for humans and agents, and the five-phase migration Wave 4 follows |
| `.orchestrated-fable/ux-erp-audit-2026-09/verify-*.md` | The three verification reports |
| `docs/review/2026-07-26/production-readiness.md` | The previous audit (its verdict is stale; see section f) |
