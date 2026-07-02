# Goldsmith ERP — Product Vision & Roadmap (July 2026)

Status: **Draft — pending review by Anne/Max**
Basis: codebase inventory of `main` (e8197ed) + market research
(`docs/technical/research/MARKET_RESEARCH_2026-07.md`), 2026-07-02.

## Decisions taken (confirmed with Max, 2026-07-02)

| Decision | Choice |
|---|---|
| Customer reach | **No live portal for now** — email/PDF progress updates with logged approvals; data model stays portal-ready (tokens) so a hosted portal can be added later without rework |
| Audience | **Anne first, sellable later** — single-workshop deployment, German UI, but no hardcoded shop assumptions; `tenant_id` stub already exists |
| Next-milestone focus | **Consultation/intake** and **customer updates + cost approval** |
| Cost calculator ambition | **Statistical, not ML** — analogous estimating from historical similar jobs + live metal prices; transparent and explainable |

## Assumptions to confirm (chosen by recommendation; Anne/Max can override)

1. **Milestone order** V1.1 Intake → V1.2 Updates/Approval → V1.3 Estimator
   (intake produces the structured data the other two consume).
2. **Sketch capture** = photo of the paper sketch via the existing photo
   pipeline (drawing canvas deferred to backlog).
3. **Email sending** = SMTP through the workshop's existing mailbox
   (no transactional-email vendor); approval evidence = customer email reply
   logged in the system.

## The vision in one paragraph

A goldsmith runs her whole workshop from one locally-hosted system: a customer
walks in and experiences a professional guided consultation (wishes, budget,
measurements, sketches, no-gos captured on a tablet); the resulting quote is
produced in minutes from live metal prices plus labor estimates learned from
her own past jobs; the piece gets a QR tag and every step, photo, material
draw and minute of work attaches to it; the customer receives progress emails
with photos, and if the cost is going to exceed the estimate she is notified
and her approval is captured — keeping the goldsmith §649 BGB-safe; delivered
pieces feed their actuals back into the estimator, so every job makes the next
quote better.

## Where we stand (inventory of `main`, 2026-07-02)

Already mature — do not rebuild:

| Area | State |
|---|---|
| Customers | Encrypted PII, GDPR export/erasure, audit log, measurements library, preferences/allergies/tags |
| Orders | 9-status lifecycle + history, handoffs, hallmark (Punzierung) compliance, order comments, repairs as parallel pipeline |
| QR | Label generation with QR per order/repair, camera scanner, scan log (offline-capable), adoption dashboard — **all slice branches merged** |
| Photos | Upload/thumbnails per order; repair photos phased intake/during/completed |
| Materials | Metal inventory (FIFO/LIFO/avg), Altgold module with signature workflow, gemstones, usage-per-order |
| Money | Deterministic cost calculator, quotes (Kostenvoranschlag), invoices |
| ML | Duration prediction, anomaly detection, inventory depletion forecast |
| Time | Full tracking incl. interruptions, billable flag, summary endpoint |
| Infra | 3-role RBAC (~40 permissions), WebSockets, PWA, rate limiting, audit logging |
| Portal | Status-only lookup (reference+email), deliberately no PII/photos/costs |

### Gap analysis vs the vision

| # | Vision feature | Status | Gap |
|---|---|---|---|
| 1 | Consultation/intake (wishes, sketches, no-gos, style profile) | **Missing** | No models, services, or UI at all; only free-text notes |
| 2 | Customer progress updates with photos | **Missing** | Portal shows status text only; no email updates, no photo sharing |
| 3 | Cost-overrun notification + customer approval (§649 BGB) | **Missing** | Quotes exist, but no projected-cost watch, no change request, no approval evidence |
| 4 | Live metal prices | **Partial** | `MetalPriceHistory` exists but manual entry only — no scheduled API sync |
| 5 | Learning labor estimator | **Partial** | ML infra (`find_similar_orders`) exists for *duration*, not wired into *pricing* |
| 6 | NFC scanning | Missing | QR done; Web NFC never built (low priority — QR covers the workflow) |
| 7 | Consent tracking, vault mgmt, payment reminders, DATEV export | Missing | Known SPEC_V2 leftovers, backlog |

## Roadmap

### V1.1 — Consultation & Intake (`SPEC_V1_1_CONSULTATION_INTAKE.md`)

The "wow" moment when a customer walks in. Guided tablet flow: customer →
occasion/budget → wishes → style profile & no-gos → measurements → sketch/
reference photos → summary → convert to quote or order. New `Consultation`
model linked to customer/quote/order; sketches ride the existing photo
pipeline; no-gos become structured, persistent customer data. Includes the
photo-intake checklist for repairs (dispute protection).

### V1.2 — Customer Updates & Cost Approval (`SPEC_V1_2_CUSTOMER_UPDATES_COST_APPROVAL.md`)

Progress emails with explicitly selected photos (design-IP rule: nothing is
shared by default). Projected-cost watcher compares quote vs (materials
consumed + tracked time × rate) and alerts at a configurable threshold
(default 15%). Cost change requests presented change-order style (what/why/
prior state), sent by email; approval evidence (email reply, in-person,
phone) logged with timestamp and recorder. Every update carries a token so a
hosted portal can later render the same content.

### V1.3 — Learning Cost Estimator (`SPEC_V1_3_LEARNING_COST_ESTIMATOR.md`)

Daily metal-price sync (Bundesbank reference price primary, MetalpriceAPI
optional). Labor estimation by analogous method: median + range of actual
hours from similar completed orders (type/technique/finish), shown with
sample size and confidence; goldsmith adjusts, system records estimate-vs-
actual and shows calibration over time. Quote UI gets a live, explainable
breakdown.

### Backlog (V1.4+, unordered)

- Hosted customer portal (reuse V1.2 tokens; tunnel or small cloud front-end)
- Drawing canvas for sketches (Morpholio-Trace-style annotate-over-photo)
- Occasion-based CRM triggers (birthdays, wedding anniversaries)
- Payment reminders (Mahnwesen), DATEV/Lexware export
- Vault/safe location management (Tresor)
- Consent tracking on customer record
- NFC tags, multi-workshop tenancy (tenant_id stub exists)

## Positioning (for "sellable later")

Market research found no product combining per-piece QR + photo progress +
approval workflow + learning estimator + Altgold + consultation capture.
DACH competitors: Joinpoints (€25/user/mo, kanban+sketch attachment, no
inventory/estimator), PrismaNote (€89–199/mo, Altgold+partial portal, no
QR/consultation). Differentiators to protect: consultation experience,
§649-compliance workflow, estimator that learns from the shop's own data,
fully self-hosted (data never leaves the workshop).

## Session handoff

Next steps, in order:
1. Anne/Max review this doc + the three specs; confirm or override the three
   assumptions above.
2. Write the V1.1 implementation plan (slice breakdown) from the spec.
3. Before V1.2 implementation: collect the workshop SMTP credentials and
   decide the sender address; legal wording of the overrun notice should get
   a once-over (Handwerkskammer template exists — see research doc §3).
