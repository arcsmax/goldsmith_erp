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

## Status legend (updated 2026-09-25, after waves 1-7 landed on `audit/2026-09-fixes`)

- **`fixed (<sha1>[, <sha2>...])`** — a fix-item scratch report or a commit message on `audit/2026-09-fixes` states this finding is resolved; the short SHA(s) are the commits that did it (in landing order). Commit hashes are from `git log --oneline main..HEAD`.
- **`partial: <what's left>`** — a report explicitly describes the finding as only partly closed, or closes the finding's primary defect while leaving a sub-part (named in the clause) for a later wave. The clause names the residual gap and, where relevant, the wave item that owns it.
- **`open`** — no scratch report or commit claims this finding was touched. This includes findings whose owning fix item is still running (see [MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md) section 0 for the in-progress list) as well as findings in waves 2-7 that have not started.
- This pass covers waves 1-7 where evidence exists (see [PROGRESS.md](PROGRESS.md) for the full changelog, the ~53 fix-item scratch reports and the 2 live-verification rounds read to build it). No row was set to `fixed`/`partial` on the strength of a commit message alone where a scratch report contradicted it; per this task's method, the report is the source of truth on any disagreement. Severities and wave/fix-item assignments are unchanged from the original synthesis. Two items were still running as this pass was written and are not reflected past what had landed: W3-11 (Numeric/tz migration) and the post-W2 open-items agent — see [MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md) section 0.

**Counts after this pass (waves 1-7, 2026-09-25):** fixed 107, partial 42, open 63.

## Register

| ID | Severity | Title | Source | Verified | Wave | Status | Fix item |
|---|---|---|---|---|---|---|---|
| SEC-02 | CRITICAL | Placeholder SECRET_KEY accepted with DEBUG=False: admin JWT forgery | 02 | Y | 1 | fixed (b315d25, e121bfb) | W1-01 |
| BE-01 | CRITICAL | Quote conversion stores gross; invoice adds 19% VAT again | 03 | Y | 1 | fixed (6cecd9e) | W1-07 |
| BE-02 | CRITICAL | Invoice bills purchase cost, ignores margin and agreed price | 03 | Y | 1 | fixed (41c1a4f) | W1-07 |
| BE-05 | CRITICAL | PUT /invoices cancels PAID invoice; bypasses INVOICE_DELETE | 03 | Y | 1 | fixed (41c1a4f, b9bc5fa) | W1-06 |
| FE-01 | CRITICAL | Customer portal redirects every visitor to staff login | 04 | Y | 1 | fixed (405bf6c) | W1-13 |
| FE-02 | CRITICAL | QR timer start dead-ends: no activity ever chosen | 04 | Y | 1 | fixed (3cf39de) | W1-15 |
| GDPR-01 | CRITICAL | Erasure destroys tax/AML records; no immutable invoice copy | 07 | Y | 1 | fixed (996703f, 1230e8f) | W1-10 |
| GDPR-02 | CRITICAL | Allergy health data without consent, readable by all roles | 07 | Y | 1 | fixed (996703f, f976482) | W1-05 |
| SEC-01 | HIGH | VIEWER reads financial data on 11 endpoints | 02 | Y | 1 | fixed (fd15807, 083b1f9, c8065f8) | W1-04 |
| SEC-08 | HIGH | Dev compose exposes unauthenticated Redis and HTTP backend | 02 | Y | 1 | fixed (948ddf5) | W1-01 |
| SEC-F1 | HIGH † | setup.sh writes a .env.production that cannot boot | 02 | N | 1 | fixed (29fab2f) | W1-02 |
| BE-03 | HIGH | Altgold credit crashes invoice creation; VAT treatment likely wrong | 03 | Y | 1 | fixed (41c1a4f) | W1-08 |
| BE-04 | HIGH | Soll/Ist "Rechnung erstellen" always 500 (aware due_date) | 03 | Y | 1 | fixed (41c1a4f) | W1-06 |
| BE-07 | HIGH | Second metal consumption overwrites order material cost and weight | 03 | Y | 1 | fixed (d07b769) | W1-11 |
| BE-08 | HIGH | AVERAGE costing draws whole weight from first batch | 03 | Y | 1 | fixed (d07b769) | W1-11 |
| BE-09 | HIGH | Reminder scans re-fire every 5 min, emailing customers | 03 | Y | 1 | fixed (4fb66d7, 22612fb, 9af6d05) | W1-12 |
| BE-10 | HIGH | Estimator prices labor from summed medians, not shown median | 03 | Y | 1 | fixed (27ea4f4) | W1-16 |
| BE-11 | HIGH | Signed scrap gold mutable; mixed metals valued at gold price | 03 | Y | 1 | fixed (33ddd44, 17adb24) | W1-08 |
| BE-12 | HIGH | Double-tap Start creates two running timers, permanent 500 | 03 | Y | 1 | fixed (d5f4b22) | W1-17 |
| BE-13 | HIGH | DATEV export books drafts/cancelled invoices to 19% account | 03 | Y | 1 | fixed (4e7b77f) | W1-09 |
| FE-03 | HIGH | Repair scans open or book against order with same ID | 04 | Y | 1 | fixed (3cf39de, d1c82a3) | W1-15 |
| FE-04 | HIGH | Half the quick actions unhandled; deep links go nowhere | 04 | Y | 1 | partial: photo-related deep link now works via scan-to-Fotos-tab (8f8e1b9, f5cf713); `?edit=location`, `?action=print-label`, `?action=consume-material` still unhandled on the order page | W1-15 (deep links W2-01) |
| FE-07 | HIGH | TimeTrackingProvider initialises before login and never again | 04 | Y | 1 | fixed (775c3c0) | W1-14 |
| FE-09 | HIGH | Offline banner promises sync that does not exist | 04 | Y | 1 | fixed (1d57dc8) | W1-14 |
| FE-10 | HIGH | Timer "Pause" is cosmetic; server keeps counting | 04 | Y | 1 | fixed (4208877) | W1-14 |
| FE-11 | HIGH | Service worker caches PII/prices, survives logout | 04 | Y | 1 | fixed (775c3c0, 1d57dc8) | W1-14 |
| DOM-10 | HIGH | Customer emails sent per staff user and repeated | 05 | Y | 1 | fixed (4fb66d7, 9af6d05) | W1-12 |
| DOM-19 | HIGH | Altgold add-item sends number; API wants string; 925 maps to 0 | 05 | Y | 1 | fixed (9639f64, 33ddd44) | W1-08 |
| DOM-20 | HIGH | Mixed-metal Altgold valued entirely at gold price | 05 | Y | 1 | partial: valuation now per-metal-price-correct (33ddd44); total_fine_gold_g still aggregates across metals, no per-metal breakdown (needs schema change) | W1-08 |
| GDPR-03 | HIGH | VIEWER reads repair costs, insurance values, revenue, prices | 07 | Y | 1 | fixed (fd15807, 083b1f9) | W1-04 |
| GDPR-04 | HIGH | Design IP and photos readable by VIEWER | 07 | Y | 1 | fixed (fd15807, 083b1f9) | W1-04 |
| VER-01 | HIGH | Repair-ready notification sends customer name to every user incl. VIEWER | VFD | Y (new) | 1 | fixed (4fb66d7) | W1-12 |
| SEC-03 | MEDIUM | Shipped env files set 7-8 day token lifetime | 02 | N | 1 | fixed (29fab2f) | W1-02 |
| SEC-04 | MEDIUM | Rate limits key on nginx IP: global login lockout | 02 | N | 1 | fixed (b315d25) | W1-03 |
| SEC-05 | MEDIUM | Customer PII written to logs via request URLs | 02 | N | 1 | fixed (b315d25, 4518e2f) | W1-20 |
| SEC-06 | MEDIUM | SPA served without CSP, frame protection or HSTS | 02 | N | 1 | fixed (4518e2f) | W1-02 |
| SEC-07 | MEDIUM | Stored HTML injection in printable labels (incl. F-3) | 02 | N | 1 | partial: label HTML escaping done (e9cfca8); F-3 print-script still blocked by CSP, not relaxed | W1-18 |
| SEC-09 | MEDIUM | Design IP visible to VIEWER | 02 | N | 1 | fixed (fd15807, 083b1f9) | W1-04 |
| SEC-10 | MEDIUM | Public portal mounted despite "no live portal" decision | 02 | N | 1 | fixed (8940316) | W1-03 |
| SEC-11 | MEDIUM | PUT /users/me changes email/password without re-authentication | 02 | N | 1 | fixed (467bc3b, e121bfb) | W1-19 |
| SEC-F2 | MEDIUM † | nginx 1 MB body limit breaks 8-10 MB uploads | 02 | N | 1 | fixed (948ddf5) | W1-02 |
| SEC-F6 | MEDIUM † | No API to assign roles; new users default VIEWER | 02 | N | 1 | fixed (61dc5a3) | W1-19 |
| BE-17 | MEDIUM | Quotes: cross-customer, duplicate orders on convert, expired approvals | 03 | N | 1 | partial: convert_quote now reuses the linked order and writes net (6cecd9e); adversarial round found zero-price conversion, a concurrent double-conversion race and a customer-reassignment gap still open, routed to W2-05 | W1-07 |
| BE-18 | MEDIUM | Editing a time entry can store negative durations | 03 | N | 1 | fixed (d5f4b22) | W1-17 |
| BE-21 | MEDIUM | Monitor loop shares one session; one error aborts later steps | 03 | N | 1 | open | W1-12 |
| BE-23 | MEDIUM | Invoice PDF rendered from live customer; lacks §14 fields | 03 | N | 1 | partial: PDF now renders from the immutable snapshot, not the live customer row (1230e8f); §14 UStG seller fields still missing, deferred to W2-04 | W1-10 |
| FE-19 | MEDIUM | Timer polling continues after logout and when idle | 04 | N | 1 | fixed (775c3c0) | W1-14 |
| DOM-07 | MEDIUM | No consent capture for photos, marketing, AGB | 05 | N | 1 | partial: consent purposes (photo_use, marketing, email_contact) exist and can be granted via ConsentPanel (996703f, f976482); nothing yet enforces them before use | W1-05 |
| GDPR-09 | MEDIUM | Valuation PDF not ADMIN-only; repair insurance value plain, unaudited | 07 | N | 1 | partial: valuation PDF export restricted to ADMIN (90fe1b5); repair_jobs.estimated_value still plaintext and unaudited (deferred to W5-06) | W1-04 (encryption W5-06) |
| GDPR-10 | MEDIUM | Customer names/emails in request logs via query strings | 07 | N | 1 | fixed (b315d25, 54c0815) | W1-20 |
| GDPR-11 | MEDIUM | No consent or objection management at all | 07 | N | 1 | partial: consent store and capture UI built (996703f, f976482); no self-service objection/withdrawal beyond staff-initiated revoke, no enforcement yet | W1-05 |
| GDPR-13 | MEDIUM | Internal staff text sent to customers in automatic emails | 07 | N | 1 | fixed (4fb66d7) | W1-12 |
| VER-02 | MEDIUM | Repair-ready notifications skip WebSocket publish | VFD | Y (new) | 1 | fixed (4fb66d7) | W1-12 |
| SEC-13 | LOW | Time-entry stop/edit/interrupt lack owner check | 02 | N | 1 | fixed (d5f4b22) | W1-17 |
| SEC-15 | LOW | Remaining audit-log gaps for financial reads | 02 | N | 1 | open | W1-04 |
| SEC-17 | LOW | Login timing oracle for account enumeration | 02 | N | 1 | fixed (ec46dd6) | W1-03 |
| SEC-18 | LOW | Image decompression bomb headroom vs 512 MB container | 02 | N | 1 | fixed (77c7a35) | W1-18 |
| BE-25 | LOW | Duplicate invoice/quote line builders with hardcoded 75.0 rate | 03 | N | 1 | open | W1-07 |
| OPS-15 | LOW | AUTH_REVOCATION_FAIL_CLOSED undocumented in .env.example | 06 | N | 1 | fixed (948ddf5) | W1-02 |
| GDPR-19 | LOW | Photo originals keep EXIF; labels print full names (incl. F-9) | 07 | N | 1 | partial: EXIF stripped from stored originals (77c7a35); labels still print full names, initials-only setting not implemented | W1-18 |
| ARCH-01 | HIGH | Order lifecycle unmodelled; status history never written | 01 | Y | 2 | fixed (e5511ef, 34d1c6d, 4acfa8d) | W2-07 |
| BE-06 | HIGH | Order status not a state machine; no history | 03 | Y | 2 | fixed (e5511ef, 4acfa8d) | W2-07 |
| FE-05 | HIGH | Dashboard drops overdue orders; failure shows "alles erledigt" | 04 | Y | 2 | fixed (9bb29ba, f6b4c57) | W2-03 |
| FE-08 | HIGH | Frontend never subscribes to channels the backend publishes | 04 | Y | 2 | fixed (c8065f8, faa106e) | W2-13 |
| FE-13 | HIGH | No order-photo upload; gallery uses unservable URLs | 04 | Y | 2 | fixed (2d1a92d, 342ac5a, f5cf713) | W2-01 |
| DOM-01 | HIGH | No way to upload order photos; scanner photo goes nowhere | 05 | Y | 2 | fixed (8f8e1b9, f5cf713) | W2-01 |
| DOM-02 | HIGH | Walk-in customers without email cannot be created | 05 | Y | 2 | fixed (16eb65a) | W2-10 |
| DOM-03 | HIGH | Consultation conversion drops deadline, type, metal, measurements, photos | 05 | Y | 2 | fixed (ef3b1f8) | W2-05 |
| DOM-04 | HIGH | No gemstone capture (4C, Fassung, customer stone) | 05 | Y | 2 | partial: gemstone capture (4C, Fassung, Kundenstein) built (a57beac); not wired into quote/invoice PDF rendering, and a new order must be saved before stones can be added | W2-06 |
| DOM-11 | HIGH | Quote "Versenden" only flips status, sends nothing | 05 | Y | 2 | fixed (34d1cfb) | W2-05 |
| DOM-11b | HIGH | Quote-to-order conversion drops lines, metal, weight, deadline | 05 | Y | 2 | fixed (ef3b1f8) | W2-05 |
| DOM-12 | HIGH | Repairs get no customer updates; false customer_notified_at | 05 | Y | 2 | fixed (664231b, 718791a) | W2-02 |
| DOM-13 | HIGH | No Storniert or Pausiert order statuses | 05 | Y | 2 | fixed (34d1c6d, e5511ef) | W2-07 |
| DOM-14 | HIGH | Overdue orders ranked lowest on dashboard | 05 | Y | 2 | fixed (9bb29ba, f6b4c57) | W2-03 |
| DOM-15 | HIGH | Dashboard ignores repairs and customer-pending items | 05 | Y | 2 | fixed (9bb29ba, f6b4c57) | W2-03 |
| DOM-22 | HIGH | Hallmark vocabulary too narrow, forces false Feingehalt records | 05 | Y | 2 | fixed (70d799b) | W2-09 |
| DOM-24 | HIGH | Invoice PDF lacks §14 UStG seller data and Leistungsdatum | 05 | Y | 2 | partial: WorkshopSettings/NumberSequence back full §14 UStG invoice content and gap-free numbering (4286fc2); `templates/invoice.html` preview not updated to the new layout, and issuing with incomplete Werkstatt-Stammdaten only warns rather than blocking | W2-04 |
| BE-16 | MEDIUM | Sequential numbers use unlocked MAX+1; break at 10,000 | 03 | N | 2 | fixed (4286fc2) | W2-04 |
| BE-19 | MEDIUM | Interruptions never reduce time; actual_hours frozen at completion | 03 | N | 2 | fixed (93889f8) | W2-14 |
| BE-20 | MEDIUM | Events published to unsubscribed channels; Redis lacks timeouts | 03 | N | 2 | partial: fan-out hub with Redis timeouts and bool return landed (c8065f8, faa106e); repair_updates, material_updates, consultation_updates, metal_price_updates and anomaly_alerts still have no subscriber | W2-13 |
| BE-22 | MEDIUM | Metal price feed treats USD as EUR; Pt priced at 999 | 03 | N | 2 | fixed (60a8289) | W2-15 |
| FE-17 | MEDIUM | Walk-in repair intake takes customer as numeric ID | 04 | N | 2 | fixed (470d3b0, 3b91696) | W2-12 |
| FE-18 | MEDIUM | Cross-page hand-offs pass query params nobody reads | 04 | N | 2 | partial: send-quote flow now records agreement evidence (34d1cfb); `/quotes` still ignores `?quote_id` and the dashboard's quote row opens the list, not the specific quote (fix-w2-03-dashboard.md) | W2-05 |
| DOM-05 | MEDIUM | Ring-size requirement triggered by substring "ring" (Ohrring) | 05 | N | 2 | fixed (a57beac) | W2-06 |
| DOM-06 | MEDIUM | Metal and alloy entered twice and can contradict | 05 | N | 2 | fixed (a57beac): single alloy picker replaces double entry; legacy metal types (333/900 gold) still missing from the picker | W2-06 |
| DOM-08 | MEDIUM | Repair intake has no signed receipt or conditions | 05 | N | 2 | partial: single-screen counter intake with a printed Annahmeschein (3b91696, 470d3b0); digital signature capture explicitly stopped, no schema change made | W2-12 |
| DOM-09 | MEDIUM | Order form never sets order_type; estimator exact tier starves | 05 | N | 2 | fixed (a57beac) | W2-06 |
| DOM-11c | MEDIUM | Metal price source not shown when quoting | 05 | N | 2 | fixed (60a8289) | W2-15 |
| DOM-15b | MEDIUM | Dashboard widgets truncated at 100 orders | 05 | N | 2 | fixed (9bb29ba, f6b4c57) | W2-03 |
| DOM-16 | MEDIUM | Order history tab does not show status history | 05 | N | 2 | fixed (962edbd, 487d3e2) | W2-08 |
| DOM-17 | MEDIUM | 13 tabs on the order page | 05 | N | 2 | fixed (72b9e9e): order page collapsed from up to 14 tabs to 5 | W2-08 |
| DOM-18 | MEDIUM | Status change is 9 free buttons, no next-step guidance | 05 | N | 2 | fixed (b033057, 1aa8f0b): "Weiter" button plus a reason dialog for hold/cancel | W2-08 |
| DOM-21 | MEDIUM | No ID capture or Ankaufsbuch for Altgold buy-ins | 05 | N | 2 | fixed (abd162c): Altgold ID capture and Ankaufsbuch export; GDPR export/retention of the captured ID fields still open (W2-16 follow-up) | W2-16 |
| DOM-23 | MEDIUM | Punzierung hard gate, scanner-only, raw error on order page | 05 | N | 2 | fixed (70d799b, 3938c25) | W2-09 |
| DOM-24b | MEDIUM | No Storno/credit-note flow; issued invoices editable | 05 | N | 2 | fixed (4286fc2): Storno/credit-note flow with immutable linkage | W2-04 |
| DOM-30 | MEDIUM | Customer updates manual only; no milestone prompts | 05 | N | 2 | fixed (1aa8f0b, 72b9e9e) | W2-08 |
| DOM-34 | MEDIUM | Insurance valuation has no UI | 05 | N | 2 | fixed (f6f5628) | W2-11 |
| DOM-35 | MEDIUM | No care instructions or warranty at handover | 05 | N | 2 | partial: handover PDF now includes care instructions (f6f5628); text is hardcoded, not workshop-editable | W2-11 |
| DOM-38 | MEDIUM | Customer 360 misses repairs, consultations, quotes; invoices capped 200 | 05 | N | 2 | partial: Verlauf tab merges orders/repairs/quotes/invoices/updates (3340086, 49e2efd); consultations still missing from the merged view, invoices still capped at 200 | W2-12 |
| DOM-11d | LOW | Quote approvable from DRAFT without recorded agreement method | 05 | N | 2 | fixed (34d1cfb): `response_method` required to approve a quote | W2-05 |
| DOM-15c | LOW | No receivables or monthly revenue glance | 05 | N | 2 | open | W2-03 |
| DOM-44 | LOW † | Two unconnected hallmark systems (OrderHallmark register unused) | 05 | N | 2 | open: `frontend/src/api/hallmarks.ts` (orphaned OrderHallmark client) confirmed still dead by fix-w2-09-hallmark.md, not removed | W2-09 |
| DOM-46 | LOW † | Legacy NEW status still default and in labels | 05 | N | 2 | fixed (34d1c6d) | W2-07 |
| ARCH-03 | HIGH | Repository layer is 1.8k LOC dead code; routers run SQL | 01 | Y | 3 | open | W3-09 |
| ARCH-04 | HIGH | Background work in web process; 2 workers duplicate it | 01 | Y | 3 | partial: advisory-lock leader election for the system monitor (22612fb) plus a full transactional outbox and worker process (c4e4090, d41625b, f55fbaf, 1409dc8) now landed; lifespan-managed task cancellation in the web process (W3-10) still pending | W3-10 (outbox W6-01) |
| BE-14 | HIGH | Float money and round() cause cent errors on documents | 03 | Y | 3 | partial: invoice calculate_totals now Decimal/ROUND_HALF_UP (f827746); quote_service.calculate_totals and the full Numeric-column migration (~70 Float money columns) still pending (W3-11) | W3-11 |
| FE-06 | HIGH | Lists, pickers, dashboards silently cap at 100/200 rows | 04 | Y | 3 | partial: `Page[T]` envelope with server-side filter/search live for orders, repairs, quotes, materials, time-tracking, notifications (7e48494, 8dff361); frontend does not yet send `offset` or consume the envelope; customers, invoices, activities, comments, users and calendar endpoints remain unpaginated | W3-08 |
| ARCH-06 | MEDIUM | No frontend server-state layer; lists truncate, never refresh | 01 | N | 3 | open | W3-03 |
| ARCH-07 | MEDIUM | API types hand-maintained on both sides, no generated contract | 01 | N | 3 | fixed (f532896, d0cbb13, 8dff361) | W3-02 |
| ARCH-08 | MEDIUM | Inconsistent pagination, error envelope, prefixes, exception mapping | 01 | N | 3 | partial: `DomainError` hierarchy with one handler, and the `Page[T]` envelope, both landed (5183407, 7e48494, 8dff361); 63 router except-blocks still hand-map errors instead of raising `DomainError` | W3-07 (pagination W3-08) |
| ARCH-11 | MEDIUM | Real-time fan-out per socket, no lifecycle, partly unused | 01 | N | 3 | partial: one Redis subscriber per process (was per-socket) via the new RealtimeHub (c8065f8); lifespan-managed task cancellation still pending (W3-10) | W3-10 |
| BE-15 | MEDIUM | Timezone-aware inputs reach naive columns (fails on PG) | 03 | N | 3 | partial: UtcNaiveDatetime normalisation applied to invoice due_date/paid_date and time-entry end_time; app-wide sweep of ~98 naive DateTime columns still pending (W3-11) | W3-11 |
| FE-12 | MEDIUM | Role enum casing drift hides admin metal-type manager | 04 | N | 3 | fixed (f532896): generated types fixed the uppercase/lowercase role-enum casing drift | W3-02 |
| FE-14 | MEDIUM | ErrorBoundary retry never reloads; resets on every re-render | 04 | N | 3 | open | W3-01 |
| FE-15 | MEDIUM | No ESLint at all; hooks rules unenforced | 04 | N | 3 | partial: ESLint 9 with react-hooks and jsx-a11y rolled out (445b5bd, 1f0c253, ee852ed); 5 errors remain in `OrderFormModal.tsx` (owned by another in-flight agent) | W3-06 |
| FE-16 | MEDIUM | Forms: mixed validation, raw axios errors, no dirty guard | 04 | N | 3 | open | W3-05 |
| FE-20 | MEDIUM | No cancellation or dedupe; 54 copies of loading boilerplate | 04 | N | 3 | open | W3-03 |
| SEC-F5 | MEDIUM † | PUT /admin/email-config changes one worker only, lost on restart | 02 | N | 3 | open | W3-10 |
| SEC-12 | LOW | WebSocket auth skips revocation and is_active; accepts ?token= | 02 | N | 3 | partial: unchanged since W2-13 — `/ws/events` checks token revocation; `?token=` query auth, `is_active` and Origin checks still pending (W3-10 not started) | W3-10 |
| SEC-16 | LOW | Unbounded limit on 7 list endpoints | 02 | N | 3 | fixed (7e48494): legacy (non-paged) list responses now capped at limit ≤500 | W3-08 |
| BE-24 | LOW | Dead repository layer references non-existent columns | 03 | N | 3 | open | W3-09 |
| BE-26 | LOW | Unlimited list endpoints; stray test DBs in repo root | 03 | N | 3 | partial: unbounded-limit part addressed for the 6 paged endpoints via the `Page[T]` cap (7e48494); customers/invoices lists and the stray test-DB cleanup remain | W3-08 |
| FE-22 | LOW | Dead components, eager recharts, public sourcemaps | 04 | N | 3 | open | W3-01 |
| FE-23 | LOW | Accessibility mechanics: clickable divs, tabs without roles | 04 | N | 3 | partial: many clickable-div/static-interaction and label-association defects fixed via the ESLint jsx-a11y rollout (445b5bd, 1f0c253, ee852ed); 5 remain in `OrderFormModal.tsx` | W3-04 |
| FE-24 | LOW | Derived state in effects; 13 status-label maps drift | 04 | N | 3 | open | W3-04 |
| OPS-13 | LOW | Frontend ESLint config missing; issue #33 open | 06 | N | 3 | partial: same ESLint rollout as FE-15; 5 errors remain in `OrderFormModal.tsx`, `yarn lint`/CI `lint-frontend` not yet green | W3-06 |
| DES-01 | HIGH | Primary CTA, links, active nav fail AA contrast | 08 | Y | 4 | partial: primary-colour token and the backend theme default both moved to AA contrast (54f9c3b, 7c30827); a few hardcoded non-token hex values remain in `order-detail.css`/`dashboard.css` | W4-01 |
| DES-02 | HIGH | Focus ring 2.15:1; 33 outline:none | 08 | N | 4 | fixed (54f9c3b): global `:focus-visible` ring overrides 35 pre-existing `outline:none` rules, 0 introduced AA failures; ring width shipped at 2px vs. the playbook's 3px, flagged not reconciled | W4-01 |
| DES-03 | HIGH | 6 of 10 order statuses unstyled; 8+ badge systems | 08 | Y | 4 | fixed (54f9c3b, dc83d95): full tone coverage for 10 order + 9 repair statuses | W4-02 |
| DES-04 | HIGH | Deadline urgency colour-only; absent from Orders list | 08 | N | 4 | open | W4-02 |
| DES-05 | HIGH | Global class collisions (.btn-primary x7, .modal-* x4-5) | 08 | N | 4 | partial: Button/IconButton/Card primitives with one API now exist in `src/ui` (163a781); legacy `.btn-primary`/`.modal-*` collisions not yet removed from existing pages (migration is W4-05..W4-07) | W4-09 |
| DES-06 | HIGH | No Button/IconButton API; .btn below 44px | 08 | N | 4 | partial: Button/IconButton primitives meet the 44px minimum (163a781); not yet adopted outside `src/ui` | W4-03 |
| DES-07 | HIGH | Modals lack dialog role, Escape, focus trap; backdrop loses data | 08 | N | 4 | partial: Modal/Dialog/Sheet primitive has dialog role, Escape, focus trap and a dirty-guard (25b75ff); existing ConfirmDialog/useConfirm and legacy modals not yet migrated onto it | W4-03 |
| DES-08 | HIGH | 1,580 hex values, 9 golds, 41 undefined custom properties | 08 | partial | 4 | partial: hex-literal ratchet wired into pre-commit/CI (b1f3b6a), count trending down (2113→2086); 37 of 42 undefined custom properties repointed to semantic tokens (54f9c3b); not eliminated | W4-01 |
| DES-10 | HIGH | Offline banner hidden under sticky header | 08 | N | 4 | fixed (54f9c3b): offline-banner/drawer z-index layering fixed, building on the earlier sticky-header fix (4e18bf0) | W4-01 |
| DES-12 | HIGH | No bottom nav on mobile; header overflows at 390px | 08 | N | 4 | open | W4-04 |
| DES-14 | HIGH | Owner (ADMIN) lands on KPI dashboard, not bench worklist | 08 | N | 4 | open | W4-04 |
| DES-15 | HIGH | Orders table lacks customer/photo; rows not keyboard reachable | 08 | N | 4 | open | W4-05 |
| DES-26 | HIGH | Client portal: no photos, generic name, 1.65:1 footer | 08 | N | 4 | open | W4-08 |
| DES-28 | HIGH | Type and targets too small at the bench (Werkbank-Modus) | 08 | N | 4 | open | W4-04 |
| DES-09 | MEDIUM | 50 font sizes, 15+ radii, 98 shadows, ad hoc z-index | 08 | N | 4 | partial: semantic spacing/type/radius/shadow/z-index tokens added (54f9c3b); legacy z-index literals not yet remapped | W4-01 |
| DES-11 | MEDIUM | 12 flat nav links; settings page unreachable | 08 | N | 4 | open | W4-04 |
| DES-13 | MEDIUM | Dark mode announced but provider and toggle unmounted | 08 | Y | 4 | open | W4-10 |
| DES-16 | MEDIUM | Edit and delete emoji buttons adjacent in every row | 08 | N | 4 | open | W4-05 |
| DES-17 | MEDIUM | ASCII or dropped umlauts in UI copy (about 20 sites) | 08 | N | 4 | partial: ASCII-umlaut fallbacks fixed across Scanner/Quotes/dashboard/Settings/Portal (e451ef5, 36509cd, 862189f); CustomerFormModal, Toast, CommentsTab, ScrapGoldTab, ScanOverlay, QuickActionModalV2, UserSettingsPage and the generated `schema.d.ts` still have ASCII fallbacks | W4-01 |
| DES-18 | MEDIUM | Empty states text-only, no next action | 08 | N | 4 | partial: `EmptyState`/`PageState` primitives with a next-action slot now exist in `src/ui` (c69d9a0); not yet adopted by existing empty states | W4-03 |
| DES-19 | MEDIUM | 13+ loading and 5+ error patterns; #ff4444 fails contrast | 08 | N | 4 | partial: status/error colour tokens covered by the W4-01 sweep; `PageState` primitive built (c69d9a0) to consolidate loading/error patterns, not yet adopted across the 13+/5+ existing call sites | W4-03 |
| DES-20 | MEDIUM | Vite template leftovers in index.css | 08 | N | 4 | open | W4-09 |
| DES-21 | MEDIUM | Inter never loaded; no tabular numerals | 08 | N | 4 | open | W4-03 |
| DES-22 | MEDIUM | Emoji icons; no domain icons | 08 | N | 4 | partial: an inline icon set now exists in `src/ui` (7c379c0-area, W4-02); not yet adopted to replace emoji icons; a real icon library deferred (needs a package.json change) | W4-03 |
| DES-24 | MEDIUM | Three scanner entry points, two scanner UIs | 08 | N | 4 | open | W4-04 |
| DES-25 | MEDIUM | Tailwind installed yet banned by plan; mixed usage | 08 | N | 4 | open | W4-09 |
| DES-27 | MEDIUM | Admin theme colours set without contrast checks | 08 | N | 4 | fixed (7c30827): admin theme colours now contrast-gated both client-side (`useTheme.ts`) and server-side on `PUT /theme`; default moved to AA-compliant `#b45309` | W4-01 |
| DES-23 | LOW | 222 inline style={{}} in 37 files | 08 | N | 4 | open | W4-07 |
| DES-29 | LOW | Hover lifts on touch; few reduced-motion guards | 08 | N | 4 | partial: covered nominally by the W4-01 token sweep per its own findings list; no reduced-motion/hover-on-touch specific fix documented, no screenshot verification run | W4-01 |
| DES-30 | LOW | Dead code: OrderList, unused @utility set, ThemeToggle | 08 | N | 4 | open | W4-09 |
| OPS-06 | HIGH | 35 open Dependabot alerts (1 critical, 20 high) | 06 | N | 5 | fixed (94a272f, 250e5a9): Dependabot critical/high cleared; remaining `ecdsa` transitive vuln removed by replacing python-jose with PyJWT | W5-01 |
| GDPR-05 | HIGH | Art. 15 export incomplete and ADMIN-only | 07 | Y | 5 | fixed (7b1d756) | W5-08 |
| GDPR-06 | HIGH | Backups unencrypted; cloud sync URL-only auth; no key escrow | 07 | Y | 5 | fixed (3f0e7f7) | W5-05 |
| GDPR-07 | HIGH | Restore then re-run cleanup misses later erasures | 07 | Y | 5 | fixed (3f0e7f7): restore-then-replay erasure ledger | W5-05 |
| GDPR-08 | HIGH | No storage limitation for most personal data | 07 | Y | 5 | fixed (15bd0c0): retention schedule and `RETENTION_EXECUTE` gate, dry-run by default | W5-07 |
| ARCH-12 | MEDIUM | Observability stops at JSON logs; no error tracking | 01 | N | 5 | partial: worker/outbox admin panel gives some queue observability (d099e0e); no error tracking (Sentry/GlitchTip) wired yet (W5-12 not started) | W5-12 |
| SEC-14 | MEDIUM | Plaintext signatures/notes/financial columns; unencrypted backups | 02 | N | 5 | open | W5-06 |
| SEC-F4 | MEDIUM † | Backup/GDPR alerts never arrive; off-site sync silently off | 02 | N | 5 | open | W5-05 |
| OPS-01 | MEDIUM | Four of six E2E specs never run in CI | 06 | N | 5 | fixed (23fd91c): nightly workflow wires the 4 previously-unrun E2E specs | W5-02 |
| OPS-02 | MEDIUM | Frontend coverage tool not installed; config dead | 06 | N | 5 | fixed (40fe1a4): frontend coverage tool installed, baseline established | W5-02 |
| OPS-03 | MEDIUM | mypy green via 1,532-error baseline without shrink pressure | 06 | N | 5 | open | W5-02 |
| OPS-04 | MEDIUM | No CI dependency caching | 06 | N | 5 | fixed (533e62d) | W5-02 |
| OPS-05 | MEDIUM | No local make test/lint targets | 06 | N | 5 | fixed (533e62d) | W5-03 |
| OPS-07 | MEDIUM | Compliance systemd timers exist but nothing installs them | 06 | N | 5 | fixed (33cce19) | W5-03 |
| GDPR-14 | MEDIUM | Per-employee accuracy analytics not in Art. 30 record | 07 | N | 5 | open | W5-09 |
| GDPR-15 | MEDIUM | SMTP, backup host, accounting export not covered as processors | 07 | N | 5 | partial: processors list documented (537594a); TLS-on-every-SMTP-port enforcement still open (tracked to W5-09) | W5-09 |
| GDPR-16 | MEDIUM | Cleanup/retention timers not installed; point at dev compose | 07 | N | 5 | partial: `install-timers.sh` and the `RETENTION_EXECUTE` gate landed (33cce19, 15bd0c0); the systemd cleanup service's default `COMPOSE_FILE` still points at the dev compose file | W5-03 |
| GDPR-17 | MEDIUM | No breach-response runbook or register (Art. 33/34) | 07 | N | 5 | fixed (863b38c): breach-response runbook and Art. 30/33/34 documents | W5-10 |
| ARCH-14 | LOW | Migrations and seed run on every boot; PWA caches orders | 01 | N | 5 | open | W5-12 |
| ARCH-16 | LOW | Architecture docs stale; no ADRs | 01 | N | 5 | partial: single-box deployment ADR added, stale docs archived (03bf8ac); the C4/likec4 model and other ADRs (jose, estimator, no-portal) not done | W5-11 |
| SEC-F7 | LOW † | Caddy internal root CA not in backup plan | 02 | N | 5 | open | W5-05 |
| SEC-F8 | LOW † | SameSite=Strict on IP site: never co-host other web apps | 02 | N | 5 | fixed (2d748f6) | W5-11 |
| SEC-F10 | LOW † | Demo seed accounts use known password demo2026! | 02 | N | 5 | fixed (2d748f6): documented as a known limitation | W5-11 |
| OPS-08 | LOW | docs/DEPLOYMENT.md stale and misleading | 06 | N | 5 | fixed (2d748f6): stale DEPLOYMENT.md archived, rollback and log rotation documented | W5-11 |
| OPS-09 | LOW | Redis publish-to-WebSocket path fully mocked in tests | 06 | N | 5 | open | W5-04 |
| OPS-10 | LOW | "Passes on PostgreSQL" xfail claim never checked | 06 | N | 5 | open | W5-02 |
| OPS-11 | LOW | No dependency vulnerability scan in CI | 06 | N | 5 | fixed (a3642f1): advisory pip-audit/yarn audit added | W5-02 |
| OPS-12 | LOW | ruff and pylint not run in CI | 06 | N | 5 | fixed (a3642f1): ruff added to the CI lint job, non-blocking baseline | W5-02 |
| OPS-14 | LOW | Seven stale worktrees and stray alembic_backup/ | 06 | N | 5 | fixed (c3df1a4): read-only stale-worktree/branch reporter | W5-13 |
| GDPR-18 | LOW | Encryption hardening: tolerate_plaintext, no rotation path | 07 | N | 5 | open | W5-06 |
| ARCH-02 | HIGH | Order and RepairJob duplicate aggregates; repairs cannot be invoiced | 01 | Y | 6 | open | W6-04 |
| ARCH-05 | HIGH | Customer communication is a side effect of staff notifications | 01 | Y | 6 | fixed (777137d, 2669451): CustomerMessageService is the single outbound customer path; quotes routed through it too | W6-02 |
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
