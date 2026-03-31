# Next Phase Implementation Plan
**Created:** 2025-11-10 (Session Continuation)
**Status:** Post CustomersPage & OrderDetailPage Enhancement

---

## Current State Analysis

### ✅ COMPLETED
**Backend (Test Coverage: ~65%)**
- ✅ CustomerService (40+ tests)
- ✅ OrderService (50+ tests)
- ✅ Auth & UserService (65+ tests)
- ✅ MetalInventoryService (18 unit + 25+ integration tests)
- ✅ CostCalculationService (16 unit tests)

**Frontend (CRM & Order Management: 90%)**
- ✅ CustomersPage - Full CRUD with search, filters, pagination
- ✅ OrderDetailPage - Enhanced with cost breakdown, metal info, customer cards
- ✅ LoginPage, RegisterPage, DashboardPage (basic)
- ✅ ScannerPage

### ⚠️ GAPS IDENTIFIED

**Backend - Missing Test Coverage (3 services):**
- ❌ MaterialService - No tests (7.4 KB)
- ❌ TimeTrackingService - No tests (10.8 KB)
- ❌ ActivityService - No tests (6 KB)

**Frontend - Read-Only Pages (Need CRUD):**
- ⚠️ MaterialsPage - Read-only, "New Material" button not wired
- ⚠️ OrdersPage - Read-only, "New Order" button not wired
- ⚠️ UsersPage - Likely read-only

**Frontend - Missing Pages (Backends Ready):**
- ❌ TimeTrackingPage - Backend complete, no UI
- ❌ MetalInventoryPage - Backend complete, no UI

**Frontend - Basic Pages (Need Enhancement):**
- ⚠️ DashboardPage - Likely needs KPI cards, charts

---

## Priority Analysis

### P0 - Critical for Production
1. **MaterialsPage CRUD** - Materials are core to goldsmith operations
2. **OrdersPage Enhancement** - Need to create orders from UI
3. **Test Coverage** - MaterialService, TimeTrackingService (critical paths)

### P1 - High Impact
4. **MetalInventoryPage** - Metal management UI (backend ready)
5. **TimeTrackingPage** - Time tracking UI (backend ready)
6. **DashboardPage Enhancement** - KPIs, recent orders, alerts

### P2 - Nice to Have
7. **ActivityService Tests** - Activity logging (less critical)
8. **UsersPage CRUD** - Admin user management
9. **Calendar View** - Future feature

---

## Implementation Plan

## Phase 1: Core CRUD Pages (Days 1-3)
**Goal:** Enable full material and order management from UI

### Day 1: MaterialsPage CRUD (P0)
**Time:** 8-10 hours

**Features:**
1. **Material List** (existing, enhance)
   - ✅ Already shows materials table
   - Add search by name
   - Add filter by low stock (< threshold)
   - Add sort by name, price, stock
   - Add "Low Stock" visual indicator

2. **Material Form Modal**
   - Create component: `MaterialFormModal.tsx`
   - Fields:
     - Name* (text)
     - Description (textarea)
     - Unit Price* (number, € currency)
     - Stock* (number)
     - Unit* (dropdown: Stück, g, kg, ml, l)
     - Min Stock Threshold (number, for alerts)
   - Validation: required fields, positive numbers
   - Wire up "New Material" button

3. **Material Actions**
   - Edit button (per row) → open modal with data
   - Delete button (with confirmation)
   - Stock adjustment modal (+/- stock)

**Files:**
```
frontend/src/components/materials/MaterialFormModal.tsx  (new)
frontend/src/pages/MaterialsPage.tsx                     (enhance)
frontend/src/styles/materials.css                        (new)
```

---

### Day 2: OrdersPage Enhancement (P0)
**Time:** 10-12 hours

**Features:**
1. **Orders List** (existing, enhance)
   - ✅ Already shows orders table with click navigation
   - Add search by title, description
   - Add filter by status (NEW, IN_PROGRESS, COMPLETED, DELIVERED)
   - Add filter by customer (dropdown/autocomplete)
   - Add sort by deadline, created_at, price
   - Add pagination (25/50/100 per page)
   - Status badges with colors (already exists)

2. **Order Form Modal**
   - Create component: `OrderFormModal.tsx`
   - **Basic Info Tab:**
     - Title* (text)
     - Description* (textarea)
     - Customer* (searchable dropdown from customers API)
     - Deadline (date picker)
     - Status (dropdown: NEW, IN_PROGRESS, COMPLETED, DELIVERED)
     - Current Location (text)

   - **Metal Tab** (optional):
     - Metal Type (dropdown: Gold 24K, Gold 18K, Gold 14K, Silver 925, Silver 999, Platinum)
     - Estimated Weight (number, g)
     - Scrap Percentage (number, default 5%)
     - Costing Method (dropdown: FIFO, LIFO, AVERAGE, SPECIFIC)
     - Specific Batch ID (if SPECIFIC selected)

   - **Pricing Tab:**
     - Manual Price Override (number, €)
     - Labor Hours (number)
     - Hourly Rate (number, default 75€)
     - Profit Margin % (number, default 40%)
     - VAT Rate % (number, default 19%)

   - **Validation:**
     - Required: title, description, customer_id
     - If metal_type selected, require estimated_weight_g
     - If costing_method=SPECIFIC, require specific_metal_purchase_id
     - Positive numbers for all numeric fields

3. **Order Actions**
   - Edit button → open modal with data
   - Delete button (with confirmation, soft delete)
   - Duplicate button (create copy)
   - Quick status change dropdown (in table row)

**Files:**
```
frontend/src/components/orders/OrderFormModal.tsx        (new)
frontend/src/pages/OrdersPage.tsx                        (enhance)
frontend/src/styles/orders.css                           (new)
```

---

### Day 3: Test Coverage - MaterialService (P0)
**Time:** 6-8 hours

**File:** `tests/unit/test_material_service.py`

**Test Cases:**
1. Material Creation
   - Valid material creation
   - Duplicate name validation
   - Required field validation
   - Negative price/stock validation
   - Invalid unit validation

2. Material Updates
   - Update name, description
   - Update price, stock
   - Update unit
   - Stock adjustment (add/subtract)
   - Prevent negative stock

3. Material Listing & Search
   - List all materials
   - Search by name (partial match)
   - Filter by low stock
   - Sort by name, price, stock
   - Pagination

4. Material Deletion
   - Delete material (soft or hard?)
   - Prevent deletion if used in orders
   - Cascade behavior

5. Stock Calculations
   - Calculate total stock value
   - Low stock detection
   - Stock history (if implemented)

**Integration Tests:**
- POST /api/v1/materials (create)
- GET /api/v1/materials (list)
- GET /api/v1/materials/{id} (get)
- PATCH /api/v1/materials/{id} (update)
- DELETE /api/v1/materials/{id} (delete)
- PATCH /api/v1/materials/{id}/adjust-stock (stock adjustment)

**Expected:** 25-30 test cases

---

## Phase 2: Metal Inventory & Time Tracking UI (Days 4-6)
**Goal:** Complete feature set with advanced UIs

### Day 4: MetalInventoryPage (P1)
**Time:** 10-12 hours

**Features:**
1. **Metal Purchase List**
   - Table with columns:
     - ID, Date, Metal Type, Weight (g), Price/g, Total Cost, Batch #, Status
   - Search by batch number
   - Filter by metal type
   - Filter by status (in_stock, partially_used, depleted)
   - Sort by date, price
   - Color-coded metal type badges (same as OrderDetailPage)

2. **Add Metal Purchase Modal**
   - Fields:
     - Metal Type* (dropdown with icons)
     - Purchase Date* (date picker)
     - Weight (g)* (number)
     - Price per Gram* (number, €)
     - Supplier (text)
     - Batch Number (auto-generated or manual)
     - Purity (number, %, e.g., 99.9% for gold)
     - Notes (textarea)
   - Auto-calculate total cost
   - Validation

3. **Metal Inventory Summary**
   - Cards showing:
     - Total Gold inventory (by type: 24K, 18K, 14K)
     - Total Silver inventory (925, 999)
     - Total Platinum inventory
     - Total value by metal type
   - Weight in grams, value in €

4. **Batch Detail View**
   - Click batch → see detail modal
   - Show:
     - Purchase info
     - Remaining weight
     - Orders using this batch
     - Usage history

**Files:**
```
frontend/src/pages/MetalInventoryPage.tsx                (new)
frontend/src/components/metal/MetalPurchaseFormModal.tsx (new)
frontend/src/components/metal/MetalSummaryCards.tsx      (new)
frontend/src/styles/metal-inventory.css                  (new)
frontend/src/api/metal-inventory.ts                      (new)
```

---

### Day 5-6: TimeTrackingPage (P1)
**Time:** 12-16 hours

**Features:**
1. **Time Entry List**
   - Table with columns:
     - Date, Order, User, Task, Hours, Notes
   - Filter by date range (this week, this month, custom)
   - Filter by user (dropdown)
   - Filter by order (searchable)
   - Group by user or order
   - Total hours summary

2. **Add Time Entry Modal**
   - Fields:
     - Order* (searchable dropdown)
     - Task Type* (dropdown: Design, Manufacturing, Polish, Repair, Meeting, Admin)
     - Date* (date picker, default today)
     - Start Time (time picker, optional)
     - End Time (time picker, optional)
     - Hours* (number, auto-calculate from start/end if provided)
     - Notes (textarea)
   - Validation
   - Save → creates TimeEntry

3. **Time Tracking Widget (for active tracking)**
   - Start Timer button
   - Running timer display (00:00:00)
   - Stop button → save entry
   - Pause/Resume buttons
   - Order selector (for what you're working on)

4. **Time Reports**
   - Weekly summary by user
   - Monthly summary by project
   - Billable vs non-billable hours
   - Export to CSV

**Files:**
```
frontend/src/pages/TimeTrackingPage.tsx                  (new)
frontend/src/components/time/TimeEntryFormModal.tsx      (new)
frontend/src/components/time/ActiveTimer.tsx             (new)
frontend/src/components/time/TimeReportsSummary.tsx      (new)
frontend/src/styles/time-tracking.css                    (new)
frontend/src/api/time-tracking.ts                        (new)
```

---

## Phase 3: Test Coverage Completion (Day 7)
**Goal:** Reach 80%+ test coverage

### TimeTrackingService Tests
**File:** `tests/unit/test_time_tracking_service.py`

**Test Cases:**
1. Time Entry Creation
   - Valid entry
   - Auto-calculate hours from start/end
   - Validate order_id exists
   - Validate positive hours
   - Validate date not in future

2. Time Entry Updates
   - Update hours, notes
   - Update task type
   - Change order

3. Time Entry Listing & Filtering
   - List all entries
   - Filter by user
   - Filter by order
   - Filter by date range
   - Group by user/order
   - Calculate totals

4. Time Reports
   - Weekly hours by user
   - Monthly hours by project
   - Billable hours calculation

**Expected:** 20-25 test cases

---

### ActivityService Tests (Optional)
**File:** `tests/unit/test_activity_service.py`

**Test Cases:**
1. Activity Logging
   - Log user action
   - Log system event
   - Auto-capture user_id, timestamp

2. Activity Retrieval
   - Get by user
   - Get by entity (order, customer)
   - Get by date range
   - Pagination

3. Activity Types
   - ORDER_CREATED, ORDER_UPDATED, CUSTOMER_CREATED, etc.
   - Validate activity_type enum

**Expected:** 10-15 test cases

**Estimated Time:** 8-10 hours

---

## Phase 4: Dashboard Enhancement (Day 8)
**Goal:** Beautiful, informative dashboard

### DashboardPage Enhancement (P1)
**Time:** 8-10 hours

**Features:**
1. **KPI Cards**
   - Total Orders (this month)
   - Revenue (this month)
   - Active Orders (in progress)
   - Pending Deadlines (next 7 days)
   - Low Stock Alerts
   - Time Tracked (this week)

2. **Recent Orders Widget**
   - Last 5 orders
   - Click → navigate to detail

3. **Deadline Calendar**
   - Mini calendar showing orders by deadline
   - Color-coded by status
   - Click date → filter orders

4. **Stock Alerts**
   - Materials below threshold
   - Metal inventory running low

5. **Revenue Chart**
   - Last 6 months revenue
   - Line chart or bar chart
   - Use Chart.js or Recharts

6. **Activity Feed**
   - Recent system activity
   - Last 10 activities
   - User actions, order updates

**Files:**
```
frontend/src/pages/DashboardPage.tsx                     (enhance)
frontend/src/components/dashboard/KPICard.tsx            (new)
frontend/src/components/dashboard/RecentOrders.tsx       (new)
frontend/src/components/dashboard/StockAlerts.tsx        (new)
frontend/src/components/dashboard/RevenueChart.tsx       (new)
frontend/src/styles/dashboard.css                        (enhance)
```

---

## Success Criteria

### Phase 1 Complete:
- [ ] MaterialsPage has full CRUD (create, edit, delete, stock adjust)
- [ ] OrdersPage has full CRUD with search, filters, pagination
- [ ] Material form validates correctly
- [ ] Order form validates correctly (basic + metal + pricing)
- [ ] MaterialService has 25+ tests, all passing
- [ ] Test coverage: 70%+

### Phase 2 Complete:
- [ ] MetalInventoryPage shows purchases, batches, summary
- [ ] Add metal purchase modal works
- [ ] TimeTrackingPage shows entries with filters
- [ ] Time entry modal works (manual + timer)
- [ ] Time reports display correctly

### Phase 3 Complete:
- [ ] TimeTrackingService has 20+ tests
- [ ] ActivityService has 10+ tests
- [ ] All tests pass
- [ ] Test coverage: 80%+

### Phase 4 Complete:
- [ ] Dashboard shows KPI cards
- [ ] Dashboard shows recent orders
- [ ] Dashboard shows stock alerts
- [ ] Dashboard shows revenue chart
- [ ] Dashboard shows activity feed

---

## Timeline Summary

| Day | Phase | Focus | Deliverables | Hours |
|-----|-------|-------|--------------|-------|
| 1 | P1 | MaterialsPage CRUD | Material form, CRUD ops | 8-10h |
| 2 | P1 | OrdersPage Enhancement | Order form (3 tabs), filters | 10-12h |
| 3 | P1 | MaterialService Tests | 25+ tests, integration | 6-8h |
| 4 | P2 | MetalInventoryPage | Purchase list, add modal, summary | 10-12h |
| 5-6 | P2 | TimeTrackingPage | Entry list, form, timer, reports | 12-16h |
| 7 | P3 | Test Coverage | TimeTracking + Activity tests | 8-10h |
| 8 | P4 | Dashboard Enhancement | KPIs, charts, alerts | 8-10h |

**Total Estimated Time:** 62-78 hours (8-10 days)

---

## Next Immediate Action

**START NOW:** MaterialsPage CRUD

### Step 1: Create MaterialFormModal component
```bash
touch frontend/src/components/materials/MaterialFormModal.tsx
touch frontend/src/styles/materials.css
```

### Step 2: Implement form with fields
- Name, Description, Unit Price, Stock, Unit
- Validation (required, positive numbers)
- Create/Edit modes

### Step 3: Wire up to MaterialsPage
- "New Material" button → open modal
- Edit button (per row) → open modal with data
- Delete button → confirmation → API call

### Step 4: Test CRUD operations
- Create material
- Edit material
- Delete material
- Stock adjustment

**Expected Output:** Full material management from UI, production-ready CRUD

---

## Architecture Notes

### Component Patterns
- **Modal Forms:** Reusable pattern from CustomersPage (CustomerFormModal)
- **Search & Filters:** Similar to CustomersPage
- **Pagination:** Use existing pagination component
- **Loading States:** Consistent loading/error handling
- **API Integration:** Use axios from `api/` folder

### Styling
- **Consistent Design:** Follow CustomersPage styling
- **Color Scheme:** Purple gradient for primary actions
- **Responsive:** Mobile-first design
- **Accessibility:** Proper labels, keyboard navigation

### Testing
- **Unit Tests:** Service layer logic
- **Integration Tests:** API endpoints
- **Manual Testing:** Full CRUD workflows
- **Edge Cases:** Validation, error handling

---

**Let's start with MaterialsPage CRUD!** 🚀
