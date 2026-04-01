# Make It Work: Critical Gaps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 7 CRITICAL gaps that prevent the Goldsmith ERP from functioning as described in the Ideensammlung — mandatory order fields, status workflow, PDF generation, photo upload, color system, customer 360 page, and handoff UI.

**Architecture:** Three independent tracks that can be parallelized. Track A (Order Model) is the foundation — it adds goldsmith-specific fields and the status workflow gate. Track B (Infrastructure) adds PDF generation and photo upload. Track C (Frontend) builds the missing pages and fixes the color system. Tracks B and C have no dependency on Track A.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy async / WeasyPrint (PDF) / Pillow (thumbnails) / React 18.3 / TypeScript / CSS Custom Properties

**Research:** `docs/superpowers/specs/` contains 8 research agent reports from the parallel analysis session.

---

## Track A: Order Data Model + Status Workflow

### Task A1: Add goldsmith-specific fields to Order model

**Files:**
- Modify: `src/goldsmith_erp/db/models.py` — Order class (line 294)
- Modify: `src/goldsmith_erp/models/order.py` — OrderCreate, OrderUpdate schemas
- Create: `alembic/versions/20260401_add_goldsmith_order_fields.py`

- [ ] **Step 1: Add new columns to Order model**

Add after line 333 (`completed_at`):
```python
    # Goldsmith Intake Fields (Pflichtfelder for order confirmation)
    alloy = Column(String(20), nullable=True, index=True)  # '585', '750', '333', etc.
    ring_size_mm = Column(Float, nullable=True)  # Per-order ring size (mm inner circumference)
    surface_finish = Column(String(50), nullable=True)  # 'Hochglanz', 'Matt', 'Gebürstet', 'Gehämmert', 'Oxidiert'
    fitting_date = Column(DateTime, nullable=True)  # Anprobe-Datum
    has_scrap_gold = Column(Boolean, default=False)  # Altgold vorhanden?
    special_instructions = Column(Text, nullable=True)  # Sonderwünsche

    # Soft delete (prevent financial data loss)
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
```

- [ ] **Step 2: Expand OrderStatusEnum**

Replace the current 4-state enum (line 20) with the goldsmith production workflow:
```python
class OrderStatusEnum(str, enum.Enum):
    DRAFT = "draft"                    # Initial input, Pflichtfelder not yet complete
    CONFIRMED = "confirmed"            # All Pflichtfelder filled, order accepted
    IN_PROGRESS = "in_progress"        # Active production
    WAITING_FOR_FITTING = "waiting_for_fitting"  # Rohfassung fertig, Anprobe pending
    FITTING_DONE = "fitting_done"      # After successful fitting
    READY_FOR_SETTING = "ready_for_setting"  # Bereit für Fassen
    QUALITY_CHECK = "quality_check"    # Qualitätskontrolle
    COMPLETED = "completed"            # Fertiggestellt
    DELIVERED = "delivered"            # Ausgeliefert
    # Legacy compatibility
    NEW = "new"                        # Maps to DRAFT for backward compat
```

- [ ] **Step 3: Update Pydantic schemas in `models/order.py`**

Add the new fields to `OrderCreate` and `OrderUpdate`:
```python
    alloy: Optional[str] = None
    ring_size_mm: Optional[float] = None
    surface_finish: Optional[str] = None
    fitting_date: Optional[datetime] = None
    has_scrap_gold: bool = False
    special_instructions: Optional[str] = None
```

- [ ] **Step 4: Create Alembic migration**

Manual migration that adds the 8 new columns + updates the enum type. Use `ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS` for each new status.

- [ ] **Step 5: Commit**

```bash
git add src/goldsmith_erp/db/models.py src/goldsmith_erp/models/order.py alembic/versions/
git commit -m "feat: add goldsmith intake fields and expanded order status workflow

Alloy, ring_size_mm, surface_finish, fitting_date, has_scrap_gold,
special_instructions, soft delete. Status workflow: DRAFT→CONFIRMED→
IN_PROGRESS→COMPLETED→DELIVERED with goldsmith production stages.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task A2: Add order confirmation gate (Pflichtfelder-Garantie)

**Files:**
- Modify: `src/goldsmith_erp/services/order_service.py`

- [ ] **Step 1: Add confirmation validation to order_service.py**

Add a method that validates all Pflichtfelder before allowing status transition to CONFIRMED:
```python
@staticmethod
def validate_for_confirmation(order: OrderModel) -> list[str]:
    """Return list of missing required fields for order confirmation."""
    missing = []
    if not order.customer_id:
        missing.append("Kunde (customer_id)")
    if not order.title:
        missing.append("Auftragsbezeichnung (title)")
    if not order.metal_type:
        missing.append("Metallart (metal_type)")
    if not order.alloy:
        missing.append("Legierung (alloy)")
    if not order.deadline:
        missing.append("Abgabetermin (deadline)")
    # Ring-specific: require ring_size_mm if order_type is ring
    if order.order_type and order.order_type.lower() in ('ring', 'engagement_ring', 'wedding_ring'):
        if not order.ring_size_mm:
            missing.append("Ringmaß (ring_size_mm)")
    return missing
```

- [ ] **Step 2: Add status transition guard to update_order**

In `update_order`, before applying a status change, check:
```python
if new_status == OrderStatusEnum.CONFIRMED:
    missing = OrderService.validate_for_confirmation(order)
    if missing:
        raise ValueError(f"Pflichtfelder nicht ausgefüllt: {', '.join(missing)}")
```

- [ ] **Step 3: Add soft delete to delete_order**

Replace hard delete with soft delete. Block deletion if order has invoices or time entries.

- [ ] **Step 4: Commit**

---

### Task A3: Update OrderFormModal with goldsmith intake fields

**Files:**
- Modify: `frontend/src/components/orders/OrderFormModal.tsx`
- Modify: `frontend/src/lib/validation/schemas.ts`
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Add new fields to OrderType in types.ts**

```typescript
alloy?: string;
ring_size_mm?: number;
surface_finish?: string;
fitting_date?: string;
has_scrap_gold?: boolean;
special_instructions?: string;
```

- [ ] **Step 2: Add fields to OrderCreateSchema in schemas.ts**

Add alloy, surface_finish as optional strings, ring_size_mm as optional number, fitting_date as optional string, has_scrap_gold as boolean.

- [ ] **Step 3: Add intake fields to OrderFormModal**

Add a new "Auftrag" tab between Basis and Metall with:
- Legierung dropdown (333, 375, 585, 750, 900, 999, Ag925, Ag800, Pt950)
- Oberflaeche dropdown (Hochglanz, Matt, Gebürstet, Gehämmert, Oxidiert, Sandgestrahlt)
- Ringmaß input (shown conditionally when order_type is ring)
- Anprobe-Datum date picker
- Altgold vorhanden checkbox
- Sonderwünsche textarea

Add a "Pflichtfelder" checklist panel showing completion status before the submit button.

- [ ] **Step 4: Verify build and commit**

```bash
cd frontend && yarn build
git add frontend/src/
git commit -m "feat: add goldsmith intake fields to order form (Pflichtfelder)"
```

---

## Track B: PDF Generation + Photo Upload

### Task B1: Add PDF generation infrastructure

**Files:**
- Create: `src/goldsmith_erp/services/pdf_service.py`
- Create: `src/goldsmith_erp/templates/invoice.html`
- Create: `src/goldsmith_erp/templates/scrap_gold_receipt.html`
- Modify: `pyproject.toml` — add weasyprint dependency

- [ ] **Step 1: Add WeasyPrint dependency**

```bash
poetry add weasyprint jinja2
```

- [ ] **Step 2: Create Jinja2 HTML templates**

Create `src/goldsmith_erp/templates/invoice.html`:
- German invoice layout (Rechnung)
- Fields: Rechnungsnummer, Datum, Fälligkeitsdatum, customer address block
- Line items table with Beschreibung, Menge, Einzelpreis, Gesamtpreis
- Subtotal, MwSt (19%), Gesamtbetrag
- Optional: Gutschrift Altgold line (negative amount)
- Footer: bank details placeholder, Steuernummer placeholder

Create `src/goldsmith_erp/templates/scrap_gold_receipt.html`:
- Ankaufsbeleg layout
- Customer data, date, items table (Beschreibung, Legierung, Gewicht, Feingehalt)
- Total fine gold, gold price, total value
- Signature image (base64 embedded)
- Legal disclaimer text

- [ ] **Step 3: Create PDF service**

```python
class PDFService:
    @staticmethod
    def render_invoice_pdf(invoice_data: dict) -> bytes:
        """Render invoice as PDF bytes using WeasyPrint."""
        template = jinja_env.get_template("invoice.html")
        html = template.render(**invoice_data)
        return weasyprint.HTML(string=html).write_pdf()

    @staticmethod
    def render_scrap_gold_receipt(scrap_gold_data: dict) -> bytes:
        """Render scrap gold receipt as PDF bytes."""
        template = jinja_env.get_template("scrap_gold_receipt.html")
        html = template.render(**scrap_gold_data)
        return weasyprint.HTML(string=html).write_pdf()
```

- [ ] **Step 4: Add PDF download endpoints**

Add to invoice router:
- `GET /api/v1/invoices/{id}/pdf` — returns `StreamingResponse(content_type="application/pdf")`

Add to scrap gold router:
- `GET /api/v1/scrap-gold/{id}/receipt.pdf` — returns PDF receipt

- [ ] **Step 5: Commit**

---

### Task B2: Add photo upload infrastructure

**Files:**
- Create: `src/goldsmith_erp/services/photo_service.py`
- Create: `src/goldsmith_erp/api/routers/photos.py`
- Modify: `src/goldsmith_erp/main.py` — register router
- Modify: `src/goldsmith_erp/core/config.py` — add PHOTO_STORAGE_PATH

- [ ] **Step 1: Add config setting**

```python
PHOTO_STORAGE_PATH: str = "./uploads/photos"
PHOTO_MAX_SIZE_MB: int = 8
PHOTO_ALLOWED_TYPES: list = ["image/jpeg", "image/png", "image/webp"]
```

- [ ] **Step 2: Create photo service**

```python
class PhotoService:
    @staticmethod
    async def upload_photo(db, order_id, file: UploadFile, user_id, notes=None) -> OrderPhoto:
        """Save uploaded photo to disk, create DB record, generate thumbnail."""
        # Validate file type and size
        # Generate unique filename
        # Save to PHOTO_STORAGE_PATH/{order_id}/{filename}
        # Generate 200px thumbnail
        # Create OrderPhoto record
        # Return photo object

    @staticmethod
    async def get_photos(db, order_id) -> list[OrderPhoto]:
        """Get all photos for an order."""

    @staticmethod
    async def delete_photo(db, photo_id, user_id) -> None:
        """Delete photo file and DB record."""

    @staticmethod
    def get_photo_path(photo: OrderPhoto) -> Path:
        """Resolve the full filesystem path for a photo."""
```

- [ ] **Step 3: Create photo router**

```python
@router.post("/orders/{order_id}/photos")
async def upload_photo(order_id: int, file: UploadFile = File(...), ...):
    """Upload a photo for an order."""

@router.get("/orders/{order_id}/photos")
async def list_photos(order_id: int, ...):
    """List all photos for an order."""

@router.get("/photos/{photo_id}/file")
async def serve_photo(photo_id: str, ...):
    """Serve the actual photo file."""

@router.get("/photos/{photo_id}/thumbnail")
async def serve_thumbnail(photo_id: str, ...):
    """Serve the thumbnail version."""

@router.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str, ...):
    """Delete a photo."""
```

- [ ] **Step 4: Register router and commit**

---

## Track C: Missing Frontend Pages + Color System

### Task C1: Fix color system — replace hardcoded hex with CSS variables

**Files:**
- Modify: `frontend/src/styles/brand-tokens.css` — add complete semantic token layer
- Modify: ALL 18 CSS files with hardcoded hex values

- [ ] **Step 1: Define complete semantic token layer in brand-tokens.css**

Add to `:root {}`:
```css
/* Semantic tokens — all UI elements reference these, never raw hex */
--color-surface-header: var(--color-brand-cta-600);
--color-surface-header-gradient: linear-gradient(135deg, var(--color-brand-cta-600), var(--color-brand-cta-700));
--color-surface-page: #f8f6f0;  /* warm ivory */
--color-surface-card: #ffffff;
--color-surface-sidebar: #ffffff;

--color-interactive-primary: var(--color-brand-cta-600);
--color-interactive-primary-hover: var(--color-brand-cta-700);
--color-interactive-primary-text: #ffffff;

--color-text-heading: var(--color-brand-primary-900);
--color-text-body: var(--color-brand-primary-700);
--color-text-muted: var(--color-brand-primary-400);

--color-border-default: var(--color-brand-primary-200);
--color-border-focus: var(--color-brand-cta-500);

--color-status-success: #16a34a;
--color-status-warning: #d97706;
--color-status-error: #dc2626;
--color-status-info: #2563eb;
```

- [ ] **Step 2: Replace #667eea / #764ba2 with semantic tokens**

The purple-blue gradient appears 64 times across 11 files. Replace ALL instances:
- `background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)` → `background: var(--color-surface-header-gradient)`
- `color: #667eea` → `color: var(--color-interactive-primary)`
- `border-color: #667eea` → `border-color: var(--color-border-focus)`

Target files: `layout.css`, `auth.css`, `dashboard.css`, `orders.css`, `materials.css`, `order-detail.css`, `scanner.css`, `calendar.css`, `notification-bell.css`, `invoices.css`, `scrap-gold.css`

- [ ] **Step 3: Replace remaining hardcoded colors with tokens**

For each CSS file, replace common patterns:
- `color: #333` / `#213547` → `var(--color-text-heading)`
- `color: #666` / `#6b7280` → `var(--color-text-muted)`
- `background: #f5f7fa` / `#f9fafb` → `var(--color-surface-page)`
- `border: ... #e0e0e0` / `#e5e7eb` → `var(--color-border-default)`

- [ ] **Step 4: Verify build and commit**

---

### Task C2: Build Customer 360 Detail Page

**Files:**
- Create: `frontend/src/pages/CustomerDetailPage.tsx`
- Create: `frontend/src/styles/customer-detail.css`
- Create: `frontend/src/api/measurements.ts`
- Modify: `frontend/src/App.tsx` — add route
- Modify: `frontend/src/pages/CustomersPage.tsx` — link to detail page

- [ ] **Step 1: Create measurements API client**

```typescript
export const measurementsApi = {
    getForCustomer: (customerId: number) => apiClient.get(`/customers/${customerId}/measurements`),
    add: (customerId: number, data: MeasurementCreate) => apiClient.post(`/customers/${customerId}/measurements`, data),
    update: (id: number, data: MeasurementUpdate) => apiClient.put(`/measurements/${id}`, data),
    delete: (id: number) => apiClient.delete(`/measurements/${id}`),
    getRingSize: (customerId: number, hand: string, finger: string) =>
        apiClient.get(`/customers/${customerId}/ring-size?hand=${hand}&finger=${finger}`),
};
```

- [ ] **Step 2: Create CustomerDetailPage with 4 tabs**

Tab 1 — Stammdaten: customer base data, editable
Tab 2 — Maß-Bibliothek: per-finger ring sizes with hand/finger selectors, chain lengths, add/edit/delete
Tab 3 — Auftragshistorie: visual timeline of orders with thumbnail photos, status, date, linked invoice
Tab 4 — Rechnungen: list of all invoices for this customer

- [ ] **Step 3: Add route and navigation**

In App.tsx: `<Route path="/customers/:id" element={...} />`
In CustomersPage.tsx: clicking a customer row navigates to `/customers/{id}`

- [ ] **Step 4: Verify build and commit**

---

### Task C3: Build Handoff UI

**Files:**
- Create: `frontend/src/api/handoffs.ts`
- Create: `frontend/src/components/orders/HandoffTab.tsx`
- Modify: `frontend/src/pages/OrderDetailPage.tsx` — add handoff tab
- Modify: `frontend/src/pages/DashboardPage.tsx` — add pending handoffs widget

- [ ] **Step 1: Create handoffs API client**

```typescript
export const handoffsApi = {
    create: (orderId: number, data: HandoffCreate) => apiClient.post(`/orders/${orderId}/handoff`, data),
    accept: (handoffId: number, data?: { response_notes?: string }) => apiClient.put(`/handoffs/${handoffId}/accept`, data),
    decline: (handoffId: number, data: { response_notes: string }) => apiClient.put(`/handoffs/${handoffId}/decline`, data),
    getPending: () => apiClient.get('/handoffs/pending'),
    getForOrder: (orderId: number) => apiClient.get(`/orders/${orderId}/handoffs`),
};
```

- [ ] **Step 2: Create HandoffTab component**

Shows handoff history for the order + "Übergabe erstellen" form:
- Goldsmith selector dropdown (list active users)
- Handoff type: Weitergabe / Prüfung anfordern / Zurück zur Nacharbeit / Fertigmeldung
- Notes textarea
- History list showing all past handoffs with accept/decline status

- [ ] **Step 3: Add pending handoffs widget to GoldsmithDashboard**

Fetch `GET /handoffs/pending`, show cards with order title, from-user, type, accept/decline buttons.

- [ ] **Step 4: Wire HandoffTab into OrderDetailPage**

Add `handoff` to OrderTab type union. Add tab button and content panel.

- [ ] **Step 5: Verify build and commit**

---

## Post-Implementation Verification

### Task V1: Full verification

- [ ] **Step 1: Run full test suite**
```bash
cd src && poetry run pytest ../tests/ -q --tb=short
```
Expected: 485+ passed, 0 failed

- [ ] **Step 2: Verify frontend builds**
```bash
cd frontend && yarn build
```

- [ ] **Step 3: Verify all modules import**
```bash
poetry run python -c "from goldsmith_erp.main import app; print(f'Routes: {len([r for r in app.routes if hasattr(r, \"path\")])}')"
```

- [ ] **Step 4: Verify running instance**
```bash
curl -s http://localhost:8080/health | python3 -m json.tool
```

- [ ] **Step 5: Commit all fixes and tag**
```bash
git tag -a v1.1.0-alpha -m "v1.1.0-alpha: Critical gaps fixed — goldsmith intake fields, PDF generation, photo upload, color system, customer 360, handoff UI"
```
