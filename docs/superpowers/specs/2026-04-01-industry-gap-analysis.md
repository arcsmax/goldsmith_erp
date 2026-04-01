# Industry Gap Analysis: Goldsmith ERP vs. Market Leaders

**Date:** 2026-04-01
**Research Method:** Web analysis of 13 competing solutions (PrismaNote, PIRO, Luxare, Orderry, Synergics, QuoteMachine, CCJewel, crystalworks, Craftybase, RepairDesk, Gem Logic, WJewel, Gold Matrix)

---

## Executive Summary

Our Goldsmith ERP has strong foundations (FastAPI backend, React frontend, 145 API routes, ML pipeline, GDPR compliance) but is missing 4 features that EVERY competitor offers. These are not nice-to-haves — they are table stakes that a goldsmith will expect on day one.

---

## CRITICAL Missing Features (Every Competitor Has These)

### 1. Repair/Service Tracking Workflow

**What competitors do:** Dedicated repair workflow separate from custom orders:
- Intake: customer drops off piece → photos taken → bag number assigned → label printed
- Diagnosis: goldsmith inspects → enters findings → estimates cost
- Quote: auto-generated quote sent to customer via email/SMS
- Approval: customer approves (digitally or in person)
- Work: repair tracked with status updates → technician assigned
- Completion: quality check → customer notified "ready for pickup"
- Pickup: piece returned → payment recorded

**Why this matters:** Repairs are 30-50% of a typical goldsmith workshop's revenue. Without repair tracking, the goldsmith uses paper bags and Post-its — exactly what the Ideensammlung was trying to eliminate.

**Our status:** No repair entity. Orders cover custom work but not repair intake.

**Industry examples:**
- PrismaNote: "Reparatursystem mit Tütennummer, Fotos, Techniker-Zuordnung"
- Luxare: "Streamlines workflows from intake to invoicing"
- RepairDesk: "Repair tickets with customer notes and pre-repair images"

### 2. Quote/Estimate → Customer Approval → Order Pipeline

**What competitors do:**
- Generate PDF quote (Kostenvoranschlag) from order template
- Send to customer via email
- Customer approves with e-signature (from phone/tablet)
- Approved quote auto-converts to confirmed order
- Quote vs. final invoice comparison for margin analysis

**Why this matters:** The Ideensammlung explicitly mentions "verbindliches Angebot" in Module 2. Without a quote entity, the goldsmith calculates a price but has no way to formally present it to the customer for approval before starting work.

**Our status:** CostCalculationService can compute a price. InvoiceService can generate invoices. But there's no Quote/Kostenvoranschlag entity between them.

**Industry examples:**
- QuoteMachine: "Interactive quotes with add-ons, fillable forms, signature fields"
- Orderry: "Create, send, and track repair estimates with e-signature approval"
- PIRO: "Customer Portal allows customers to create price quotes"

### 3. Customer SMS/Email Notifications

**What competitors do:**
- Auto-send SMS or email on every status change
- "Your repair has been received" → "Work started" → "Ready for pickup"
- Configurable per notification type (some via SMS, some via email)
- WhatsApp integration (PrismaNote)
- Customer can reply to confirm pickup time

**Why this matters:** The Ideensammlung explicitly requests "Push-Notifications / E-Mail" and gives examples: "Morgen: Kundenname XY, Artikel: Ring" — these are meant to go to the goldsmith AND the customer.

**Our status:** In-app notifications only (NotificationBell). No SMS, no email, no WhatsApp. Goldsmith gets reminders but customer gets nothing.

**Industry examples:**
- PrismaNote: "Per WhatsApp oder E-Mail benachrichtigen wenn Reparatur fertig"
- Luxare: "Automated SMS or email alerts when job moves between stages"
- RepairDesk: "Notify customers via SMS and email"

### 4. QR/Barcode Label Printing

**What competitors do:**
- Print adhesive labels with QR code, order number, customer name
- Attach to physical piece, repair bag, or work envelope
- Goldsmith scans label at workbench to log time, change status
- Labels include: order ID, customer name, deadline, current status

**Why this matters:** Our QR scanner page exists but there's nothing TO scan — no labels are generated. The scanner workflow is half-built without the ability to print labels.

**Our status:** ScannerPage accepts manual order number entry. No label generation, no printing.

**Industry examples:**
- PrismaNote: "Etiketten & Reparaturbeutel für Juweliere — Beutel direkt bedrucken"
- PIRO: "Barcode and RFID processing"
- Craftybase: "Barcode support for inventory items"

---

## HIGH Priority Gaps

### 5. Hallmarking/Certification Tracking
Track hallmark submissions (Punzierung), certificate numbers, assay office status. German goldsmiths are required to hallmark precious metals above certain weights.

### 6. Before/After Photo Documentation
Side-by-side before (intake) and after (completion) photos for repairs. Auto-attached to order for customer transparency and legal protection.

### 7. Insurance Valuation Certificates
Generate official valuation certificates (Wertgutachten) for insurance purposes. PDF with goldsmith stamp, material details, appraised value.

### 8. Customer Self-Service Portal
Customer-facing web page where they can check order/repair status without calling the workshop.

### 9. POS/Cash Register Integration
GoBD/TSE-compliant cash register for walk-in sales (German tax law requirement for retail).

---

## Technical State-of-the-Art (2026)

### What leading ERPs do technically:
1. **Live price feeds** — metal prices updating every 15 minutes, auto-recalculating inventory values
2. **AI-assisted forecasting** — predict material needs based on seasonal order patterns
3. **Mobile-first interfaces** — large touch targets, workshop-optimized views
4. **Automated communications** — multi-channel (SMS, email, WhatsApp) triggered by workflow events
5. **Customer portals** — self-service status checking, quote approval, payment
6. **Zero-code workflow customization** — admin can modify status pipelines without code changes
7. **Digital twin simulation** — simulate production schedules before committing resources

### What we already do well:
- Mobile-responsive layout with 44px touch targets ✓
- ML-based duration prediction (unique differentiator) ✓
- Real-time WebSocket updates ✓
- PDF invoice and receipt generation ✓
- GDPR compliance framework ✓
- Automated in-app notifications ✓
- Role-based access control ✓

---

## Implementation Priority

Based on impact × effort:

| Priority | Feature | Impact | Effort |
|----------|---------|--------|--------|
| 1 | Repair tracking workflow | Very High (30-50% of revenue) | Medium |
| 2 | Quote/Kostenvoranschlag pipeline | Very High (required for Module 2) | Medium |
| 3 | Customer email notifications | High (Ideensammlung requirement) | Small |
| 4 | QR label printing | High (completes scanner workflow) | Small |

---

## Sources

- [PrismaNote Goldschmiede Software](https://www.prismanote.de/goldschmied)
- [Synergics ERP 2026 Upgrades](https://www.synergicssolutions.com/behind-the-scenes-7-ways-synergics-is-upgrading-erp-for-jewellery-businesses-in-2026)
- [PIRO Jewelry ERP](https://www.gopiro.com/)
- [Luxare Repair Tracking](https://www.luxare.com/jewelry-repair)
- [Orderry Jewelry Software](https://orderry.com/jewelry-software/)
- [QuoteMachine for Jewelers](https://www.quotemachine.com/en/jewelery/)
- [Gem Logic Repair Management](https://www.gem-logic.com/repair-management)
- [RepairDesk Jewelry](https://www.repairdesk.co/jewelry-repair-shop-software/)
- [Top 10 Jewelry Software Solutions 2025](https://www.gem-logic.com/articles/top-10-software-solutions-for-jewelers-2025/)
- [CCJewel Reparaturverwaltung](http://design.reparaturverwaltung.net/)
- [PrismaNote Etiketten & Reparaturbeutel](https://www.prismanote.de/etiketten-reparaturbeutel)
- [PrismaNote Reparaturmanagement](https://www.prismanote.de/effizientes-reparaturmanagement-von-der-annahme-bis-zur-abholung)
- [Capterra Juwelier Software DE](https://www.capterra.com.de/directory/10061/jewelry-store-management/software)
