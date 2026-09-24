# Findings Register (audit 2026-09-25, `main` @ 73fff19)

This is the tracking artifact for the September 2026 audit. One row per finding. When a fix item lands on `audit/2026-09-fixes`, set `status` to `fixed (<commit>)` for every row that names that item. Execution detail for every fix item is in [MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md).

## Notes on IDs and severities

- **Sources:** 01 = [01-architecture.md](01-architecture.md), 02 = [02-security.md](02-security.md), 03 = [03-backend-correctness.md](03-backend-correctness.md), 04 = [04-frontend-code-and-flows.md](04-frontend-code-and-flows.md), 05 = [05-domain-product-fit.md](05-domain-product-fit.md), 06 = [06-testing-ci-ops.md](06-testing-ci-ops.md), 07 = [07-gdpr-privacy.md](07-gdpr-privacy.md), 08 = [08-design-investigation.md](08-design-investigation.md), VFD = `.orchestrated-fable/ux-erp-audit-2026-09/verify-frontend-domain-design.md`.
- **Corrected severities** from the verifiers override the reports: SEC-02 HIGH to CRITICAL, BE-05 HIGH to CRITICAL (authorization bypass: GOLDSMITH holds INVOICE_EDIT but not INVOICE_DELETE, yet can cancel a PAID invoice via PUT), FE-13 MEDIUM to HIGH (same defect as DOM-01).
- **Range severities** are recorded at their upper bound: SEC-10 (LOW-MEDIUM) as MEDIUM, OPS-04 (LOW/MEDIUM) as MEDIUM.
- **Domain rows (05):** the report rates gaps by impact H/M/L; they are recorded as HIGH/MEDIUM/LOW. Its gap tables already carry IDs (including sub-IDs 11b, 11c, 11d, 15b, 15c, 24b). The section E "Feature bloat" table has no IDs, so its rows were assigned IDs in order of appearance: ML router = DOM-40, analytics router = DOM-41, scan adoption gate = DOM-42, theme router = DOM-43, materials vs metal inventory vs metal types vs gemstone = **DOM-33** (the report's capability inventory already calls this row "DOM-33" but never defines it), two hallmark systems = DOM-44, `Customer.ring_size` vs measurement library = DOM-45, legacy `NEW` status = DOM-46. Three section E rows restate existing IDs and get no new row: `OrderItem` unused (DOM-26), metal/alloy double entry (DOM-06), 13 tabs and 14 nav items (DOM-17, with the nav half in DES-11). None of the section E rows has an impact rating; DOM-33 and DOM-40 to DOM-46 are rated LOW by this synthesis (marked †).
- **Design rows (08):** DES-01 to DES-30 are the rows I-01 to I-30 of the section I improvement plan, in order. The report rates impact H/M/L, recorded here as HIGH/MEDIUM/LOW.
- **SEC-F rows:** the numbered items F-1 to F-10 in 02 §F. F-3 (label print script blocked by CSP) is folded into SEC-07 and F-9 (EXIF kept on originals) into GDPR-19, because the report itself cross-references them. The report gives the F-items no severity; the severities shown are assigned by this synthesis (marked †).
- **VER rows:** new issues found by the frontend/domain/design verifier (VFD, "New issues" 1 and 2). VFD new issue 3 (false `customer_notified_at`) sharpens DOM-12 and is tracked there. The backend verifier's new finding (invoice cancel authorization bypass) is merged into BE-05.
- **Not in the register:** the "status of prior findings" tables (section A of each report) and the "things you might have missed" lists, except where an item carries its own ID. Open prior-audit items without IDs are bundled into fix item W7-06.
- **Verified:** `Y` = confirmed by a verification agent, `partial` = partially confirmed, `N` = outside a verifier's scope (verifiers covered CRITICAL/HIGH findings, impact-H domain gaps and four design claims). No finding was refuted.

**Totals:** 212 findings. CRITICAL 8, HIGH 67, MEDIUM 91, LOW 46. By wave: W1 60, W2 43, W3 23, W4 30, W5 30, W6 10, W7 16.

## Register

| ID | Severity | Title | Source | Verified | Wave | Status | Fix item |
|---|---|---|---|---|---|---|---|
| SEC-02 | CRITICAL | Placeholder SECRET_KEY accepted with DEBUG=False: admin JWT forgery | 02 | Y | 1 | open | W1-01 |
| BE-01 | CRITICAL | Quote conversion stores gross; invoice adds 19% VAT again | 03 | Y | 1 | open | W1-07 |
| BE-02 | CRITICAL | Invoice bills purchase cost, ignores margin and agreed price | 03 | Y | 1 | open | W1-07 |
| BE-05 | CRITICAL | PUT /invoices cancels PAID invoice; bypasses INVOICE_DELETE | 03 | Y | 1 | open | W1-06 |
| FE-01 | CRITICAL | Customer portal redirects every visitor to staff login | 04 | Y | 1 | open | W1-13 |
| FE-02 | CRITICAL | QR timer start dead-ends: no activity ever chosen | 04 | Y | 1 | open | W1-15 |
| GDPR-01 | CRITICAL | Erasure destroys tax/AML records; no immutable invoice copy | 07 | Y | 1 | open | W1-10 |
| GDPR-02 | CRITICAL | Allergy health data without consent, readable by all roles | 07 | Y | 1 | open | W1-05 |
| SEC-01 | HIGH | VIEWER reads financial data on 11 endpoints | 02 | Y | 1 | open | W1-04 |
| SEC-08 | HIGH | Dev compose exposes unauthenticated Redis and HTTP backend | 02 | Y | 1 | open | W1-01 |
| SEC-F1 | HIGH † | setup.sh writes a .env.production that cannot boot | 02 | N | 1 | open | W1-02 |
| BE-03 | HIGH | Altgold credit crashes invoice creation; VAT treatment likely wrong | 03 | Y | 1 | open | W1-08 |
| BE-04 | HIGH | Soll/Ist "Rechnung erstellen" always 500 (aware due_date) | 03 | Y | 1 | open | W1-06 |
| BE-07 | HIGH | Second metal consumption overwrites order material cost and weight | 03 | Y | 1 | open | W1-11 |
| BE-08 | HIGH | AVERAGE costing draws whole weight from first batch | 03 | Y | 1 | open | W1-11 |
| BE-09 | HIGH | Reminder scans re-fire every 5 min, emailing customers | 03 | Y | 1 | open | W1-12 |
| BE-10 | HIGH | Estimator prices labor from summed medians, not shown median | 03 | Y | 1 | open | W1-16 |
| BE-11 | HIGH | Signed scrap gold mutable; mixed metals valued at gold price | 03 | Y | 1 | open | W1-08 |
| BE-12 | HIGH | Double-tap Start creates two running timers, permanent 500 | 03 | Y | 1 | open | W1-17 |
| BE-13 | HIGH | DATEV export books drafts/cancelled invoices to 19% account | 03 | Y | 1 | open | W1-09 |
| FE-03 | HIGH | Repair scans open or book against order with same ID | 04 | Y | 1 | open | W1-15 |
| FE-04 | HIGH | Half the quick actions unhandled; deep links go nowhere | 04 | Y | 1 | open | W1-15 (deep links W2-01) |
| FE-07 | HIGH | TimeTrackingProvider initialises before login and never again | 04 | Y | 1 | open | W1-14 |
| FE-09 | HIGH | Offline banner promises sync that does not exist | 04 | Y | 1 | open | W1-14 |
| FE-10 | HIGH | Timer "Pause" is cosmetic; server keeps counting | 04 | Y | 1 | open | W1-14 |
| FE-11 | HIGH | Service worker caches PII/prices, survives logout | 04 | Y | 1 | open | W1-14 |
| DOM-10 | HIGH | Customer emails sent per staff user and repeated | 05 | Y | 1 | open | W1-12 |
| DOM-19 | HIGH | Altgold add-item sends number; API wants string; 925 maps to 0 | 05 | Y | 1 | open | W1-08 |
| DOM-20 | HIGH | Mixed-metal Altgold valued entirely at gold price | 05 | Y | 1 | open | W1-08 |
| GDPR-03 | HIGH | VIEWER reads repair costs, insurance values, revenue, prices | 07 | Y | 1 | open | W1-04 |
| GDPR-04 | HIGH | Design IP and photos readable by VIEWER | 07 | Y | 1 | open | W1-04 |
| VER-01 | HIGH | Repair-ready notification sends customer name to every user incl. VIEWER | VFD | Y (new) | 1 | open | W1-12 |
| SEC-03 | MEDIUM | Shipped env files set 7-8 day token lifetime | 02 | N | 1 | open | W1-02 |
| SEC-04 | MEDIUM | Rate limits key on nginx IP: global login lockout | 02 | N | 1 | open | W1-03 |
| SEC-05 | MEDIUM | Customer PII written to logs via request URLs | 02 | N | 1 | open | W1-20 |
| SEC-06 | MEDIUM | SPA served without CSP, frame protection or HSTS | 02 | N | 1 | open | W1-02 |
| SEC-07 | MEDIUM | Stored HTML injection in printable labels (incl. F-3) | 02 | N | 1 | open | W1-18 |
| SEC-09 | MEDIUM | Design IP visible to VIEWER | 02 | N | 1 | open | W1-04 |
| SEC-10 | MEDIUM | Public portal mounted despite "no live portal" decision | 02 | N | 1 | open | W1-03 |
| SEC-11 | MEDIUM | PUT /users/me changes email/password without re-authentication | 02 | N | 1 | open | W1-19 |
| SEC-F2 | MEDIUM † | nginx 1 MB body limit breaks 8-10 MB uploads | 02 | N | 1 | open | W1-02 |
| SEC-F6 | MEDIUM † | No API to assign roles; new users default VIEWER | 02 | N | 1 | open | W1-19 |
| BE-17 | MEDIUM | Quotes: cross-customer, duplicate orders on convert, expired approvals | 03 | N | 1 | open | W1-07 |
| BE-18 | MEDIUM | Editing a time entry can store negative durations | 03 | N | 1 | open | W1-17 |
| BE-21 | MEDIUM | Monitor loop shares one session; one error aborts later steps | 03 | N | 1 | open | W1-12 |
| BE-23 | MEDIUM | Invoice PDF rendered from live customer; lacks §14 fields | 03 | N | 1 | open | W1-10 |
| FE-19 | MEDIUM | Timer polling continues after logout and when idle | 04 | N | 1 | open | W1-14 |
| DOM-07 | MEDIUM | No consent capture for photos, marketing, AGB | 05 | N | 1 | open | W1-05 |
| GDPR-09 | MEDIUM | Valuation PDF not ADMIN-only; repair insurance value plain, unaudited | 07 | N | 1 | open | W1-04 (encryption W5-06) |
| GDPR-10 | MEDIUM | Customer names/emails in request logs via query strings | 07 | N | 1 | open | W1-20 |
| GDPR-11 | MEDIUM | No consent or objection management at all | 07 | N | 1 | open | W1-05 |
| GDPR-13 | MEDIUM | Internal staff text sent to customers in automatic emails | 07 | N | 1 | open | W1-12 |
| VER-02 | MEDIUM | Repair-ready notifications skip WebSocket publish | VFD | Y (new) | 1 | open | W1-12 |
| SEC-13 | LOW | Time-entry stop/edit/interrupt lack owner check | 02 | N | 1 | open | W1-17 |
| SEC-15 | LOW | Remaining audit-log gaps for financial reads | 02 | N | 1 | open | W1-04 |
| SEC-17 | LOW | Login timing oracle for account enumeration | 02 | N | 1 | open | W1-03 |
| SEC-18 | LOW | Image decompression bomb headroom vs 512 MB container | 02 | N | 1 | open | W1-18 |
| BE-25 | LOW | Duplicate invoice/quote line builders with hardcoded 75.0 rate | 03 | N | 1 | open | W1-07 |
| OPS-15 | LOW | AUTH_REVOCATION_FAIL_CLOSED undocumented in .env.example | 06 | N | 1 | open | W1-02 |
| GDPR-19 | LOW | Photo originals keep EXIF; labels print full names (incl. F-9) | 07 | N | 1 | open | W1-18 |
| ARCH-01 | HIGH | Order lifecycle unmodelled; status history never written | 01 | Y | 2 | open | W2-07 |
| BE-06 | HIGH | Order status not a state machine; no history | 03 | Y | 2 | open | W2-07 |
| FE-05 | HIGH | Dashboard drops overdue orders; failure shows "alles erledigt" | 04 | Y | 2 | open | W2-03 |
| FE-08 | HIGH | Frontend never subscribes to channels the backend publishes | 04 | Y | 2 | open | W2-13 |
| FE-13 | HIGH | No order-photo upload; gallery uses unservable URLs | 04 | Y | 2 | open | W2-01 |
| DOM-01 | HIGH | No way to upload order photos; scanner photo goes nowhere | 05 | Y | 2 | open | W2-01 |
| DOM-02 | HIGH | Walk-in customers without email cannot be created | 05 | Y | 2 | open | W2-10 |
| DOM-03 | HIGH | Consultation conversion drops deadline, type, metal, measurements, photos | 05 | Y | 2 | open | W2-05 |
| DOM-04 | HIGH | No gemstone capture (4C, Fassung, customer stone) | 05 | Y | 2 | open | W2-06 |
| DOM-11 | HIGH | Quote "Versenden" only flips status, sends nothing | 05 | Y | 2 | open | W2-05 |
| DOM-11b | HIGH | Quote-to-order conversion drops lines, metal, weight, deadline | 05 | Y | 2 | open | W2-05 |
| DOM-12 | HIGH | Repairs get no customer updates; false customer_notified_at | 05 | Y | 2 | open | W2-02 |
| DOM-13 | HIGH | No Storniert or Pausiert order statuses | 05 | Y | 2 | open | W2-07 |
| DOM-14 | HIGH | Overdue orders ranked lowest on dashboard | 05 | Y | 2 | open | W2-03 |
| DOM-15 | HIGH | Dashboard ignores repairs and customer-pending items | 05 | Y | 2 | open | W2-03 |
| DOM-22 | HIGH | Hallmark vocabulary too narrow, forces false Feingehalt records | 05 | Y | 2 | open | W2-09 |
| DOM-24 | HIGH | Invoice PDF lacks §14 UStG seller data and Leistungsdatum | 05 | Y | 2 | open | W2-04 |
| BE-16 | MEDIUM | Sequential numbers use unlocked MAX+1; break at 10,000 | 03 | N | 2 | open | W2-04 |
| BE-19 | MEDIUM | Interruptions never reduce time; actual_hours frozen at completion | 03 | N | 2 | open | W2-14 |
| BE-20 | MEDIUM | Events published to unsubscribed channels; Redis lacks timeouts | 03 | N | 2 | open | W2-13 |
| BE-22 | MEDIUM | Metal price feed treats USD as EUR; Pt priced at 999 | 03 | N | 2 | open | W2-15 |
| FE-17 | MEDIUM | Walk-in repair intake takes customer as numeric ID | 04 | N | 2 | open | W2-12 |
| FE-18 | MEDIUM | Cross-page hand-offs pass query params nobody reads | 04 | N | 2 | open | W2-05 |
| DOM-05 | MEDIUM | Ring-size requirement triggered by substring "ring" (Ohrring) | 05 | N | 2 | open | W2-06 |
| DOM-06 | MEDIUM | Metal and alloy entered twice and can contradict | 05 | N | 2 | open | W2-06 |
| DOM-08 | MEDIUM | Repair intake has no signed receipt or conditions | 05 | N | 2 | open | W2-12 |
| DOM-09 | MEDIUM | Order form never sets order_type; estimator exact tier starves | 05 | N | 2 | open | W2-06 |
| DOM-11c | MEDIUM | Metal price source not shown when quoting | 05 | N | 2 | open | W2-15 |
| DOM-15b | MEDIUM | Dashboard widgets truncated at 100 orders | 05 | N | 2 | open | W2-03 |
| DOM-16 | MEDIUM | Order history tab does not show status history | 05 | N | 2 | open | W2-08 |
| DOM-17 | MEDIUM | 13 tabs on the order page | 05 | N | 2 | open | W2-08 |
| DOM-18 | MEDIUM | Status change is 9 free buttons, no next-step guidance | 05 | N | 2 | open | W2-08 |
| DOM-21 | MEDIUM | No ID capture or Ankaufsbuch for Altgold buy-ins | 05 | N | 2 | open | W2-16 |
| DOM-23 | MEDIUM | Punzierung hard gate, scanner-only, raw error on order page | 05 | N | 2 | open | W2-09 |
| DOM-24b | MEDIUM | No Storno/credit-note flow; issued invoices editable | 05 | N | 2 | open | W2-04 |
| DOM-30 | MEDIUM | Customer updates manual only; no milestone prompts | 05 | N | 2 | open | W2-08 |
| DOM-34 | MEDIUM | Insurance valuation has no UI | 05 | N | 2 | open | W2-11 |
| DOM-35 | MEDIUM | No care instructions or warranty at handover | 05 | N | 2 | open | W2-11 |
| DOM-38 | MEDIUM | Customer 360 misses repairs, consultations, quotes; invoices capped 200 | 05 | N | 2 | open | W2-12 |
| DOM-11d | LOW | Quote approvable from DRAFT without recorded agreement method | 05 | N | 2 | open | W2-05 |
| DOM-15c | LOW | No receivables or monthly revenue glance | 05 | N | 2 | open | W2-03 |
| DOM-44 | LOW † | Two unconnected hallmark systems (OrderHallmark register unused) | 05 | N | 2 | open | W2-09 |
| DOM-46 | LOW † | Legacy NEW status still default and in labels | 05 | N | 2 | open | W2-07 |
| ARCH-03 | HIGH | Repository layer is 1.8k LOC dead code; routers run SQL | 01 | Y | 3 | open | W3-09 |
| ARCH-04 | HIGH | Background work in web process; 2 workers duplicate it | 01 | Y | 3 | open | W3-10 (outbox W6-01) |
| BE-14 | HIGH | Float money and round() cause cent errors on documents | 03 | Y | 3 | open | W3-11 |
| FE-06 | HIGH | Lists, pickers, dashboards silently cap at 100/200 rows | 04 | Y | 3 | open | W3-08 |
| ARCH-06 | MEDIUM | No frontend server-state layer; lists truncate, never refresh | 01 | N | 3 | open | W3-03 |
| ARCH-07 | MEDIUM | API types hand-maintained on both sides, no generated contract | 01 | N | 3 | open | W3-02 |
| ARCH-08 | MEDIUM | Inconsistent pagination, error envelope, prefixes, exception mapping | 01 | N | 3 | open | W3-07 (pagination W3-08) |
| ARCH-11 | MEDIUM | Real-time fan-out per socket, no lifecycle, partly unused | 01 | N | 3 | open | W3-10 |
| BE-15 | MEDIUM | Timezone-aware inputs reach naive columns (fails on PG) | 03 | N | 3 | open | W3-11 |
| FE-12 | MEDIUM | Role enum casing drift hides admin metal-type manager | 04 | N | 3 | open | W3-02 |
| FE-14 | MEDIUM | ErrorBoundary retry never reloads; resets on every re-render | 04 | N | 3 | open | W3-01 |
| FE-15 | MEDIUM | No ESLint at all; hooks rules unenforced | 04 | N | 3 | open | W3-06 |
| FE-16 | MEDIUM | Forms: mixed validation, raw axios errors, no dirty guard | 04 | N | 3 | open | W3-05 |
| FE-20 | MEDIUM | No cancellation or dedupe; 54 copies of loading boilerplate | 04 | N | 3 | open | W3-03 |
| SEC-F5 | MEDIUM † | PUT /admin/email-config changes one worker only, lost on restart | 02 | N | 3 | open | W3-10 |
| SEC-12 | LOW | WebSocket auth skips revocation and is_active; accepts ?token= | 02 | N | 3 | open | W3-10 |
| SEC-16 | LOW | Unbounded limit on 7 list endpoints | 02 | N | 3 | open | W3-08 |
| BE-24 | LOW | Dead repository layer references non-existent columns | 03 | N | 3 | open | W3-09 |
| BE-26 | LOW | Unlimited list endpoints; stray test DBs in repo root | 03 | N | 3 | open | W3-08 |
| FE-22 | LOW | Dead components, eager recharts, public sourcemaps | 04 | N | 3 | open | W3-01 |
| FE-23 | LOW | Accessibility mechanics: clickable divs, tabs without roles | 04 | N | 3 | open | W3-04 |
| FE-24 | LOW | Derived state in effects; 13 status-label maps drift | 04 | N | 3 | open | W3-04 |
| OPS-13 | LOW | Frontend ESLint config missing; issue #33 open | 06 | N | 3 | open | W3-06 |
| DES-01 | HIGH | Primary CTA, links, active nav fail AA contrast | 08 | Y | 4 | open | W4-01 |
| DES-02 | HIGH | Focus ring 2.15:1; 33 outline:none | 08 | N | 4 | open | W4-01 |
| DES-03 | HIGH | 6 of 10 order statuses unstyled; 8+ badge systems | 08 | Y | 4 | open | W4-02 |
| DES-04 | HIGH | Deadline urgency colour-only; absent from Orders list | 08 | N | 4 | open | W4-02 |
| DES-05 | HIGH | Global class collisions (.btn-primary x7, .modal-* x4-5) | 08 | N | 4 | open | W4-09 |
| DES-06 | HIGH | No Button/IconButton API; .btn below 44px | 08 | N | 4 | open | W4-03 |
| DES-07 | HIGH | Modals lack dialog role, Escape, focus trap; backdrop loses data | 08 | N | 4 | open | W4-03 |
| DES-08 | HIGH | 1,580 hex values, 9 golds, 41 undefined custom properties | 08 | partial | 4 | open | W4-01 |
| DES-10 | HIGH | Offline banner hidden under sticky header | 08 | N | 4 | open | W4-01 |
| DES-12 | HIGH | No bottom nav on mobile; header overflows at 390px | 08 | N | 4 | open | W4-04 |
| DES-14 | HIGH | Owner (ADMIN) lands on KPI dashboard, not bench worklist | 08 | N | 4 | open | W4-04 |
| DES-15 | HIGH | Orders table lacks customer/photo; rows not keyboard reachable | 08 | N | 4 | open | W4-05 |
| DES-26 | HIGH | Client portal: no photos, generic name, 1.65:1 footer | 08 | N | 4 | open | W4-08 |
| DES-28 | HIGH | Type and targets too small at the bench (Werkbank-Modus) | 08 | N | 4 | open | W4-04 |
| DES-09 | MEDIUM | 50 font sizes, 15+ radii, 98 shadows, ad hoc z-index | 08 | N | 4 | open | W4-01 |
| DES-11 | MEDIUM | 12 flat nav links; settings page unreachable | 08 | N | 4 | open | W4-04 |
| DES-13 | MEDIUM | Dark mode announced but provider and toggle unmounted | 08 | Y | 4 | open | W4-10 |
| DES-16 | MEDIUM | Edit and delete emoji buttons adjacent in every row | 08 | N | 4 | open | W4-05 |
| DES-17 | MEDIUM | ASCII or dropped umlauts in UI copy (about 20 sites) | 08 | N | 4 | open | W4-01 |
| DES-18 | MEDIUM | Empty states text-only, no next action | 08 | N | 4 | open | W4-03 |
| DES-19 | MEDIUM | 13+ loading and 5+ error patterns; #ff4444 fails contrast | 08 | N | 4 | open | W4-03 |
| DES-20 | MEDIUM | Vite template leftovers in index.css | 08 | N | 4 | open | W4-09 |
| DES-21 | MEDIUM | Inter never loaded; no tabular numerals | 08 | N | 4 | open | W4-03 |
| DES-22 | MEDIUM | Emoji icons; no domain icons | 08 | N | 4 | open | W4-03 |
| DES-24 | MEDIUM | Three scanner entry points, two scanner UIs | 08 | N | 4 | open | W4-04 |
| DES-25 | MEDIUM | Tailwind installed yet banned by plan; mixed usage | 08 | N | 4 | open | W4-09 |
| DES-27 | MEDIUM | Admin theme colours set without contrast checks | 08 | N | 4 | open | W4-01 |
| DES-23 | LOW | 222 inline style={{}} in 37 files | 08 | N | 4 | open | W4-07 |
| DES-29 | LOW | Hover lifts on touch; few reduced-motion guards | 08 | N | 4 | open | W4-01 |
| DES-30 | LOW | Dead code: OrderList, unused @utility set, ThemeToggle | 08 | N | 4 | open | W4-09 |
| OPS-06 | HIGH | 35 open Dependabot alerts (1 critical, 20 high) | 06 | N | 5 | open | W5-01 |
| GDPR-05 | HIGH | Art. 15 export incomplete and ADMIN-only | 07 | Y | 5 | open | W5-08 |
| GDPR-06 | HIGH | Backups unencrypted; cloud sync URL-only auth; no key escrow | 07 | Y | 5 | open | W5-05 |
| GDPR-07 | HIGH | Restore then re-run cleanup misses later erasures | 07 | Y | 5 | open | W5-05 |
| GDPR-08 | HIGH | No storage limitation for most personal data | 07 | Y | 5 | open | W5-07 |
| ARCH-12 | MEDIUM | Observability stops at JSON logs; no error tracking | 01 | N | 5 | open | W5-12 |
| SEC-14 | MEDIUM | Plaintext signatures/notes/financial columns; unencrypted backups | 02 | N | 5 | open | W5-06 |
| SEC-F4 | MEDIUM † | Backup/GDPR alerts never arrive; off-site sync silently off | 02 | N | 5 | open | W5-05 |
| OPS-01 | MEDIUM | Four of six E2E specs never run in CI | 06 | N | 5 | open | W5-02 |
| OPS-02 | MEDIUM | Frontend coverage tool not installed; config dead | 06 | N | 5 | open | W5-02 |
| OPS-03 | MEDIUM | mypy green via 1,532-error baseline without shrink pressure | 06 | N | 5 | open | W5-02 |
| OPS-04 | MEDIUM | No CI dependency caching | 06 | N | 5 | open | W5-02 |
| OPS-05 | MEDIUM | No local make test/lint targets | 06 | N | 5 | open | W5-03 |
| OPS-07 | MEDIUM | Compliance systemd timers exist but nothing installs them | 06 | N | 5 | open | W5-03 |
| GDPR-14 | MEDIUM | Per-employee accuracy analytics not in Art. 30 record | 07 | N | 5 | open | W5-09 |
| GDPR-15 | MEDIUM | SMTP, backup host, accounting export not covered as processors | 07 | N | 5 | open | W5-09 |
| GDPR-16 | MEDIUM | Cleanup/retention timers not installed; point at dev compose | 07 | N | 5 | open | W5-03 |
| GDPR-17 | MEDIUM | No breach-response runbook or register (Art. 33/34) | 07 | N | 5 | open | W5-10 |
| ARCH-14 | LOW | Migrations and seed run on every boot; PWA caches orders | 01 | N | 5 | open | W5-12 |
| ARCH-16 | LOW | Architecture docs stale; no ADRs | 01 | N | 5 | open | W5-11 |
| SEC-F7 | LOW † | Caddy internal root CA not in backup plan | 02 | N | 5 | open | W5-05 |
| SEC-F8 | LOW † | SameSite=Strict on IP site: never co-host other web apps | 02 | N | 5 | open | W5-11 |
| SEC-F10 | LOW † | Demo seed accounts use known password demo2026! | 02 | N | 5 | open | W5-11 |
| OPS-08 | LOW | docs/DEPLOYMENT.md stale and misleading | 06 | N | 5 | open | W5-11 |
| OPS-09 | LOW | Redis publish-to-WebSocket path fully mocked in tests | 06 | N | 5 | open | W5-04 |
| OPS-10 | LOW | "Passes on PostgreSQL" xfail claim never checked | 06 | N | 5 | open | W5-02 |
| OPS-11 | LOW | No dependency vulnerability scan in CI | 06 | N | 5 | open | W5-02 |
| OPS-12 | LOW | ruff and pylint not run in CI | 06 | N | 5 | open | W5-02 |
| OPS-14 | LOW | Seven stale worktrees and stray alembic_backup/ | 06 | N | 5 | open | W5-13 |
| GDPR-18 | LOW | Encryption hardening: tolerate_plaintext, no rotation path | 07 | N | 5 | open | W5-06 |
| ARCH-02 | HIGH | Order and RepairJob duplicate aggregates; repairs cannot be invoiced | 01 | Y | 6 | open | W6-04 |
| ARCH-05 | HIGH | Customer communication is a side effect of staff notifications | 01 | Y | 6 | open | W6-02 |
| DOM-29 | HIGH | Customer cannot approve or decline in one click | 05 | Y | 6 | open | W6-07 |
| ARCH-09 | MEDIUM | db/models.py and services are growing god-modules | 01 | N | 6 | open | W6-05 |
| ARCH-10 | MEDIUM | Three unrelated photo models; local filesystem assumption | 01 | N | 6 | open | W6-03 |
| FE-21 | MEDIUM | Portal thin: placeholder contacts, raw ISO dates, no token route | 04 | N | 6 | open | W6-07 |
| DOM-31 | MEDIUM | Portal link never rendered in emails; tokens expire in 1 h | 05 | N | 6 | open | W6-07 |
| GDPR-12 | MEDIUM | Public portal leaks design text, enumerable, broken rate limit | 07 | N | 6 | open | W6-07 |
| DOM-32 | LOW | No post-pickup feedback or rating | 05 | N | 6 | open | W6-06 |
| GDPR-20 | LOW | No self-service rights request; audit IP kept forever | 07 | N | 6 | open | W6-07 |
| DOM-25 | MEDIUM | No assignee or "mine" view; no apprentice role | 05 | N | 7 | open | W7-01 |
| DOM-26 | MEDIUM | No multi-piece orders (wedding ring pairs) | 05 | N | 7 | open | W7-01 |
| DOM-27 | MEDIUM | Endkontrolle has no checklist | 05 | N | 7 | open | W7-01 |
| DOM-36 | MEDIUM | No aftercare reminders (service check, rhodium, anniversary) | 05 | N | 7 | open | W7-02 |
| DOM-37 | MEDIUM | No deposit (Anzahlung) or partial payment | 05 | N | 7 | open | W7-02 |
| DOM-39 | MEDIUM | No offline queue for bench actions | 05 | N | 7 | open | W7-03 |
| ARCH-13 | LOW | No feature flags; unused dependencies declared | 01 | N | 7 | open | W7-04 |
| ARCH-15 | LOW | Audit and authorization routed by URL shape, not data | 01 | N | 7 | open | W7-05 |
| FE-25 | LOW | yarn build exits 127 in this checkout (install-state drift) | 04 | Y | 7 | open | W7-06 |
| DOM-28 | LOW | Seed activities miss core techniques (Giessen, Montage, ...) | 05 | N | 7 | open | W7-04 |
| DOM-33 | LOW † | Two stock worlds: materials vs metal inventory vs gemstones | 05 | N | 7 | open | W7-04 |
| DOM-40 | LOW † | ML router (914 lines) has no frontend caller | 05 | N | 7 | open | W7-04 |
| DOM-41 | LOW † | Analytics router has no frontend caller | 05 | N | 7 | open | W7-04 |
| DOM-42 | LOW † | Scan adoption gate is a rollout tool, not a workshop need | 05 | N | 7 | open | W7-04 |
| DOM-43 | LOW † | Server-side theme persistence over-engineered | 05 | N | 7 | open | W7-04 |
| DOM-45 | LOW † | Customer.ring_size duplicates the measurement library | 05 | N | 7 | open | W7-04 |
