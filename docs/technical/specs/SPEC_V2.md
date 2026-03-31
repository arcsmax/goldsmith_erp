# Goldsmith ERP - V2 Specification

**Version:** 2.0
**Date:** 2026-03-31
**Status:** Draft - Awaiting detailed user input
**Authors:** arcsmax, Claude (AI-assisted analysis)

---

## 1. Vision & Goals

### What is Goldsmith ERP?

A specialized ERP system designed exclusively for modern goldsmith workshops. Unlike generic ERP/CRM tools, it understands the unique workflows of jewelry making: alloy calculations, scrap gold handling, fitting appointments, workbench-level time tracking via QR/NFC, and ML-powered deadline prediction.

### V1.0 Definition of "Done"

A goldsmith can run their daily workshop operations entirely through this system:
- Accept an order with all required specs (alloy, measurements, deadline)
- Track time against orders at the workbench (QR/NFC scan)
- Manage material inventory and procurement
- Handle scrap gold intake with legal documentation
- View a calendar with traffic-light deadlines
- Communicate with office staff via order comments
- Generate invoices from tracked work
- See ML-predicted delivery dates

### Success Metrics

| Metric | Target |
|--------|--------|
| Time tracking adoption | >90% of work hours captured |
| Deadline accuracy | >85% on-time delivery |
| Order completeness | 100% mandatory fields filled |
| Daily active usage | All workshop staff using daily |
| Data entry time | <2 min to create a complete order |

---

## 2. User Personas

### Goldschmied (Goldsmith / Craftsperson)
- **Role:** `goldsmith`
- **Primary activities:** Production work at the bench
- **Needs:** Quick time tracking (scan & go), see today's deadlines, know what's next
- **Pain points:** Interrupted workflow for admin tasks, unclear priorities
- **Dashboard:** Production focus - my orders, today's deadlines, running timer

### Buerokraft (Office Staff / Admin)
- **Role:** `admin`
- **Primary activities:** Order intake, customer communication, invoicing, procurement
- **Needs:** Full overview of all orders, customer management, material ordering
- **Pain points:** Manual quote-to-invoice transfer, forgotten scrap gold, scattered notes
- **Dashboard:** Full KPIs, new orders, low stock alerts, upcoming deadlines

### Betrachter (Viewer / Apprentice)
- **Role:** `viewer`
- **Primary activities:** Learning, observing, basic tasks
- **Needs:** See order status, learn workflows
- **Dashboard:** Simplified read-only stats

### Kunde (Customer) - Future V2.0
- **Role:** Not yet implemented
- **Needs:** Order status tracking, delivery date visibility
- **Implementation:** Customer portal (post-V1.0)

---

## 3. Module Overview

### Currently Implemented (V1.0-alpha)

| Module | Status | Completeness |
|--------|--------|-------------|
| Authentication & RBAC | Done | 95% (missing token refresh) |
| Order Management | Done | 85% (missing mandatory field validation backend) |
| Customer CRM | Done | 90% (measurement library just added) |
| Material Inventory | Done | 85% |
| Metal Inventory (FIFO/LIFO) | Done | 90% |
| Time Tracking | Done | 90% |
| Activities | Done | 95% |
| Cost Calculation | Done | 80% (hardcoded metal price) |
| Calendar (Traffic Light) | Done | 90% (just built) |
| Order Comments (Post-its) | Done | 90% (just built) |
| Role-Specific Dashboards | Done | 85% (just built) |
| Health Checks (K8s) | Done | 100% |
| WebSocket Real-time | Done | 80% |

### To Build (V1.0 Completion)

| Module | Priority | Effort | Description |
|--------|----------|--------|-------------|
| Scrap Gold (Altgold) | MUST | 3-4 weeks | Alloy calculator, photo upload, digital signature, auto invoice credit |
| Invoice Generation | MUST | 2-3 weeks | Quote-to-invoice flow, PDF generation, Soll/Ist comparison |
| Automated Reminders | SHOULD | 2 weeks | Day-before-pickup, fitting follow-up, deadline alerts |
| Fitting (Anprobe) Workflow | SHOULD | 1 week | New order status, fitting appointments, follow-up triggers |
| Handoff Protocol | SHOULD | 1 week | Status-change notifications between team members |
| Supplier/Procurement | COULD | 2 weeks | Supplier links, weekly consolidated ordering lists |
| Mobile/PWA | SHOULD | 2-3 weeks | Offline capability, touch-optimized workbench UI |
| ML Duration Prediction | COULD | 3-4 weeks | XGBoost model, requires 100+ completed orders |

### Future (V2.0+)

| Module | Description |
|--------|-------------|
| Customer Portal | Status tracking for customers |
| Anomaly Detection | Alert on unusual activity durations |
| Batch Processing | Identify similar orders for consolidated work |
| Worker Specialization | ML-learned individual strengths |
| Seasonal Forecasting | Workload prediction by season |
| Multi-Workshop | Support multiple locations |

---

## 4. Feature Specifications

### 4.1 Scrap Gold Module (Altgold-Verrechnung)

**Priority:** MUST-HAVE
**Effort:** 3-4 weeks
**Source:** Anne's Ideensammlung Module 4

#### Overview
When a customer brings old jewelry for credit against a new order, the goldsmith needs to:
1. Document what was received (photos)
2. Calculate fine gold content from alloy and weight
3. Generate a legally binding receipt with digital signature
4. Automatically apply the credit to the final invoice

#### Data Model

```
ScrapGold
  id: int (PK)
  order_id: int (FK -> orders)
  customer_id: int (FK -> customers)
  created_by: int (FK -> users)
  status: enum (received, calculated, signed, credited)
  total_fine_gold_g: float (calculated)
  total_value_eur: float (calculated)
  price_source: enum (daily_rate, fixed_rate)
  gold_price_per_g: float (rate used)
  receipt_pdf_path: string (generated PDF)
  signature_data: text (base64 signature image)
  signed_at: datetime
  notes: text
  created_at: datetime

ScrapGoldItem
  id: int (PK)
  scrap_gold_id: int (FK -> scrap_gold)
  description: string ("Alter Ehering", "Kette")
  alloy: enum (999, 750, 585, 333, etc.)
  weight_g: float (total weight)
  fine_content_g: float (calculated: weight * alloy/1000)
  photo_path: string (uploaded photo)
```

#### Alloy Calculator Logic

| Alloy | Punze | Fine Content |
|-------|-------|-------------|
| 999 | 999 | 99.9% |
| 750 | 18K | 75.0% |
| 585 | 14K | 58.5% |
| 375 | 9K | 37.5% |
| 333 | 8K | 33.3% |

`fine_content_g = weight_g * (alloy / 1000)`

#### API Endpoints

```
POST   /api/v1/orders/{id}/scrap-gold          Create scrap gold entry
GET    /api/v1/orders/{id}/scrap-gold           Get scrap gold for order
POST   /api/v1/scrap-gold/{id}/items            Add item
DELETE /api/v1/scrap-gold/{id}/items/{item_id}  Remove item
POST   /api/v1/scrap-gold/{id}/calculate        Calculate totals
POST   /api/v1/scrap-gold/{id}/sign             Submit digital signature
GET    /api/v1/scrap-gold/{id}/receipt.pdf       Download receipt PDF
```

#### Frontend Components

- `ScrapGoldTab` in OrderDetailPage (new tab)
- `AlloyCalculator` component (alloy selector + weight input + auto-calculate)
- `ScrapGoldItemList` (add/remove items with running total)
- `SignaturePad` (canvas-based signature capture)
- `ScrapGoldReceipt` (preview/download PDF)

#### Integration Points

- Order creation popup: "Altgold vorhanden? Ja/Nein"
- Invoice generation: Auto-deduct scrap gold value as "Gutschrift Altgold"
- Photo upload: Reuse existing OrderPhoto infrastructure

---

### 4.2 Invoice Generation (Rechnungserstellung)

**Priority:** MUST-HAVE
**Effort:** 2-3 weeks
**Source:** Anne's Ideensammlung Module 2

#### Overview
Close the loop between quote (Vorkalkulation) and invoice (Rechnung):
1. Generate binding offer from estimated materials + labor
2. Track actual values during production (Arbeitszettel)
3. Compare estimate vs. actual (Soll/Ist)
4. Generate invoice with one click

#### Data Model

```
Invoice
  id: int (PK)
  order_id: int (FK -> orders)
  invoice_number: string (unique, auto-generated: "RE-2026-0001")
  status: enum (draft, sent, paid, cancelled)

  # Cost Breakdown
  material_cost: float
  gemstone_cost: float
  labor_cost: float
  scrap_gold_credit: float (from ScrapGold module)
  subtotal: float
  profit_margin_percent: float
  profit_amount: float
  vat_rate: float
  vat_amount: float
  total: float

  # Soll/Ist Comparison
  estimated_total: float (from Vorkalkulation)
  actual_total: float
  deviation_percent: float

  # Document
  pdf_path: string
  sent_at: datetime
  paid_at: datetime
  due_date: datetime

  created_at: datetime

InvoiceLineItem
  id: int (PK)
  invoice_id: int (FK -> invoices)
  description: string
  quantity: float
  unit_price: float
  total: float
  category: enum (material, labor, gemstone, scrap_gold_credit, other)
```

#### Key Logic

```
Soll/Ist Comparison:
  estimated = Vorkalkulation (weight * price/g + labor_hours * rate + gemstones)
  actual = Arbeitszettel (actual_weight * price/g + tracked_hours * rate + gemstones)
  deviation = ((actual - estimated) / estimated) * 100

  If deviation > 10%: Warning to review before generating invoice
```

---

### 4.3 Automated Reminders (Automatisierte Erinnerungen)

**Priority:** SHOULD-HAVE
**Effort:** 2 weeks
**Source:** Anne's Ideensammlung Module 5

#### Reminder Types

| Trigger | Message | Recipients |
|---------|---------|------------|
| 1 day before pickup | "Morgen: Kunde XY, Artikel: Ring - ist der Stein schon gefasst?" | Goldsmith + Office |
| Status -> "Rohfassung fertig" + Anprobe pending | "Anprobe fuer Kunden XY jetzt moeglich - Termin vereinbaren?" | Office |
| Deadline < 2 days + status != completed | "DRINGEND: Auftrag XY Deadline in {n} Tagen!" | Goldsmith |
| Low stock threshold reached | "Material {name} unter Mindestbestand ({current}/{min})" | Office |

#### Implementation

- **Backend:** Background task scheduler (ARQ or Celery Beat)
- **Delivery:** In-app notifications (new `Notification` model) + optional email (SMTP)
- **Frontend:** Notification bell in header with unread count + dropdown list

---

### 4.4 Fitting (Anprobe) Workflow

**Priority:** SHOULD-HAVE
**Effort:** 1 week

#### New Order Statuses

```
Current:  new -> in_progress -> completed -> delivered
Extended: new -> in_progress -> fitting_ready -> fitting_done -> completed -> delivered
```

- `fitting_ready`: Raw setting done, customer can try on
- `fitting_done`: Customer approved, continue to completion

#### Trigger

When goldsmith changes status to `fitting_ready`, system auto-notifies office to schedule fitting appointment.

---

### 4.5 Handoff Protocol (Stabuebergabe)

**Priority:** SHOULD-HAVE
**Effort:** 1 week

When order status changes, automatically notify the next responsible team member:
- "In Bearbeitung" -> "Bereit fuer Fassen": Notify the fasser
- "Fassen fertig" -> "Bereit fuer Polieren": Notify the polisher
- "Polieren fertig" -> "Qualitaetskontrolle": Notify QA person

Uses the existing Redis pub/sub + WebSocket infrastructure.

---

## 5. Data Requirements for ML

### Minimum Viable Dataset
- **100 completed orders** with full time tracking data
- Fields needed per order: type, complexity (1-5), metal type, weight, stone count, setting type, labor hours per activity, total duration

### Feature Engineering (from FEATURE_SPEC_TIME_TRACKING_ML.md)
- Order attributes: 15 features (type, complexity, metal, weight, stones, etc.)
- Historical: average duration by type, user productivity factors
- Temporal: day of week, time of year, workload level

### Models to Build (in order)
1. **Duration Prediction** (XGBoost) - When enough data exists
2. **Delivery Date Calculation** - Multi-factor (duration + workload + materials + holidays)
3. **Anomaly Detection** (Isolation Forest) - Flag unusually long activities
4. **Batch Detection** - Group similar orders for efficiency

---

## 6. Technical Requirements

### Performance
- API response time: p95 < 200ms
- Calendar page load: < 1 second
- Dashboard load: < 2 seconds
- Time tracking start/stop: < 500ms

### Mobile/Offline (V1.0 target)
- PWA with service worker for offline time tracking
- Touch-optimized scanner and timer pages
- Minimum viewport: 375px (iPhone SE)

### Security
- RBAC enforced on all endpoints (30 permissions, 3 roles)
- HttpOnly cookies for session management
- Rate limiting on authentication endpoints
- Input validation on all user input
- GDPR compliance for customer data

### Integrations (Future)
- Metal price API (replace hardcoded 45 EUR/g)
- SMTP email for reminders and notifications
- PDF generation (ReportLab or WeasyPrint) for invoices and receipts
- File storage (S3-compatible) for photos and documents

---

## 7. Compliance & Legal

### GDPR
- Customer data: consent tracking, right to deletion, data export
- Employee time tracking: transparent, employee-visible
- Data retention: configurable per data type
- Audit trail: all changes logged

### Scrap Gold Legal Requirements
- Digital receipt with customer signature
- Documented alloy and weight
- Photo evidence of received items
- Accounting-compliant credit integration

---

## 8. Prioritized Roadmap

### Phase A: V1.0 Completion (6-8 weeks)

**Week 1-2: Scrap Gold Module (Backend)**
- ScrapGold + ScrapGoldItem models and migration
- Alloy calculator service
- CRUD endpoints
- PDF receipt generation

**Week 2-3: Scrap Gold Module (Frontend)**
- ScrapGoldTab in OrderDetailPage
- AlloyCalculator component
- SignaturePad component
- Receipt preview/download

**Week 3-4: Invoice Generation**
- Invoice model and migration
- Line item generation from order data
- Soll/Ist comparison logic
- PDF invoice generation
- Invoice page in frontend

**Week 4-5: Notifications & Reminders**
- Notification model
- Background task scheduler setup
- Reminder rules engine
- Notification bell UI
- Optional email delivery

**Week 5-6: Fitting Workflow + Handoff**
- Extended order status enum
- Status-change notification triggers
- Frontend status flow visualization

**Week 6-8: Polish & Testing**
- Mobile responsiveness
- End-to-end testing
- Performance optimization
- User documentation updates

### Phase B: Intelligence Layer (4-6 weeks post-V1.0)
- ML data pipeline
- Duration prediction model
- Delivery date calculator
- Anomaly detection

### Phase C: Scale (Ongoing)
- Customer portal
- Advanced reporting
- Multi-language support
- Multi-workshop support

---

## 9. Open Questions (For User Input)

> These questions need your input to finalize the spec:

1. **Scrap Gold pricing:** Should we use a daily gold rate API, or does the workshop set a fixed rate per alloy type?
2. **Invoice numbering:** What format? "RE-2026-0001" or custom?
3. **Email notifications:** Required for V1.0, or in-app only is sufficient?
4. **Fitting appointments:** Should the system manage actual calendar slots, or just flag orders as "ready for fitting"?
5. **Multi-user workshops:** How many simultaneous users do you expect? (affects performance targets)
6. **Accounting software:** Do you use DATEV, Lexware, or another accounting system for export?
7. **Photo storage:** Local filesystem or cloud (S3)? Expected volume per month?
8. **Mobile priority:** Which pages are most critical for mobile/tablet use at the workbench?
9. **Customer communication:** Should customers receive automated email updates on order status?
10. **Backup strategy:** Automated daily backups to where? Local disk, cloud?

---

*This spec is a living document. Update as requirements are clarified.*
