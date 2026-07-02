# SPEC V1.1 — Consultation & Intake (Beratung & Annahme)

Status: **Draft — pending review**
Date: 2026-07-02
Depends on: nothing new (builds on existing Customer, CustomerMeasurement,
Quote, Order, OrderPhoto, CalendarEvent)

## Goal

When a customer sits down at the bench, the goldsmith opens a guided,
tablet-friendly flow that captures everything about the wish — occasion,
budget, design ideas, sketches, measurements, hard exclusions — and converts
it into a Quote or Order in one tap. The customer sees a professional,
structured process; the system gains the structured data that V1.2 (updates)
and V1.3 (estimator) will consume.

Market context: no purpose-built jewelry consultation-intake product exists;
"style profile / no-gos" has no industry standard — we design it from scratch
(research doc §5).

## Scope

In: consultation record, style profile & no-gos, sketch/reference photo
capture (photo of paper sketch — no drawing canvas), guided intake UI,
conversion to quote/order, repair photo-intake checklist.
Out (backlog): drawing canvas, AR preview, customer-facing summary email
(that's V1.2 infrastructure), appointment self-booking.

## Domain model

### `Consultation` (new table)

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| customer_id | FK customers, required | |
| conducted_by | FK users | |
| calendar_event_id | FK calendar_events, nullable | links the APPOINTMENT |
| occasion | enum | engagement, wedding, anniversary, birthday, self, redesign (Umarbeitung), repair_consult, other |
| occasion_date | date, nullable | drives deadline discussion + CRM triggers later |
| budget_min / budget_max | Numeric, nullable | **financial data — ADMIN/GOLDSMITH visibility, audit-logged** (CLAUDE.md rule) |
| piece_type | OrderTypeEnum reuse | ring, chain, pendant, … |
| wishes | Text | free narrative, the goldsmith's words |
| materials_discussed | JSONB | e.g. [{"metal":"gold_585","tone":"rosé"}] |
| source_material | Text, nullable | customer brings Altgold / heirloom stones |
| status | enum | draft → completed → converted → archived |
| converted_quote_id / converted_order_id | FK, nullable | conversion outcome |
| follow_up_at | datetime, nullable | "wants to think about it" → reminder |
| notes | Text | anything unstructured |
| created_at / updated_at | | |

Wishes/notes/sketches are **design IP**: GOLDSMITH or ADMIN access only, never
in data exports without explicit consent (CLAUDE.md privacy rules).

### Style profile & no-gos (customer-level, persistent)

Extend `Customer` rather than new table — preferences JSON exists but no-gos
deserve first-class structure so they can *warn* later:

- `style_profile` JSONB on Customer: `{metal_tones: [], finishes: [],
  stone_preferences: [], style_words: []}` — filled progressively across
  consultations.
- New table `CustomerNoGo`: id, customer_id, category enum (metal, stone,
  finish, design_element, allergy, other), value (text), note, source
  (consultation_id nullable), created_at. Allergy no-gos sync with the
  existing `Customer.allergies` field (single source: NoGo table wins; keep
  the legacy field read-compatible).
- **Warning hook:** when an Order/Quote for the customer specifies an alloy or
  stone matching a NoGo (simple normalized string match on category+value),
  the UI shows a blocking warning ("Kundin: kein Nickel!") that must be
  explicitly dismissed. This is the feature's payoff.

### Sketches & reference photos

Reuse the photo pipeline. Generalize `OrderPhoto`-style storage with a new
`ConsultationPhoto` table: id, consultation_id, kind enum (sketch, reference,
inspiration, existing_piece), file_path, notes, taken_by, created_at. Same
magic-byte validation + thumbnails as `photo_service.py`. On conversion,
photos are linked (not copied) to the created order via a nullable
`order_id` so the bench sees the sketch.

### Measurements

No new model — the intake flow embeds the existing `MeasurementService`
(ring size ISO 8653 mm-circumference, chain/wrist lengths, per-finger) and
records `measured_at/by` provenance as today.

### Repair photo-intake checklist

For `RepairJob` intake: a configurable checklist (default: prongs, pavé,
engraving, hallmark, existing wear/damage — research doc §2) rendered in the
repair intake UI; each item satisfied by an attached `RepairPhoto`
(phase=intake) or an explicit "not applicable" with reason. Stored as JSONB
`intake_checklist` on RepairJob. Dispute protection, mirrors insurance
practice.

## API

New router `api/routers/consultations.py` (all `@require_permission`, new
permissions `CONSULTATION_VIEW/CREATE/EDIT` for ADMIN+GOLDSMITH; VIEWER gets
none — design IP):

- `POST /consultations` / `GET /consultations` (filter by customer, status)
- `GET/PATCH /consultations/{id}`
- `POST /consultations/{id}/photos` (multipart, kind param) + list/serve/delete
- `POST /consultations/{id}/convert` body `{target: "quote"|"order"}` —
  creates the Quote/Order pre-filled (customer, piece_type, materials,
  description from wishes), links photos, sets status=converted. Single
  transaction.
- `GET/POST/DELETE /customers/{id}/no-gos`
- `GET /customers/{id}/style-profile` / `PATCH`

## Frontend

Tablet-first guided flow (`ConsultationWizard`), one step per screen, progress
indicator, auto-save per step (draft status — a consultation interrupted by a
phone call must not lose data):

1. Customer — search existing (blind-index email search exists) or quick-create
2. Occasion & budget — chips + optional date; budget as range slider + free input
3. The wish — piece type, narrative wishes, materials discussed, source material (Altgold toggle → links to existing scrap-gold flow)
4. Style & no-gos — shows existing profile/no-gos, add new; allergy quick-flags (nickel!)
5. Measurements — embedded existing measurement UI
6. Sketches & references — camera capture (photo of paper sketch), kind tagging
7. Summary — read-back view designed to be *shown to the customer* (professional moment), then: convert to Quote / convert to Order / save with follow-up date

Plus: consultation list page, consultation section on CustomerDetail, NoGo
warning banner on Order/Quote forms.

German UI copy throughout (Beratung, Anlass, Budget, Wünsche, No-Gos,
Maße, Skizzen).

## Events & notifications

- Publish `consultation_updates` on create/convert (existing Redis pattern,
  after commit).
- `follow_up_at` generates a Notification + CalendarEvent (REMINDER type) via
  existing services.

## Error handling & edge cases

- Conversion is idempotent-guarded: converting an already-converted
  consultation returns 409 with the existing target id.
- Deleting a customer (GDPR erasure) cascades: consultations scrubbed
  (wishes/notes/budget nulled, photos deleted via existing
  `FileErasureService`), row kept with anonymized marker for Art. 30 records —
  same pattern as `scrub_customer_pii`.
- Draft consultations older than a configurable retention (default 180 days)
  surface in a cleanup list (minimum-data principle).

## Testing

- Unit: service CRUD, conversion transaction (quote + order variants),
  no-go matching/warning logic, GDPR scrub of consultations.
- Integration: full wizard API flow incl. photo upload; conversion idempotency;
  permission matrix (VIEWER blocked everywhere).
- E2E (Playwright): wizard happy path on tablet viewport (768px), draft
  auto-save resume, no-go warning appears on order form.
- Coverage target 80% on new modules (project standard).

## Open questions

1. Should budget be visible to VIEWER-role apprentices? (Spec says no —
   financial data rule. Confirm with Anne.)
2. Default consultation retention for non-converted drafts: 180 days OK?
3. Does Anne want a printable consultation summary (PDF) for the customer to
   take home? (Cheap add-on via existing PDF infra — proposed: yes, phase 2
   of V1.1.)
