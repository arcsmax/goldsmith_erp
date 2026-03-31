# Next Steps Implementation Plan
**Created:** 2025-11-10
**Session:** Post P0 Completion

---

## Current State Analysis

### ✅ COMPLETED (Just Now)
1. **Metal Inventory Management System** - Full implementation with FIFO/LIFO/Average/Specific costing
2. **Metal Inventory Tests** - 18 unit tests, 25+ integration tests
3. **Cost Calculation Tests** - 16 unit tests covering all costing methods
4. **Production Deployment Guide** - 500+ line comprehensive guide
5. **P0 Critical Blockers** - Metal price management, test infrastructure

### 📊 Current Coverage Status
- **Tested Services:** metal_inventory_service.py ✅, cost_calculation_service.py ✅
- **Untested Services:** customer_service.py ❌, order_service.py ❌, user_service.py ❌, time_tracking_service.py ❌, activity_service.py ❌, material_service.py ❌
- **Test Coverage:** ~15% (2 out of 8 services)
- **Target:** 80%+

### 🎯 Identified Gaps

**Backend (85% Complete):**
- ✅ CRM (Customer Management)
- ✅ Order Management
- ✅ Cost Calculation with Metal Inventory
- ✅ Time Tracking
- ✅ Auth & Permissions (RBAC)
- ⚠️ Test Coverage (only 15%)

**Frontend (40% Complete):**
- ⚠️ CustomersPage (Backend ready, UI missing)
- ⚠️ Time-Tracking UI (Backend ready, UI missing)
- ⚠️ OrderDetailPage extensions (Backend ready, UI needs updates)
- ❌ Calendar View

---

## Priority Decision: TEST-FIRST + FRONTEND

### Rationale
1. **We're in testing momentum** - Just completed comprehensive tests for metal inventory
2. **Backend is 85% complete** - Most services need test coverage, not new features
3. **Frontend is the bottleneck** - Backend is solid, but users can't use features without UI
4. **Production readiness** - Tests are critical for deployment confidence

### Strategy: Parallel Track
**Week 1 (Days 1-3):** Test Coverage Expansion
**Week 1 (Days 4-7):** Frontend Critical Path (CustomersPage)
**Week 2:** Continue Frontend + Integration Testing

---

## Phase 1: Test Coverage Expansion (Days 1-3)

### Day 1: Customer Service Tests
**File:** `tests/unit/test_customer_service.py`
**Coverage Target:** CustomerService + Customer API endpoints

**Test Cases:**
1. Customer Creation
   - Valid customer (private)
   - Valid customer (business) with company_name
   - Duplicate email validation
   - Required field validation
   - Email format validation

2. Customer Updates
   - Update contact info
   - Update address
   - Add/remove tags
   - Change customer type
   - Update notes

3. Customer Listing & Search
   - List all customers
   - Filter by customer_type
   - Filter by is_active
   - Search by name (partial match)
   - Search by email
   - Search by company_name
   - Pagination

4. Customer Deletion (Soft Delete)
   - Deactivate customer (is_active=False)
   - Verify orders preserved
   - Reactivate customer

**Integration Tests:**
- POST /api/v1/customers (create)
- GET /api/v1/customers (list)
- GET /api/v1/customers/{id} (get)
- PATCH /api/v1/customers/{id} (update)
- DELETE /api/v1/customers/{id} (deactivate)
- Permissions testing (USER vs ADMIN)

**Estimated Time:** 6-8 hours

---

### Day 2: Order Service Tests
**File:** `tests/unit/test_order_service.py`
**Coverage Target:** OrderService + Order API endpoints

**Test Cases:**
1. Order Creation
   - Create order with customer
   - Create order with metal_type
   - Create order with gemstones
   - Validate customer_id exists
   - Validate metal_type enum
   - Default values (status=NEW, scrap=5%)

2. Order Updates
   - Update description
   - Update deadline
   - Update metal_type
   - Update costing_method
   - Change status (NEW → IN_PROGRESS → COMPLETED → DELIVERED)
   - Update location

3. Cost Calculation Integration
   - Order with metal_type triggers material cost calculation
   - Order without metal_type skips cost calculation
   - Manual overrides work
   - Price calculation formula correct

4. Order Listing & Filtering
   - List all orders
   - Filter by status
   - Filter by customer_id
   - Sort by deadline
   - Pagination

5. Order Relationships
   - Order.customer relationship works
   - Order.gemstones relationship works
   - Order.material_usage_records relationship works
   - Order.specific_metal_purchase relationship works

**Integration Tests:**
- POST /api/v1/orders (create)
- GET /api/v1/orders (list with filters)
- GET /api/v1/orders/{id} (get with relationships)
- PATCH /api/v1/orders/{id} (update)
- DELETE /api/v1/orders/{id} (soft delete)

**Estimated Time:** 8-10 hours

---

### Day 3: Auth & User Service Tests
**File:** `tests/unit/test_auth_service.py`, `tests/unit/test_user_service.py`
**Coverage Target:** Authentication, Authorization, User Management

**Test Cases:**

**Auth Service:**
1. User Registration
   - Valid registration
   - Duplicate email rejection
   - Password hashing (never stored plain)
   - Default role assignment (USER)
   - Required fields validation

2. Login
   - Valid credentials → JWT token
   - Invalid email → 401
   - Invalid password → 401
   - Inactive user → 403
   - Token contains correct claims (user_id, email, role)

3. JWT Token Validation
   - Valid token → user decoded
   - Expired token → 401
   - Invalid signature → 401
   - Tampered payload → 401

4. Permission System
   - Admin has all permissions
   - USER has limited permissions
   - Permission checks work (ORDER_CREATE, CUSTOMER_EDIT, etc.)

**User Service:**
1. User CRUD
   - Create user (admin only)
   - Get user by ID
   - Get user by email
   - Update user (email, name, role)
   - Deactivate user (is_active=False)

2. Role Management
   - Change user role (USER ↔ ADMIN)
   - Verify permissions change accordingly

**Integration Tests:**
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- GET /api/v1/auth/me (current user)
- GET /api/v1/users (admin only)
- PATCH /api/v1/users/{id} (admin only)

**Estimated Time:** 6-8 hours

**Total Phase 1 Time:** 20-26 hours (2-3 days)

---

## Phase 2: Frontend Critical Path (Days 4-7)

### Day 4-5: CustomersPage Implementation
**Priority:** P1 - Highest Impact
**Rationale:** CRM backend is complete (100%), but customers can't be managed without UI

**Files to Create:**
```
frontend/src/pages/CustomersPage.tsx
frontend/src/components/customers/CustomerList.tsx
frontend/src/components/customers/CustomerForm.tsx
frontend/src/components/customers/CustomerCard.tsx
frontend/src/api/customers.ts (already exists from Phase 2.1, verify)
```

**Features:**
1. **Customer List View**
   - Table with columns: Name, Email, Phone, Type, Orders Count, Actions
   - Search by name/email/company
   - Filter by type (private/business)
   - Filter by active/inactive
   - Sort by name, created date
   - Pagination (20 per page)
   - "New Customer" button → opens form

2. **Customer Form (Create/Edit)**
   - Modal or side panel
   - Fields:
     - First Name*, Last Name*
     - Email* (with validation)
     - Phone, Mobile
     - Company Name (if business)
     - Customer Type (private/business toggle)
     - Street, City, Postal Code, Country
     - Notes (textarea)
     - Tags (multi-select chips)
   - Form validation (required fields, email format)
   - Save button → POST/PATCH API call
   - Cancel button → close form

3. **Customer Detail Card**
   - Display customer info
   - Edit button → open form
   - Deactivate button → soft delete
   - "View Orders" link → OrdersPage filtered by customer
   - Order history summary (count, total value)

**Technical Details:**
- Use React Hook Form for form management
- Use axios for API calls (from `api/customers.ts`)
- Use React Router for navigation
- Responsive design (mobile-friendly)
- Loading states & error handling
- Success/error toast notifications

**Estimated Time:** 12-16 hours

---

### Day 6-7: OrderDetailPage Extensions
**Priority:** P1 - High Impact
**Rationale:** Orders are displayed, but missing cost breakdown and metal inventory info

**Files to Modify:**
```
frontend/src/pages/OrderDetailPage.tsx
frontend/src/components/orders/CostBreakdown.tsx (new)
frontend/src/components/orders/MetalInventoryInfo.tsx (new)
```

**Features:**
1. **Cost Breakdown Component**
   - Display cost calculation:
     ```
     Material Cost:        €945.00  (21g × €45/g)
     Labor Cost:           €225.00  (3h × €75/h)
     ─────────────────────────────
     Subtotal:             €1,170.00
     Profit Margin (40%):  €468.00
     ─────────────────────────────
     Total before VAT:     €1,638.00
     VAT (19%):            €311.22
     ═════════════════════════════
     Final Price:          €1,949.22
     ```
   - Show manual overrides (if any)
   - Edit button → open cost edit form

2. **Metal Inventory Info Component**
   - Display metal used:
     - Metal Type: Gold 18K
     - Weight: 20g (+ 5% scrap = 21g)
     - Costing Method: FIFO
     - Batch(es) Used: #123 (21g @ €45/g)
   - Link to metal inventory page

3. **Order Detail Improvements**
   - Add "Costs" tab (after "Details", "Materials")
   - Add "Metal" tab (if order has metal_type)
   - Display customer info prominently
   - Link to customer detail page
   - Display deadline with calendar icon
   - Status badge with colors (NEW=blue, IN_PROGRESS=yellow, COMPLETED=green, DELIVERED=gray)

**Estimated Time:** 8-12 hours

**Total Phase 2 Time:** 20-28 hours (3-4 days)

---

## Phase 3: Integration & Validation (Day 8)

### Testing & Quality Assurance
1. **Run Full Test Suite**
   ```bash
   poetry run pytest tests/ -v --cov=src/goldsmith_erp --cov-report=html
   ```
   - Target: 80%+ coverage
   - Fix any failing tests
   - Add missing tests for edge cases

2. **Frontend Manual Testing**
   - Test all customer CRUD operations
   - Test order cost breakdown display
   - Test metal inventory info display
   - Test navigation between pages
   - Test responsive design (mobile, tablet, desktop)
   - Test error handling (network errors, validation errors)

3. **Integration Testing**
   - Test full workflow: Create Customer → Create Order → Add Metal → View Cost Breakdown
   - Test permissions (USER vs ADMIN)
   - Test data persistence (reload page, data still there)

**Estimated Time:** 6-8 hours

---

## Success Criteria

### Phase 1 Complete When:
- [ ] Customer Service has 15+ unit tests
- [ ] Order Service has 20+ unit tests
- [ ] Auth/User Service has 15+ unit tests
- [ ] All tests pass
- [ ] Coverage report shows 60%+ overall coverage

### Phase 2 Complete When:
- [ ] CustomersPage is functional (list, create, edit, search, filter)
- [ ] Customer form validates input correctly
- [ ] OrderDetailPage shows cost breakdown
- [ ] OrderDetailPage shows metal inventory info
- [ ] Navigation works between pages
- [ ] No console errors in browser

### Overall Success:
- [ ] Test coverage: 80%+ for critical services
- [ ] Frontend: Users can manage customers without technical knowledge
- [ ] Backend: All critical paths tested and validated
- [ ] System: Ready for beta testing with real users

---

## Timeline Summary

| Day | Focus | Deliverables | Hours |
|-----|-------|--------------|-------|
| 1 | Customer Service Tests | test_customer_service.py, integration tests | 6-8h |
| 2 | Order Service Tests | test_order_service.py, integration tests | 8-10h |
| 3 | Auth/User Service Tests | test_auth_service.py, test_user_service.py | 6-8h |
| 4-5 | CustomersPage Frontend | Full customer management UI | 12-16h |
| 6-7 | OrderDetailPage Extensions | Cost breakdown, metal info | 8-12h |
| 8 | Integration & QA | Full testing, bug fixes | 6-8h |

**Total Estimated Time:** 46-62 hours (6-8 days)

---

## Next Immediate Action

**START NOW:** Customer Service Tests

```bash
# 1. Create test file
touch tests/unit/test_customer_service.py

# 2. Run tests to verify setup
poetry run pytest tests/unit/test_customer_service.py -v

# 3. Iterate: Write test → Run → Fix → Repeat
```

**Expected Output:** Comprehensive test coverage for customer management, ensuring CRM backend is production-ready.

---

## Future Phases (After Current Sprint)

**Phase 4: Time-Tracking Frontend** (Backend complete, UI missing)
**Phase 5: Calendar System** (Capacity planning, deadline visualization)
**Phase 6: Reporting & Analytics** (Sales reports, time analysis)
**Phase 7: Payment Tracking** (Anzahlung, Restzahlung, Mahnwesen)

---

**Let's start with Customer Service Tests!** 🚀
