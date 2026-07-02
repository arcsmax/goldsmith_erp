# SPEC V1.2 — Customer Updates & Cost Approval (Kundeninfo & Kostenfreigabe)

Status: **Draft — pending review**
Date: 2026-07-02
Depends on: V1.1 helpful but not required; existing Quote, Order, OrderPhoto,
TimeEntry, MaterialUsage, customer_portal token pattern

## Goal

Customers get professional progress emails with selected photos, and when the
projected cost is going to substantially exceed the Kostenvoranschlag, the
goldsmith is alerted, the customer is formally notified, and the response is
captured as evidence — implementing the §649 BGB Anzeigepflicht as a product
feature (research doc §3).

Decision context: **no live portal** (Max, 2026-07-02). Everything is
email/PDF. But every outbound update carries a token, so a hosted portal can
later render the identical content without data-model changes.

## Scope

In: SMTP email sending, progress updates with opt-in photo sharing, projected
cost watcher, cost change requests with logged approval, update history per
order.
Out (backlog): live portal pages, SMS/WhatsApp, e-signature capture, online
click-to-approve (requires hosting), automated pickup reminders.

## Domain model

### `EmailSettings` (config, not table)

SMTP host/port/user/password/sender via env (`SMTP_HOST`, `SMTP_PORT`,
`SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`) — validated at
startup like other required settings; feature degrades to **PDF-only mode**
with a visible banner if unset (fail loudly, never silently).

### `CustomerUpdate` (new table)

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| order_id / repair_job_id | FK, exactly one set | |
| kind | enum | progress, cost_change, ready_for_pickup, custom |
| subject / body | Text | rendered from German templates, editable before send |
| photo_ids | JSONB list | **only explicitly selected photos** — design-IP rule: nothing shared by default |
| cost_change_request_id | FK, nullable | when kind=cost_change |
| token | unique, indexed | portal-ready handle (unused in V1.2 emails except as reference id) |
| status | enum | draft → sent → send_failed |
| sent_at / sent_by | | |
| delivery_method | enum | email, pdf_manual (goldsmith sent it herself via WhatsApp etc.) |

### `CostChangeRequest` (new table)

Change-order style (research doc §3: construction pattern beats auto-repair):

| Field | Type | Notes |
|---|---|---|
| id | UUID PK | |
| order_id | FK, required | |
| quote_id | FK, nullable | the Kostenvoranschlag being exceeded |
| original_amount / new_amount | Numeric | prior state stays visible |
| delta_percent | computed, stored | |
| reason | Text, required | why — the legally relevant justification |
| line_items | JSONB | itemized what changed (per-line approve/decline is backlog; V1.2 approves the request as a whole) |
| status | enum | draft → sent → approved → declined → superseded |
| response_method | enum, nullable | email_reply, in_person, phone |
| response_evidence | Text | pasted email reply text / "signed printout in folder" / call summary |
| responded_at / recorded_by | | who logged the customer's answer |
| created_at / created_by | | |

Approval is **evidence logging**, not click-tracking: the customer replies to
the email (or approves in person/by phone) and the goldsmith records it. The
record (timestamp, method, evidence text, recorder) is the audit trail.
Financial data → ADMIN/GOLDSMITH only, all access audit-logged.

### Projected cost watcher (service logic, no new table)

`CostWatchService.get_projected_cost(order)` =
material actuals (existing `MaterialUsage` rollup)
+ gemstone actuals
+ tracked billable time × hourly rate (existing TimeEntry + Activity.is_billable)
+ remaining-work estimate (V1.2: simple — goldsmith-entered "% complete" on
the order, or none; V1.3 replaces this with the learning estimator).

Threshold check runs on the events that change cost (material consumption,
time entry stop) — not a cron: when projected > quote total × (1 + threshold),
create a Notification (existing system) once per order per threshold crossing.
Threshold configurable, **default 15%** (Verbraucherzentrale/HWK guidance
band; courts also weigh absolute amounts, so also alert at a configurable
absolute delta, default €150).

## Email sending

- `EmailService` (new, `services/email_service.py`): async SMTP (aiosmtplib),
  German Jinja2 templates (progress, cost change, ready for pickup), inline
  thumbnail images + full-size attachments (configurable, default: attach
  compressed ≤1600px versions), plain-text alternative part.
- Photos in emails are re-encoded copies, EXIF-stripped.
- Send failures: status=send_failed, structured log with context, Notification
  to the sender — never silent.
- Every email footer: order reference + shop contact + privacy notice line.
- PDF fallback: identical content rendered via existing PDF infra
  (`delivery_method=pdf_manual`), for customers without email or when SMTP
  is unset.

## API

New router `api/routers/customer_updates.py` (permissions:
`CUSTOMER_UPDATE_VIEW/SEND` → ADMIN+GOLDSMITH):

- `POST /orders/{id}/updates` (draft from template, kind, photo selection)
- `GET /orders/{id}/updates` (history timeline)
- `POST /updates/{id}/send` / `POST /updates/{id}/download-pdf`
- `POST /orders/{id}/cost-changes` / `GET /orders/{id}/cost-changes`
- `POST /cost-changes/{id}/send` (creates+sends the linked CustomerUpdate)
- `POST /cost-changes/{id}/record-response` body `{status, response_method,
  response_evidence}`
- `GET /orders/{id}/projected-cost` (breakdown for the alert UI)

## Frontend

- **Order detail → "Kundeninfo" tab**: update timeline (sent items, cost
  changes with status badges), "Update senden" flow: pick kind → pick photos
  (explicit multi-select with preview, nothing preselected) → edit templated
  German text → preview → send. Shows send status.
- **Cost alert banner** on order detail + dashboard when watcher fires:
  "Voraussichtliche Kosten überschreiten den Kostenvoranschlag um 18% —
  Kundin informieren (§649 BGB)". Alert links directly to creating the
  CostChangeRequest (every display links to its natural next action —
  CLAUDE.md principle).
- **Cost change form**: original vs new side by side, reason (required),
  itemized changes; after sending, a "Antwort erfassen" action logs the
  response.
- Settings page: SMTP config status, threshold percent/absolute, template
  editing (phase 2).

## GDPR & privacy

- Emails contain PII by nature — sending via the shop's own mailbox keeps it
  first-party. Log update sends with customer *ID*, never plaintext PII, in
  application logs.
- Customer erasure: CustomerUpdates and CostChangeRequests scrubbed
  (body/evidence nulled), skeleton rows kept for Art. 30 / financial audit
  (same pattern as invoice retention).
- `photo_ids` sharing is explicit per update = consent-by-action for design
  photos; no photo is ever auto-shared.

## Testing

- Unit: watcher math (materials+time+threshold crossings, absolute + percent),
  change-request state machine (incl. superseded chains), template rendering.
- Integration: draft→send flow with mocked SMTP (aiosmtplib mock), send
  failure path sets status + notification, record-response permissions,
  GDPR scrub.
- E2E: cost alert appears after time entry pushes projection over threshold;
  full send flow with photo selection.

## Open questions

1. Exact German wording of the §649 notice template — get a
   Handwerkskammer-reviewed template (HWK Rhein-Main PDF as starting point).
2. Should "ready for pickup" auto-suggest when status → completed? (Proposed:
   yes, suggestion only, never auto-send.)
3. Hourly rate source for projections: Activity-level rate vs single shop
   rate? (Proposed: single configurable shop rate in V1.2; per-activity rates
   with V1.3.)
