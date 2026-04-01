# Remaining 13 Ideensammlung Items — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all 13 remaining items from the Ideensammlung gap analysis to achieve 100% feature coverage.

**Architecture:** 5 independent batches that can be parallelized. Each batch groups items that share files or dependencies. No cross-batch file conflicts.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy async / fpdf2 / React 18.3 / TypeScript

---

## Batch 1: Material Enhancements (Items 3, 4, 5, 6)
**Files touched:** Material model, material service/router, MaterialFormModal, MaterialsPage

### Task 1: Add image_url, supplier, webshop_url, min_stock to Material model

- Add 4 columns to Material in `db/models.py`: `image_url String(500)`, `supplier String(200)`, `webshop_url String(500)`, `min_stock Float default=10.0`
- Update MaterialBase/MaterialCreate/MaterialUpdate/MaterialRead in `models/material.py`
- Update MaterialType/MaterialCreateInput in `frontend/src/types.ts`
- Update MaterialCreateSchema in `frontend/src/lib/validation/schemas.ts`
- Create single Alembic migration for all 4 columns
- Commit

### Task 2: Update MaterialFormModal and MaterialsPage with new fields

- Add to MaterialFormModal: Lieferant (text), Webshop URL (url), Mindestbestand (number), Bild (file upload)
- Add to MaterialsPage table: thumbnail column, Lieferant column, "Bestellen" link icon when webshop_url set
- Replace hardcoded `stock < 10` with `stock < (min_stock ?? 10)` in MaterialsPage low-stock filter
- Add material image upload endpoint: `POST /materials/{id}/image` (reuse photo_service helpers)
- Commit

### Task 3: Add purchase list endpoint and UI

- Add `GET /api/v1/materials/purchase-list` endpoint: query materials where `stock <= min_stock`, group by supplier
- Add `getPurchaseList()` to frontend materials API client
- Add "Bestellliste" button in MaterialsPage header → modal showing grouped list by supplier
- Update notification_service `check_low_stock_alerts()` to use `Material.stock <= Material.min_stock`
- Wire `check_low_stock_alerts()` into system_monitor loop
- Commit

---

## Batch 2: Order Production UI (Items 1, 2)
**Files touched:** OrderDetailPage, OrderContext, invoices router, new ArbeitszettelTab

### Task 4: Add Arbeitszettel tab to OrderDetailPage

- Add 'arbeitszettel' to OrderTab type in OrderContext
- Create `frontend/src/components/orders/ArbeitszettelTab.tsx`: large touch-friendly form with actual_weight_g, labor_hours, alloy, ring_size_mm, surface_finish, current_location
- Show estimated values alongside for reference (Soll vs current Ist)
- "Speichern" button calls ordersApi.update() with PATCH
- Wire into OrderDetailPage as tab between Zeiterfassung and Notizen
- Commit

### Task 5: Add DATEV/Lexoffice accounting export

- Create `src/goldsmith_erp/services/accounting_export_service.py`: DATEV CSV (Buchungsstapel format) and Lexoffice CSV
- Add `GET /api/v1/invoices/export/datev?date_from=&date_to=` and `/export/lexoffice` endpoints to invoices router
- StreamingResponse with Content-Disposition: attachment, UTF-8 BOM for Excel compat
- Add Export dropdown button (DATEV/Lexoffice) to InvoicesPage header (ADMIN only)
- Commit

---

## Batch 3: Scrap Gold + Notifications (Items 7, 8, 9)
**Files touched:** ScrapGoldTab, scrap_gold router, notification_service, system_monitor

### Task 6: Wire photo upload into ScrapGoldTab

- Add `POST /scrap-gold/{id}/items/{item_id}/photo` endpoint to scrap_gold router
- Add `GET /scrap-gold/{id}/items/{item_id}/photo` serve endpoint
- Add `uploadItemPhoto()` to frontend scrap-gold API client
- Add photo column to ScrapGoldTab items table: upload input when no photo, thumbnail when photo exists
- Commit

### Task 7: Add pickup and fitting reminder scanning

- Add `check_pickup_reminders()` to notification_service: scan orders where status=COMPLETED, notify if not yet delivered
- Add `check_fitting_reminders()` to notification_service: scan orders where status=WAITING_FOR_FITTING, notify to schedule Anprobe
- Wire both + existing `check_deadline_warnings()` + `check_low_stock_alerts()` into system_monitor `_run_one_cycle()`
- Commit

---

## Batch 4: Customer 360 Completion (Items 10, 11, 12)
**Files touched:** CustomerDetailPage, measurements API, photos API, notification_service

### Task 8: Wire Maß-Bibliothek to MeasurementService

- Fix MEASUREMENT_TYPES in CustomerDetailPage to match backend enum (remove bracelet_length/bangle_size, add correct values)
- Add update() and remove() methods to measurements API client
- Add delete button to each measurement card
- Add typed CustomerMeasurement interface to types.ts
- Optional: per-finger ring-size grid (left/right columns, 5 finger rows)
- Commit

### Task 9: Add photo thumbnails to customer order history

- Create `frontend/src/api/photos.ts` API client
- Create `frontend/src/components/AuthenticatedImage.tsx`: fetches image via Axios (with auth), displays as blob URL
- In CustomerDetailPage AuftraegeTab: fetch first photo per order, show 48x48 thumbnail in timeline cards
- Commit

### Task 10: Add birthday marketing reminder

- Add `BIRTHDAY_REMINDER = "birthday_reminder"` to NotificationTypeEnum
- Add `check_birthday_reminders()` to notification_service: scan customers whose birthday is tomorrow, notify ADMIN
- Wire into system_monitor loop
- Create Alembic migration for new enum value
- Commit

---

## Batch 5: Dashboard Todo (Item 13)
**Files touched:** DashboardPage only

### Task 11: Unified goldsmith todo list

- Replace three separate sections in GoldsmithDashboard with unified "Mein Arbeitsvorrat" list
- Merge: pending handoffs (URGENT), today-deadline orders (HIGH), WAITING_FOR_FITTING orders (MEDIUM), in_progress orders (LOW)
- Priority badges with color coding
- Keep Accept/Decline buttons inline for handoffs
- Sort by priority then deadline
- Commit

---

## Post-Implementation Verification

### Task 12: Full verification

- Run full test suite: `cd src && poetry run pytest ../tests/ -q --tb=short`
- Verify frontend builds: `cd frontend && yarn build`
- Verify all modules import: `poetry run python -c "from goldsmith_erp.main import app"`
- Restart backend container and verify health
- Tag: `git tag -a v1.1.0 -m "v1.1.0: 100% Ideensammlung coverage"`
