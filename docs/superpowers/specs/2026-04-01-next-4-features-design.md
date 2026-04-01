# Next 4 Features Design Spec: Repair Tracking, Quotes, Customer Notifications, QR Labels

**Date:** 2026-04-01
**Based on:** Industry Gap Analysis (same date) + Ideensammlung requirements
**Goal:** Close the 4 biggest gaps between our ERP and every competitor on the market.

---

## Feature 1: Repair/Service Tracking Workflow

### The Problem
Repairs are 30-50% of a goldsmith workshop's revenue. Currently, all work goes through the Order entity, which is designed for custom commissions. Repairs have a fundamentally different lifecycle: intake → diagnosis → quote → approval → work → done → pickup.

### Data Model

**RepairJob** (new table):
- id, repair_number (auto: "REP-YYYY-NNNN")
- customer_id (FK), received_by_user_id (FK)
- bag_number (String, printed on physical bag)
- item_description (Text) — "Goldring 750, Stein lose"
- item_type (enum: RING, CHAIN, BRACELET, EARRING, WATCH, BROOCH, OTHER)
- metal_type (String, optional)
- estimated_value (Float, optional — for insurance)
- status (enum: RECEIVED → DIAGNOSED → QUOTED → APPROVED → IN_REPAIR → QUALITY_CHECK → READY → PICKED_UP → CANCELLED)
- diagnosis_notes (Text) — goldsmith's findings
- estimated_cost (Float)
- actual_cost (Float)
- estimated_completion_date (DateTime)
- actual_completion_date (DateTime)
- customer_notified_at (DateTime, null until notification sent)
- picked_up_at (DateTime)
- created_at, updated_at

**RepairPhoto** (reuse pattern from OrderPhoto):
- repair_job_id (FK), phase (enum: INTAKE, DURING_REPAIR, COMPLETED)
- file_path, timestamp, taken_by

### API Endpoints

```
POST   /api/v1/repairs                    — create repair job (intake)
GET    /api/v1/repairs                    — list with filters (status, customer, date range)
GET    /api/v1/repairs/{id}               — single repair detail
PATCH  /api/v1/repairs/{id}               — update status, notes, cost
POST   /api/v1/repairs/{id}/diagnose      — add diagnosis + estimated cost
POST   /api/v1/repairs/{id}/quote         — generate quote PDF and mark QUOTED
POST   /api/v1/repairs/{id}/approve       — customer approves (triggers work start)
POST   /api/v1/repairs/{id}/complete      — mark ready for pickup, trigger notification
POST   /api/v1/repairs/{id}/pickup        — mark picked up, record payment
POST   /api/v1/repairs/{id}/photos        — upload photo with phase tag
GET    /api/v1/repairs/{id}/photos        — list photos grouped by phase
```

### Frontend Pages

**RepairsPage** (`/repairs`):
- Kanban-style board with columns: Eingang, Diagnose, Angebot, In Arbeit, Fertig, Abgeholt
- Each card: repair number, customer name, item description, deadline, bag number
- Drag-and-drop between columns changes status
- Alternative: table view with status filter (like OrdersPage)

**RepairDetailPage** (`/repairs/:id`):
- Header: repair number, status badge, bag number
- Tabs: Details, Fotos (before/during/after), Diagnose, Kostenvoranschlag, Historie
- Status action buttons at the top

**Navigation:** Add "Reparaturen" to sidebar between Aufträge and Materialien.

---

## Feature 2: Quote/Kostenvoranschlag Pipeline

### The Problem
The goldsmith calculates a price (Vorkalkulation) but has no formal document to present to the customer. The customer can't approve online. There's no audit trail of what was quoted vs what was charged.

### Data Model

**Quote** (new table):
- id, quote_number (auto: "KV-YYYY-NNNN" — Kostenvoranschlag)
- order_id (FK, optional — quote may exist before order), repair_job_id (FK, optional)
- customer_id (FK)
- status (enum: DRAFT → SENT → APPROVED → REJECTED → EXPIRED → CONVERTED)
- valid_until (DateTime — default 14 days)
- subtotal, tax_rate, tax_amount, total
- customer_signature_data (Text, base64 — reuse SignatureCanvas)
- approved_at, rejected_at, converted_at
- notes (Text)
- created_by (FK to users)
- created_at, updated_at

**QuoteLineItem** (same pattern as InvoiceLineItem):
- quote_id (FK), description, quantity, unit_price, total
- line_type (MATERIAL, LABOR, GEMSTONE, OTHER)

### Workflow

1. Goldsmith fills in order/repair details
2. Clicks "Kostenvoranschlag erstellen" → system generates quote from cost calculation
3. Quote PDF generated and sent to customer via email
4. Customer approves (signature on tablet or via email link)
5. Approved quote auto-creates a confirmed order OR marks repair as APPROVED
6. After completion, invoice references the quote (shows Soll/Ist deviation)

### API Endpoints

```
POST   /api/v1/quotes                    — create from order/repair
GET    /api/v1/quotes                    — list with filters
GET    /api/v1/quotes/{id}               — single quote detail
PATCH  /api/v1/quotes/{id}               — update draft
POST   /api/v1/quotes/{id}/send          — mark sent, trigger email
POST   /api/v1/quotes/{id}/approve       — customer approval with signature
POST   /api/v1/quotes/{id}/reject        — customer rejection
POST   /api/v1/quotes/{id}/convert       — convert to order/invoice
GET    /api/v1/quotes/{id}/pdf           — download quote PDF
```

### PDF Template (Kostenvoranschlag)

Header: "KOSTENVORANSCHLAG" + KV-YYYY-NNNN
Workshop address + Customer address
Line items table: Pos., Beschreibung, Menge, Einzelpreis, Gesamtpreis
Subtotal, MwSt, Total
"Gültig bis: DD.MM.YYYY"
Signature line for customer approval
Footer: "Dieser Kostenvoranschlag ist unverbindlich. Der endgültige Preis kann je nach tatsächlichem Materialverbrauch abweichen."

---

## Feature 3: Customer Email Notifications

### The Problem
Customers have no visibility into their order/repair status. The goldsmith must call or text manually. Every competitor sends automatic SMS/email.

### Approach

Start with **email only** (no SMS — SMS requires a provider account and per-message costs). Email via SMTP is free with any email account.

### Configuration

Add to Settings:
```python
SMTP_HOST: Optional[str] = None
SMTP_PORT: int = 587
SMTP_USER: Optional[str] = None
SMTP_PASSWORD: Optional[str] = None
SMTP_FROM: Optional[str] = None
EMAIL_NOTIFICATIONS_ENABLED: bool = False
```

When `EMAIL_NOTIFICATIONS_ENABLED` is False, skip email sending (graceful degradation).

### Email Service

**`EmailService`:**
- `send_email(to, subject, html_body, attachments=[])`
- Uses `aiosmtplib` for async email sending
- Jinja2 HTML templates with workshop branding
- Attach PDF when relevant (quote, invoice, receipt)

### Trigger Points

| Event | Email to Customer | Subject |
|-------|------------------|---------|
| Order confirmed | Yes | "Ihr Auftrag #{id} wurde bestätigt" |
| Repair received | Yes | "Ihre Reparatur #{id} wurde angenommen" |
| Quote sent | Yes (with PDF) | "Kostenvoranschlag für Ihren Auftrag" |
| Repair/Order ready | Yes | "Ihr Schmuckstück ist fertig — Abholung möglich" |
| Repair picked up | Yes (with invoice PDF) | "Vielen Dank — Rechnung anbei" |
| Fitting appointment | Yes | "Erinnerung: Anprobe am DD.MM.YYYY" |

### Email Templates

German HTML email templates with:
- Workshop logo/name in header
- Goldsmith brand colors (amber/gold)
- Clear action text
- Mobile-responsive layout
- Unsubscribe link (GDPR)

### Admin Settings Page

Add an "E-Mail" section to `/admin/system`:
- SMTP configuration form (host, port, user, password)
- "Test-E-Mail senden" button
- Toggle per notification type (enable/disable)

---

## Feature 4: QR Label Printing

### The Problem
The QR scanner page exists but there are no physical labels to scan. A goldsmith needs to print a label for each piece.

### Approach

Generate a printable label as HTML/CSS that the browser's native print dialog can print. No special label printer software needed — works with any printer.

### Label Content

```
┌──────────────────────────────────────┐
│ ███████  GOLDSCHMIEDE WERKSTATT      │
│ █ QR  █  Auftrag #123               │
│ █     █  Verlobungsring Gold 750     │
│ ███████  Kunde: M. Müller            │
│          Deadline: 15.04.2026        │
│          Status: In Bearbeitung      │
│          Ringmaß: 54mm              │
└──────────────────────────────────────┘
```

The QR code encodes the order/repair ID so the scanner page can read it.

### Implementation

**Backend:**
- `GET /api/v1/orders/{id}/label` — returns HTML label page (print-optimized CSS)
- `GET /api/v1/repairs/{id}/label` — same for repairs
- QR code generated server-side using `qrcode` Python library (or `segno`)

**Frontend:**
- "Etikett drucken" button on OrderDetailPage and RepairDetailPage
- Opens a new window with the label HTML
- Browser's print dialog handles the actual printing
- Label CSS: `@media print` with label-sized dimensions (e.g., 89x36mm for standard labels)

**Optional:** Support for Dymo/Brother label printers via specific CSS page sizes.

---

## Architecture Notes

### Shared Patterns

All 4 features follow the existing codebase patterns:
- SQLAlchemy async models in `db/models.py`
- Pydantic schemas in `models/`
- Service layer in `services/`
- FastAPI routers in `api/routers/`
- React pages/components with TypeScript
- CSS using the semantic token system

### File Conflicts

The 4 features are mostly independent:
- **Repair tracking**: new model, new service, new router, new page — no conflicts
- **Quotes**: new model, new service, new router, new page — touches `pdf_service.py` (add template)
- **Email**: new service, modifies notification_service — touches `config.py`
- **QR labels**: new endpoint on existing routers, new frontend component — touches `order_service.py`

### Dependencies

- Feature 2 (Quotes) can reference Feature 1 (Repairs) via `repair_job_id`
- Feature 3 (Email) is used by Features 1 and 2 for sending notifications
- Feature 4 (Labels) works for both orders and repairs

**Recommended implementation order:** 1 → 2 (in parallel with 3) → 4
