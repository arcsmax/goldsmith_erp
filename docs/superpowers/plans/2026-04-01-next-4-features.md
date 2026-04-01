# Next 4 Features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 4 features every competitor has that we're missing: repair tracking, quotes, customer email notifications, and QR label printing.

**Architecture:** 4 independent tracks. Track 1 (Repairs) and Track 2 (Quotes) can run in parallel. Track 3 (Email) can run in parallel with both. Track 4 (Labels) depends on Track 1 being done (needs repair model).

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy async / fpdf2 / aiosmtplib / segno (QR) / React 18.3 / TypeScript

**Design Spec:** `docs/superpowers/specs/2026-04-01-next-4-features-design.md`

---

## Track 1: Repair Tracking (6 tasks)

### Task 1.1: RepairJob model + migration

**Files:**
- Modify: `src/goldsmith_erp/db/models.py` — add RepairJobStatus enum, RepairJob model, RepairPhoto model
- Create: `src/goldsmith_erp/models/repair.py` — Pydantic schemas
- Create: `alembic/versions/20260401_add_repair_jobs_table.py`

- [ ] Add `RepairJobStatus` enum: RECEIVED, DIAGNOSED, QUOTED, APPROVED, IN_REPAIR, QUALITY_CHECK, READY, PICKED_UP, CANCELLED
- [ ] Add `RepairItemType` enum: RING, CHAIN, BRACELET, EARRING, WATCH, BROOCH, OTHER
- [ ] Add `RepairJob` model with all fields from spec
- [ ] Add `RepairPhoto` model with `phase` enum (INTAKE, DURING_REPAIR, COMPLETED)
- [ ] Create Pydantic schemas: RepairJobCreate, RepairJobUpdate, RepairJobRead, RepairPhotoRead
- [ ] Create Alembic migration
- [ ] Commit

### Task 1.2: RepairService

**Files:**
- Create: `src/goldsmith_erp/services/repair_service.py`

- [ ] create_repair(db, data, user_id) — generate repair_number, bag_number, create record
- [ ] get_repair / list_repairs with filters (status, customer_id, date range)
- [ ] update_repair — status transitions with validation (can't skip stages)
- [ ] diagnose(db, repair_id, diagnosis_notes, estimated_cost, user_id)
- [ ] complete_repair(db, repair_id) — set status READY, set completion date
- [ ] pickup(db, repair_id) — set PICKED_UP, set picked_up_at
- [ ] Commit

### Task 1.3: Repair router + permissions

**Files:**
- Create: `src/goldsmith_erp/api/routers/repairs.py`
- Modify: `src/goldsmith_erp/core/permissions.py` — add REPAIR_* permissions
- Modify: `src/goldsmith_erp/main.py` — register router

- [ ] Add REPAIR_VIEW, REPAIR_CREATE, REPAIR_EDIT permissions
- [ ] Create all endpoints from spec (POST, GET, PATCH, diagnose, complete, pickup, photos)
- [ ] Register router at /api/v1/repairs
- [ ] Commit

### Task 1.4: RepairsPage frontend

**Files:**
- Create: `frontend/src/pages/RepairsPage.tsx`
- Create: `frontend/src/api/repairs.ts`
- Create: `frontend/src/styles/repairs.css`
- Modify: `frontend/src/App.tsx` — add route
- Modify: `frontend/src/layouts/MainLayout.tsx` — add nav link
- Modify: `frontend/src/types.ts` — add repair types

- [ ] Create repairs API client with all methods
- [ ] Add RepairJob types to types.ts
- [ ] Create RepairsPage with table view: repair number, customer, item, status badge, deadline, bag number, actions
- [ ] Filter by status, search by customer/description
- [ ] "Neue Reparatur" button → creation form
- [ ] Add route /repairs and sidebar link "Reparaturen" with 🔧 icon
- [ ] Commit

### Task 1.5: RepairDetailPage frontend

**Files:**
- Create: `frontend/src/pages/RepairDetailPage.tsx`
- Modify: `frontend/src/App.tsx` — add route

- [ ] Create detail page with tabs: Details, Fotos, Diagnose, Kostenvoranschlag, Historie
- [ ] Status action buttons at top (Diagnose stellen → Angebot erstellen → etc.)
- [ ] Photo upload per phase (Eingang, Während Reparatur, Fertig)
- [ ] Diagnosis form with notes and estimated cost
- [ ] Add route /repairs/:id
- [ ] Commit

### Task 1.6: Repair notifications

**Files:**
- Modify: `src/goldsmith_erp/services/notification_service.py`
- Modify: `src/goldsmith_erp/db/models.py` — add REPAIR_RECEIVED, REPAIR_READY to NotificationTypeEnum

- [ ] Add notification on repair status changes (received → ready → picked up)
- [ ] Wire into repair_service status transitions
- [ ] Commit

---

## Track 2: Quotes/Kostenvoranschlag (4 tasks)

### Task 2.1: Quote model + migration

**Files:**
- Modify: `src/goldsmith_erp/db/models.py` — add QuoteStatus enum, Quote model, QuoteLineItem model
- Create: `src/goldsmith_erp/models/quote.py` — Pydantic schemas
- Create: `alembic/versions/20260401_add_quotes_table.py`

- [ ] Add QuoteStatus enum: DRAFT, SENT, APPROVED, REJECTED, EXPIRED, CONVERTED
- [ ] Add Quote model with all fields from spec (order_id, repair_job_id, customer_signature_data, valid_until)
- [ ] Add QuoteLineItem model
- [ ] Create Pydantic schemas
- [ ] Create migration
- [ ] Commit

### Task 2.2: QuoteService + PDF template

**Files:**
- Create: `src/goldsmith_erp/services/quote_service.py`
- Create: `src/goldsmith_erp/templates/quote.html`
- Modify: `src/goldsmith_erp/services/pdf_service.py` — add render_quote_pdf()

- [ ] create_quote_from_order(db, order_id) — auto-build line items from cost calculation
- [ ] create_quote_from_repair(db, repair_id) — build from diagnosis
- [ ] send_quote(db, quote_id) — mark SENT
- [ ] approve_quote(db, quote_id, signature_data) — mark APPROVED, store signature
- [ ] reject_quote / expire_quote
- [ ] convert_quote(db, quote_id) — create confirmed order or mark repair APPROVED
- [ ] Add Kostenvoranschlag PDF template
- [ ] Add render_quote_pdf() to PDFService
- [ ] Commit

### Task 2.3: Quote router

**Files:**
- Create: `src/goldsmith_erp/api/routers/quotes.py`
- Modify: `src/goldsmith_erp/main.py` — register router

- [ ] All endpoints from spec (create, list, get, update, send, approve, reject, convert, pdf)
- [ ] QUOTE_VIEW, QUOTE_CREATE, QUOTE_EDIT permissions
- [ ] Register router
- [ ] Commit

### Task 2.4: QuotesPage + frontend

**Files:**
- Create: `frontend/src/pages/QuotesPage.tsx`
- Create: `frontend/src/api/quotes.ts`
- Create: `frontend/src/styles/quotes.css`
- Modify: `frontend/src/App.tsx`, `frontend/src/layouts/MainLayout.tsx`, `frontend/src/types.ts`

- [ ] Create quotes API client
- [ ] Add quote types
- [ ] Create QuotesPage with list, status filters, create modal
- [ ] "Kostenvoranschlag erstellen" button on OrderDetailPage and RepairDetailPage
- [ ] Quote approval with SignatureCanvas (reuse existing component)
- [ ] PDF download button
- [ ] Add route /quotes and sidebar link "Angebote" with 📝 icon
- [ ] Commit

---

## Track 3: Customer Email Notifications (3 tasks)

### Task 3.1: Email service infrastructure

**Files:**
- Create: `src/goldsmith_erp/services/email_service.py`
- Modify: `src/goldsmith_erp/core/config.py` — add SMTP settings
- Modify: `pyproject.toml` — add aiosmtplib dependency

- [ ] Add SMTP config fields to Settings
- [ ] Install aiosmtplib: `poetry add aiosmtplib`
- [ ] Create EmailService with send_email(to, subject, html_body, attachments)
- [ ] Graceful degradation: skip if SMTP not configured
- [ ] Commit

### Task 3.2: Email templates + triggers

**Files:**
- Create: `src/goldsmith_erp/templates/email/` directory with templates
- Modify: `src/goldsmith_erp/services/notification_service.py` — add email sending
- Modify: `src/goldsmith_erp/services/order_service.py` — trigger on status change
- Modify: `src/goldsmith_erp/services/repair_service.py` — trigger on status change

- [ ] Create 6 Jinja2 HTML email templates (German, goldsmith branding):
  - order_confirmed.html, repair_received.html, quote_sent.html
  - ready_for_pickup.html, pickup_complete.html, fitting_reminder.html
- [ ] Add email trigger in NotificationService: when creating a notification, also send email if customer has email and SMTP is configured
- [ ] Attach PDF when relevant (quote, invoice)
- [ ] Commit

### Task 3.3: Email settings in admin dashboard

**Files:**
- Modify: `frontend/src/pages/AdminSystemPage.tsx` — add email config section
- Modify: `src/goldsmith_erp/api/routers/admin.py` or create new settings router

- [ ] SMTP configuration form (host, port, user, password, from address)
- [ ] "Test-E-Mail senden" button
- [ ] Per-notification-type toggle (enable/disable email for each type)
- [ ] Commit

---

## Track 4: QR Label Printing (2 tasks)

### Task 4.1: QR code generation + label endpoint

**Files:**
- Modify: `pyproject.toml` — add segno (QR library)
- Create: `src/goldsmith_erp/services/label_service.py`
- Modify: `src/goldsmith_erp/api/routers/orders.py` — add /label endpoint
- Create or modify: repair router — add /label endpoint

- [ ] Install segno: `poetry add segno`
- [ ] Create LabelService.generate_label_html(entity_type, entity_data) → HTML string
- [ ] QR code as inline SVG (segno can output SVG directly)
- [ ] Label HTML with @media print CSS for 89x36mm label size
- [ ] Add GET /orders/{id}/label and GET /repairs/{id}/label endpoints
- [ ] Commit

### Task 4.2: "Etikett drucken" button in frontend

**Files:**
- Modify: `frontend/src/pages/OrderDetailPage.tsx` — add print button
- Modify: `frontend/src/pages/RepairDetailPage.tsx` — add print button (if created)

- [ ] Add "Etikett drucken" button in order/repair detail header
- [ ] On click: fetch label HTML from API, open in new window, trigger print dialog
- [ ] Commit

---

## Verification

### Task V1: Full verification

- [ ] Run full test suite
- [ ] Verify frontend builds
- [ ] Verify all new routes are registered
- [ ] Playwright test: create repair → diagnose → quote → approve → complete → pickup
- [ ] Tag release: v1.2.0
