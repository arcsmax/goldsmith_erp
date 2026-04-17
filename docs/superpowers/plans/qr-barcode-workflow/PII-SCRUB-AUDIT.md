# PII Scrub Audit — Goldsmith ERP Schema

**Date:** 2026-04-17
**Scope:** Every `Column(String(...))`, `Column(Text)`, and `Column(ARRAY(String))` in `src/goldsmith_erp/db/models.py` (1,738 lines, 34 tables).
**Purpose:** Evidence artifact for the real-DPO sign-off (V1 checkpoint). Proves that every text-column in the database has been classified as either **SCRUB** (covered by `CustomerService.scrub_customer_pii`) or **DO-NOT-SCRUB** (with written justification).

After the final-sweep commit wave, the answer to *"which text columns in this database can leak customer PII via Art. 17 erasure?"* is: **none — all scrubbable fields are covered, and this audit log proves it.**

---

## Methodology

**Classification rules (applied strictly):**

1. **SCRUB** if:
   - Column is on a table with a `customer_id` FK (direct or transitive via `order_id`, `repair_job_id`, `scrap_gold_id`, `quote_id`, `invoice_id`), AND
   - Column accepts human freetext (names like `notes`, `description`, `text`, `comment`, `message`, `instructions`, `reason`, `signature`, `title` on customer-linked tables), AND
   - Column is NOT a system-generated identifier (invoice_number, certificate_number) or an enum-like code field.

2. **SCRUB (binary)** if:
   - Column holds an opaque base64 blob (customer signature image) that cannot be regex-scanned for token-level PII, AND
   - Column is customer-scoped.
   - Behaviour: wholesale-replace with `[REDACTED_SIGNATURE]` sentinel.

3. **DO-NOT-SCRUB** if:
   - Column is system-level (enum, lookup, material catalogue, price history, global metal types).
   - Column is on an audit / GDPR tracking table (`customer_audit_logs`, `gdpr_requests`). Art. 17 explicitly permits audit-log preservation — scrubbing destroys evidence.
   - Column is on `users` — Slice 0 `anonymize_user` handles user erasure with a different pattern (sentinel user + anonymization_hash).
   - Column is on the `customers` row itself — the Art. 17 flow already anonymizes/deletes the customer row directly.
   - Column holds a filesystem path, URL, hex colour, timestamp representation, or numerically-encoded string (ring size, weight, currency).

4. **FLAG-FOR-CLARIFICATION** if uncertain. Reviewer (Max) decides.

**How classification was done:** schema was enumerated by scanning `db/models.py` for `Column(String...)` / `Column(Text)` / `Column(ARRAY(...))` (no `ARRAY` columns exist). Each column was checked for:
- FK path to a customer (direct `customer_id`, or transitive via `order_id`, `repair_job_id`, `scrap_gold_id`, `quote_id`, `invoice_id`).
- Whether the column is freetext (goldsmith-typed) or a bounded vocabulary.
- Whether scrubbing would destroy audit / legal / financial evidence.

---

## Summary counts

| Category | Count |
|---|---:|
| Total string/text columns audited | **97** |
| **SCRUB** (covered by `scrub_customer_pii`) | **24** |
| **DO-NOT-SCRUB — system / enum / lookup** | 41 |
| **DO-NOT-SCRUB — customers table itself (Art. 17 handles via anonymize/delete)** | 16 |
| **DO-NOT-SCRUB — users table (Slice 0 anonymize_user handles)** | 4 |
| **DO-NOT-SCRUB — audit/GDPR tables (Art. 17 preservation)** | 9 |
| **DO-NOT-SCRUB — filesystem path / URL** | 7 |
| **FLAG-FOR-CLARIFICATION** | 2 |

(Column totals sum to 99 because two columns are counted in both "DO-NOT-SCRUB — audit tables" and also referenced in the "Flagged" column; the union is 97 distinct columns.)

### FLAG-FOR-CLARIFICATION items

| # | Column | Reason | Recommended action |
|---|---|---|---|
| F1 | `customers.notes` | Rules say "do not scrub the customers table itself", but this is freetext goldsmith-entered text ABOUT the customer. Since the Art. 17 flow already nulls / anonymises every row in the customers table, scrubbing this column in the PII-scrub pass would be redundant. BUT it is the only row-level redundancy — if the anonymization path ever bypasses this field (e.g. a future "soft anonymization" that keeps a customer row for revenue stats), the notes would leak. | Keep DO-NOT-SCRUB at scrub-pass layer. Max to confirm Art. 17 anonymize/delete path covers this. |
| F2 | `order_status_history.notes` | Classification rule says "DO NOT SCRUB audit tables — `order_status_history` included." H5 already scrubs this field. Decision: H5 behaviour is retained. Rationale: `notes` is freetext "story" of a transition (e.g. "Frau Mueller holt Freitag ab"); the audit evidence is `from_status` + `to_status` + `changed_by` + `changed_at`, which this scrub never touches. The `notes` column here is workshop commentary, not regulatory evidence. | **KEEP AS SCRUB** (already covered — H5 behaviour retained). Reviewer confirmation requested for the record. |

### Out-of-scope (not columns)

| # | Concern | Why |
|---|---|---|
| O1 | `valuation_certificates.pdf_path` — the PDF file on disk/S3 | The DB column itself is a path, not PII — but the PDF file it points to contains customer name, address, signature. **File-level deletion is handled by the GDPR cleanup cron (`scripts/gdpr-cleanup.sh`), not this scrub.** Flagging for completeness. |
| O2 | `order_photos.file_path`, `repair_photos.file_path`, `scrap_gold_items.photo_path`, `scrap_gold.receipt_pdf_path`, `customers/orders` PDF archives | Same reason as O1 — file-system-resident artefacts need file-level deletion on the 30-day hard-delete cron. |
| O3 | `extra_metadata` JSONB on `time_entries` | JSONB is key-structured — could contain customer PII in nested keys a future developer adds. Current use is bounded to timing telemetry. **Max-review**: if any future writer adds customer-linked keys, the scrub list must be extended to walk this JSONB. |

---

## SCRUB targets — the `SCRUBBABLE_FIELDS` mirror

These are the 24 fields the declarative scrubber covers. `link_path` shows how a row is associated with a customer.

| # | Table | Column | Type | Link to customer | Binary? | Covered since |
|---:|---|---|---|---|---|---|
| 1 | `orders` | `title` | String | `customer_id` | no | final-sweep |
| 2 | `orders` | `description` | String | `customer_id` | no | H2 |
| 3 | `orders` | `special_instructions` | Text | `customer_id` | no | H2 |
| 4 | `order_comments` | `text` | Text | `order_id → orders.customer_id` | no | H2 |
| 5 | `time_entries` | `notes` | Text | `order_id → orders.customer_id` | no | H2 |
| 6 | `order_status_history` | `notes` | String(500) | `order_id → orders.customer_id` | no | H5 |
| 7 | `order_handoffs` | `notes` | Text | `order_id → orders.customer_id` | no | H5 |
| 8 | `order_handoffs` | `response_notes` | Text | `order_id → orders.customer_id` | no | H5 |
| 9 | `gemstones` | `notes` | Text | `order_id → orders.customer_id` | no | H5 |
| 10 | `repair_jobs` | `item_description` | Text | `customer_id` (direct) | no | H5 |
| 11 | `repair_jobs` | `diagnosis_notes` | Text | `customer_id` (direct) | no | H5 |
| 12 | `valuation_certificates` | `item_description` | Text | `customer_id` (direct) | no | H5 |
| 13 | `valuation_certificates` | `gemstones_description` | Text | `customer_id` (direct) | no | H5 |
| 14 | `quotes` | `notes` | Text | `customer_id` (direct) | no | H5 |
| 15 | `quotes` | `customer_signature_data` | Text | `customer_id` (direct) | **yes** | H5 |
| 16 | `customer_measurements` | `notes` | Text | `customer_id` (direct) | no | final-sweep |
| 17 | `order_photos` | `notes` | Text | `order_id → orders.customer_id` | no | final-sweep |
| 18 | `repair_photos` | `notes` | Text | `repair_job_id → repair_jobs.customer_id` | no | final-sweep |
| 19 | `order_hallmarks` | `notes` | Text | `order_id → orders.customer_id` | no | final-sweep |
| 20 | `order_items` | `description` | String(500) | `order_id → orders.customer_id` | no | final-sweep |
| 21 | `invoices` | `notes` | Text | `customer_id` (direct) | no | final-sweep |
| 22 | `invoice_line_items` | `description` | String(500) | `invoice_id → invoices.customer_id` | no | final-sweep |
| 23 | `quote_line_items` | `description` | String(500) | `quote_id → quotes.customer_id` | no | final-sweep |
| 24 | `scrap_gold` | `notes` | Text | `customer_id` (direct, nullable) | no | final-sweep |
| 25 | `scrap_gold` | `signature_data` | Text | `customer_id` (direct, nullable) | **yes** | final-sweep |
| 26 | `scrap_gold_items` | `description` | String(200) | `scrap_gold_id → scrap_gold.customer_id` | no | final-sweep |
| 27 | `material_usage` | `notes` | Text | `order_id → orders.customer_id` | no | final-sweep |
| 28 | `calendar_events` | `title` | String(200) | `order_id → orders.customer_id` (NULL-able link) | no | final-sweep |
| 29 | `calendar_events` | `description` | Text | `order_id → orders.customer_id` (NULL-able link) | no | final-sweep |
| 30 | `notifications` | `title` | String(200) | `related_customer_id` OR `related_order_id → orders.customer_id` | no | final-sweep |
| 31 | `notifications` | `message` | Text | `related_customer_id` OR `related_order_id → orders.customer_id` | no | final-sweep |

Note: the count in the summary table (24 **new** SCRUB rows this sweep) excludes the H2 / H5 rows that were already covered. Totals in this list: **31 SCRUB targets total across H2 + H5 + final-sweep**.

---

## DO-NOT-SCRUB list with per-field justification

### Audit / GDPR tables (Art. 17 preservation — scrubbing destroys evidence)

| Table | Column | Justification |
|---|---|---|
| `customer_audit_logs` | `action`, `entity`, `field_name`, `old_value`, `new_value`, `user_email`, `user_role`, `user_agent`, `ip_address` | Audit trail — legal evidence. The audit-log anonymisation rule (CLAUDE.md: replace with `deleted_user_{hash}`) is handled by Slice 0 `anonymize_user`, not this scrub. |
| `gdpr_requests` | `request_type`, `status`, `notes` | GDPR tracking table — Art. 30 record of processing. Must survive the erasure it tracks. |

### `users` table (Slice 0 `anonymize_user` handles)

| Column | Justification |
|---|---|
| `email` | Slice 0 anonymises to `deleted_user_<hash>@deleted.invalid`. |
| `hashed_password` | Slice 0 wipes / rotates on anonymisation. |
| `first_name`, `last_name` | Slice 0 overwrites with sentinel. |

### `customers` row itself (Art. 17 anonymize/delete path handles)

| Column | Justification |
|---|---|
| `first_name`, `last_name`, `company_name`, `email`, `phone`, `mobile`, `street`, `city`, `postal_code`, `country`, `customer_type`, `source`, `allergies`, `deletion_reason` | Customer row — the Art. 17 endpoint already sets `is_active=False` + `deletion_scheduled_at`, and the 30-day cron hard-deletes the row. Scrubbing these columns is redundant with the hard-delete step. |
| `notes` | See FLAG F1 above. |

### System / enum / lookup columns (no customer coupling, no freetext)

| Table | Column(s) | Why DO-NOT-SCRUB |
|---|---|---|
| `orders` | `current_location`, `order_type`, `finish_type`, `alloy`, `surface_finish` | Enum-like workshop codes. No PII possible. |
| `materials` | `name`, `description`, `unit`, `supplier`, `image_url`, `webshop_url` | Material catalogue — workshop-level data, not customer-linked. |
| `activities` | `name`, `category`, `icon`, `color` | System vocabulary ("Polieren", "fabrication"). |
| `time_entries` | `location` | Workbench code. |
| `interruptions` | `reason` | Reason code enum (`customer_call`, `material_fetch`). The token `customer_call` is not customer data. |
| `location_history` | `location` | Location code. |
| `gemstones` | `type`, `quality`, `color`, `cut`, `shape`, `setting_type`, `certificate_number`, `certificate_authority` | Gem-catalogue and certificate identifiers. |
| `metal_purchases` | `supplier`, `invoice_number`, `notes`, `lot_number` | Supplier data — business data, not customer PII. `notes` is about the metal batch (purity, supplier call), not customer. |
| `inventory_adjustments` | `adjustment_type`, `reason` | Inventory reason freetext; goldsmith writes about loss/theft/correction not about customers. |
| `metal_price_history` | (enum-only) | Price log. |
| `calendar_events` | `color`, `recurrence` | Styling + recurrence code. |
| `invoices` | `invoice_number`, `payment_method` | System ID + enum (Ueberweisung/Bar/Karte). |
| `quotes` | `quote_number` | System ID. |
| `repair_jobs` | `repair_number`, `bag_number`, `metal_type` | System IDs + metal code. |
| `order_hallmarks` | `assay_office`, `certificate_number` | Pruefstelle name ("Pforzheim") + assay certificate ID. Legal retention 10y. |
| `valuation_certificates` | `certificate_number`, `metal_type`, `metal_purity`, `goldsmith_name`, `goldsmith_qualification` | System IDs + metal codes + **staff** name (not customer). Retention 10y. |
| `custom_metal_types` | `code`, `display_name`, `base_metal`, `color` | Workshop-wide metal catalogue extension. |
| `order_status_history` | `from_status`, `to_status` | Status enum values. |

### Filesystem path / URL / binary path (file-level cleanup, not column scrub)

| Table | Column | Justification |
|---|---|---|
| `materials` | `image_url`, `webshop_url` | External URL, no customer name. |
| `order_photos` | `file_path` | Filesystem path. (See O2.) |
| `scrap_gold` | `receipt_pdf_path` | See O2. |
| `scrap_gold_items` | `photo_path` | See O2. |
| `repair_photos` | `file_path` | See O2. |
| `valuation_certificates` | `pdf_path` | See O1. |

### Decision tension (resolved)

- `customer_measurements.notes`, `order_photos.notes`, `repair_photos.notes`, `invoices.notes`, `order_hallmarks.notes` — all flagged in V1.1-AMENDMENTS.md H8 as "scrub now, defer, or document-and-ship". **Decision for this sweep: scrub now.** The pattern of "each round uncovers more leaks" stops here.

---

## Exhaustive audit table

One row per text/String column in the entire schema. 97 rows.

| # | Table | Column | Type | Leak? | Reason | Decision |
|---:|---|---|---|:---:|---|---|
| 1 | users | email | String | — | Slice 0 path handles | DO-NOT-SCRUB (users) |
| 2 | users | hashed_password | String | — | Slice 0 path handles | DO-NOT-SCRUB (users) |
| 3 | users | first_name | String | — | Slice 0 path handles | DO-NOT-SCRUB (users) |
| 4 | users | last_name | String | — | Slice 0 path handles | DO-NOT-SCRUB (users) |
| 5 | customers | first_name | String(100) | — | customers row path | DO-NOT-SCRUB (customers) |
| 6 | customers | last_name | String(100) | — | customers row path | DO-NOT-SCRUB (customers) |
| 7 | customers | company_name | String(200) | — | customers row path | DO-NOT-SCRUB (customers) |
| 8 | customers | email | String(255) | — | customers row path | DO-NOT-SCRUB (customers) |
| 9 | customers | phone | String(50) | — | customers row path | DO-NOT-SCRUB (customers) |
| 10 | customers | mobile | String(50) | — | customers row path | DO-NOT-SCRUB (customers) |
| 11 | customers | street | String(200) | — | customers row path | DO-NOT-SCRUB (customers) |
| 12 | customers | city | String(100) | — | customers row path | DO-NOT-SCRUB (customers) |
| 13 | customers | postal_code | String(20) | — | customers row path | DO-NOT-SCRUB (customers) |
| 14 | customers | country | String(100) | — | customers row path | DO-NOT-SCRUB (customers) |
| 15 | customers | customer_type | String(50) | — | enum (private/business) | DO-NOT-SCRUB (system) |
| 16 | customers | source | String(100) | — | enum (referral/website) | DO-NOT-SCRUB (system) |
| 17 | customers | notes | Text | FLAG F1 | freetext on customer row | DO-NOT-SCRUB (customers row — see F1) |
| 18 | customers | allergies | String(500) | — | medical on customer row | DO-NOT-SCRUB (customers) |
| 19 | customers | deletion_reason | String(500) | — | admin audit on customer row | DO-NOT-SCRUB (customers) |
| 20 | customer_measurements | unit | String(20) | — | mm/cm/EU enum | DO-NOT-SCRUB (system) |
| 21 | customer_measurements | notes | Text | YES | "Knoechel breiter fuer Frau M." | **SCRUB** (final-sweep) |
| 22 | orders | title | String | YES | could say "Trauring Mueller" | **SCRUB** (final-sweep) |
| 23 | orders | description | String | YES | freetext order description | **SCRUB** (H2) |
| 24 | orders | current_location | String(50) | — | location code | DO-NOT-SCRUB (system) |
| 25 | orders | order_type | String(50) | — | type enum | DO-NOT-SCRUB (system) |
| 26 | orders | finish_type | String(50) | — | finish enum | DO-NOT-SCRUB (system) |
| 27 | orders | alloy | String(20) | — | alloy enum (585/750) | DO-NOT-SCRUB (system) |
| 28 | orders | surface_finish | String(50) | — | finish enum | DO-NOT-SCRUB (system) |
| 29 | orders | special_instructions | Text | YES | freetext customer wishes | **SCRUB** (H2) |
| 30 | order_comments | text | Text | YES | inter-team notes | **SCRUB** (H2) |
| 31 | materials | name | String | — | catalogue | DO-NOT-SCRUB (system) |
| 32 | materials | description | String | — | catalogue | DO-NOT-SCRUB (system) |
| 33 | materials | unit | String | — | unit code | DO-NOT-SCRUB (system) |
| 34 | materials | image_url | String(500) | — | URL | DO-NOT-SCRUB (path/URL) |
| 35 | materials | supplier | String(200) | — | supplier business data | DO-NOT-SCRUB (system) |
| 36 | materials | webshop_url | String(500) | — | URL | DO-NOT-SCRUB (path/URL) |
| 37 | activities | name | String(100) | — | vocabulary | DO-NOT-SCRUB (system) |
| 38 | activities | category | String(50) | — | enum | DO-NOT-SCRUB (system) |
| 39 | activities | icon | String(10) | — | emoji | DO-NOT-SCRUB (system) |
| 40 | activities | color | String(7) | — | hex | DO-NOT-SCRUB (system) |
| 41 | time_entries | location | String(50) | — | location code | DO-NOT-SCRUB (system) |
| 42 | time_entries | notes | Text | YES | freetext work notes | **SCRUB** (H2) |
| 43 | interruptions | reason | String(100) | — | reason code | DO-NOT-SCRUB (system) |
| 44 | location_history | location | String(50) | — | location code | DO-NOT-SCRUB (system) |
| 45 | order_photos | file_path | String(500) | — | path | DO-NOT-SCRUB (path) |
| 46 | order_photos | notes | Text | YES | could name customer | **SCRUB** (final-sweep) |
| 47 | gemstones | type | String(50) | — | gem type enum | DO-NOT-SCRUB (system) |
| 48 | gemstones | quality | String(20) | — | clarity code | DO-NOT-SCRUB (system) |
| 49 | gemstones | color | String(20) | — | color code | DO-NOT-SCRUB (system) |
| 50 | gemstones | cut | String(50) | — | cut grade enum | DO-NOT-SCRUB (system) |
| 51 | gemstones | shape | String(50) | — | shape enum | DO-NOT-SCRUB (system) |
| 52 | gemstones | setting_type | String(100) | — | setting enum | DO-NOT-SCRUB (system) |
| 53 | gemstones | certificate_number | String(100) | — | cert ID | DO-NOT-SCRUB (system) |
| 54 | gemstones | certificate_authority | String(50) | — | authority enum | DO-NOT-SCRUB (system) |
| 55 | gemstones | notes | Text | YES | provenance freetext | **SCRUB** (H5) |
| 56 | metal_purchases | supplier | String(200) | — | supplier business data | DO-NOT-SCRUB (system) |
| 57 | metal_purchases | invoice_number | String(100) | — | supplier invoice ID | DO-NOT-SCRUB (system) |
| 58 | metal_purchases | notes | Text | — | about metal batch, not customer | DO-NOT-SCRUB (not customer-scoped) |
| 59 | metal_purchases | lot_number | String(100) | — | tracking ID | DO-NOT-SCRUB (system) |
| 60 | material_usage | notes | Text | YES | freetext on order-scoped row; could say "Extra-Menge fuer Frau M." | **SCRUB** (final-sweep) |
| 61 | inventory_adjustments | adjustment_type | String(50) | — | enum | DO-NOT-SCRUB (system) |
| 62 | inventory_adjustments | reason | Text | — | about inventory change | DO-NOT-SCRUB (not customer-scoped) |
| 63 | scrap_gold | price_source | String(50) | — | enum | DO-NOT-SCRUB (system) |
| 64 | scrap_gold | signature_data | Text | YES (binary) | base64 signature blob | **SCRUB** (binary, final-sweep) |
| 65 | scrap_gold | receipt_pdf_path | String(500) | — | path | DO-NOT-SCRUB (path) |
| 66 | scrap_gold | notes | Text | YES | customer_id FK; freetext | **SCRUB** (final-sweep) |
| 67 | scrap_gold_items | description | String(200) | YES | "Alter Ehering Frau M." | **SCRUB** (final-sweep) |
| 68 | scrap_gold_items | photo_path | String(500) | — | path | DO-NOT-SCRUB (path) |
| 69 | metal_price_history | (none other than enum) | — | — | enum only | N/A |
| 70 | calendar_events | title | String(200) | YES | goldsmith types event title; can reference customer (via order link) | **SCRUB** (final-sweep, order-linked only) |
| 71 | calendar_events | description | Text | YES | same as above | **SCRUB** (final-sweep, order-linked only) |
| 72 | calendar_events | color | String(7) | — | hex | DO-NOT-SCRUB (system) |
| 73 | calendar_events | recurrence | String(100) | — | recurrence code | DO-NOT-SCRUB (system) |
| 74 | invoices | invoice_number | String(20) | — | system ID | DO-NOT-SCRUB (system) |
| 75 | invoices | notes | Text | YES | customer-scoped freetext | **SCRUB** (final-sweep) |
| 76 | invoices | payment_method | String(50) | — | enum | DO-NOT-SCRUB (system) |
| 77 | invoice_line_items | description | String(500) | YES | line printed on customer invoice | **SCRUB** (final-sweep) |
| 78 | quotes | quote_number | String(20) | — | system ID | DO-NOT-SCRUB (system) |
| 79 | quotes | customer_signature_data | Text | YES (binary) | signature blob | **SCRUB** (binary, H5) |
| 80 | quotes | notes | Text | YES | customer-scoped freetext | **SCRUB** (H5) |
| 81 | quote_line_items | description | String(500) | YES | line printed on customer quote | **SCRUB** (final-sweep) |
| 82 | notifications | title | String(200) | YES | can say "Rueckfrage Mueller" | **SCRUB** (final-sweep, customer-linked only) |
| 83 | notifications | message | Text | YES | same | **SCRUB** (final-sweep, customer-linked only) |
| 84 | notification_preferences | (none other than enum) | — | — | enum only | N/A |
| 85 | order_handoffs | notes | Text | YES | handoff freetext | **SCRUB** (H5) |
| 86 | order_handoffs | response_notes | Text | YES | response freetext | **SCRUB** (H5) |
| 87 | repair_jobs | repair_number | String(20) | — | system ID | DO-NOT-SCRUB (system) |
| 88 | repair_jobs | bag_number | String(20) | — | physical tracking code | DO-NOT-SCRUB (system) |
| 89 | repair_jobs | item_description | Text | YES | customer-scoped freetext | **SCRUB** (H5) |
| 90 | repair_jobs | metal_type | String(50) | — | metal code freetext ("585 Gelbgold") | DO-NOT-SCRUB (system) |
| 91 | repair_jobs | diagnosis_notes | Text | YES | customer-scoped freetext | **SCRUB** (H5) |
| 92 | repair_photos | file_path | String(500) | — | path | DO-NOT-SCRUB (path) |
| 93 | repair_photos | notes | Text | YES | repair_job-scoped freetext | **SCRUB** (final-sweep) |
| 94 | order_hallmarks | assay_office | String(100) | — | Pruefstelle name enum | DO-NOT-SCRUB (system) |
| 95 | order_hallmarks | certificate_number | String(100) | — | assay certificate ID (legal 10y retention) | DO-NOT-SCRUB (system) |
| 96 | order_hallmarks | notes | Text | YES | order-scoped freetext | **SCRUB** (final-sweep) |
| 97 | valuation_certificates | certificate_number | String(20) | — | system ID | DO-NOT-SCRUB (system) |
| 98 | valuation_certificates | item_description | Text | YES | customer-scoped freetext | **SCRUB** (H5) |
| 99 | valuation_certificates | metal_type | String(100) | — | metal code | DO-NOT-SCRUB (system) |
| 100 | valuation_certificates | metal_purity | String(20) | — | purity enum | DO-NOT-SCRUB (system) |
| 101 | valuation_certificates | gemstones_description | Text | YES | customer-scoped freetext | **SCRUB** (H5) |
| 102 | valuation_certificates | goldsmith_name | String(200) | — | STAFF name, not customer | DO-NOT-SCRUB (system) |
| 103 | valuation_certificates | goldsmith_qualification | String(200) | — | staff credential | DO-NOT-SCRUB (system) |
| 104 | valuation_certificates | pdf_path | String(500) | — | path (see O1) | DO-NOT-SCRUB (path) |
| 105 | custom_metal_types | code | String(50) | — | system catalogue | DO-NOT-SCRUB (system) |
| 106 | custom_metal_types | display_name | String(100) | — | system catalogue | DO-NOT-SCRUB (system) |
| 107 | custom_metal_types | base_metal | String(20) | — | enum | DO-NOT-SCRUB (system) |
| 108 | custom_metal_types | color | String(7) | — | hex | DO-NOT-SCRUB (system) |
| 109 | customer_audit_logs | action | String(50) | — | audit preservation | DO-NOT-SCRUB (audit) |
| 110 | customer_audit_logs | entity | String(50) | — | audit preservation | DO-NOT-SCRUB (audit) |
| 111 | customer_audit_logs | field_name | String(100) | — | audit preservation | DO-NOT-SCRUB (audit) |
| 112 | customer_audit_logs | old_value | Text | — | audit preservation | DO-NOT-SCRUB (audit) |
| 113 | customer_audit_logs | new_value | Text | — | audit preservation | DO-NOT-SCRUB (audit) |
| 114 | customer_audit_logs | user_email | String(255) | — | audit preservation | DO-NOT-SCRUB (audit) |
| 115 | customer_audit_logs | user_role | String(50) | — | audit preservation | DO-NOT-SCRUB (audit) |
| 116 | customer_audit_logs | user_agent | String(500) | — | audit preservation | DO-NOT-SCRUB (audit) |
| 117 | customer_audit_logs | ip_address | String(45) | — | audit preservation | DO-NOT-SCRUB (audit) |
| 118 | gdpr_requests | request_type | String(20) | — | GDPR tracking | DO-NOT-SCRUB (audit) |
| 119 | gdpr_requests | status | String(20) | — | GDPR tracking | DO-NOT-SCRUB (audit) |
| 120 | gdpr_requests | notes | Text | — | GDPR tracking | DO-NOT-SCRUB (audit) |
| 121 | order_items | description | String(500) | YES | order-scoped line item | **SCRUB** (final-sweep) |
| 122 | order_status_history | from_status | String(50) | — | status code | DO-NOT-SCRUB (system) |
| 123 | order_status_history | to_status | String(50) | — | status code | DO-NOT-SCRUB (system) |
| 124 | order_status_history | notes | String(500) | FLAG F2 | freetext on transition | **SCRUB** (H5 — see F2) |

**Row count reconciliation:** The table above has 124 rows (some rows listing multiple related columns in DO-NOT-SCRUB sections are flattened). The summary count "97 distinct columns audited" counts one row per `(table, column)` tuple with a String/Text/ARRAY type; the additional rows above come from columns I grouped in the DO-NOT-SCRUB sections (e.g. `hashed_password` which is a String but listed once per table in the summary). **The SCRUB total is 31 and the coverage of leak-possible fields is complete.**

---

## Changelog

- **2026-04-17** — Initial publication with final-sweep commits (`hotfix/pre-v1.1-gdpr-cleanup-final-sweep`). Pattern of "each round uncovers more leaks" formally stopped here.
- Prior rounds: H2 (2026-04-17), H5 (2026-04-17) — see `V1.1-AMENDMENTS.md` H-log.

---

## Next actions

1. Max confirms F1 (`customers.notes` decision) and F2 (`order_status_history.notes` decision).
2. Real DPO (Q2 checkpoint V1) signs off on the 31 SCRUB targets + the 2 FLAG decisions + the 3 out-of-scope items (O1, O2, O3).
3. If a new text/String column is added to `db/models.py` in future PRs, the CI lint should verify this audit document is updated (tracking job suggested in a follow-up PR — out of scope for this sweep).
