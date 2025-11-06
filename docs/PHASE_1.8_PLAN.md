# Phase 1.8 Plan: Order & Project Management

**Status**: 📋 Planning
**Estimated Duration**: 3-4 weeks
**Priority**: High
**Dependencies**: Phase 1.5 (Materials), Phase 1.7 (Customers)

---

## Executive Summary

Phase 1.8 will implement **Order and Project Management** for the goldsmith workshop, enabling tracking of custom jewelry orders from initial request through completion and delivery. This phase connects customers with materials, creating a complete workflow for the business.

---

## Business Requirements

### Goldsmith Workshop Workflow

1. **Customer requests custom jewelry** (ring, necklace, bracelet, etc.)
2. **Goldsmith creates order/project** with specifications
3. **Materials are allocated** from inventory
4. **Work is performed** (multiple stages)
5. **Order is completed** and delivered
6. **Materials are accounted for** (stock deducted)
7. **Payment is recorded**

### Key Business Needs

- Track what's being made for which customer
- Know which materials are used in each order
- See order status at a glance
- Calculate costs (materials + labor)
- Track time spent on each project
- Generate invoices
- Maintain order history for customers

---

## Phase 1.8 Scope

### Week 1: Backend Foundation
- Database models (Order, OrderItem, OrderStatusHistory)
- Order repository with CRUD operations
- Order service with business logic
- Material allocation/deallocation
- API endpoints for orders

### Week 2: Order Status & Workflow
- Order status management (draft → in_progress → completed → delivered)
- Status history tracking
- Material usage tracking
- Labor time tracking
- Order calculations (cost, margin, total)

### Week 3: Frontend Implementation
- Order list view with filters
- Order detail view with timeline
- Order creation form
- Order status updates
- Material allocation UI

---

## Database Schema

### Order Model

```python
class Order(Base):
    __tablename__ = "orders"

    # Primary Key
    id: int
    order_number: str  # ORD-YYYYMM-XXXX

    # Customer Relationship
    customer_id: int  # FK to customers

    # Order Information
    title: str  # "Custom Gold Ring", "Silver Necklace Repair"
    description: str  # Detailed specifications
    order_type: str  # "custom_jewelry", "repair", "modification"

    # Status
    status: str  # "draft", "approved", "in_progress", "completed", "delivered", "cancelled"
    priority: str  # "low", "normal", "high", "urgent"

    # Dates
    order_date: datetime
    estimated_completion_date: datetime (optional)
    actual_completion_date: datetime (optional)
    delivery_date: datetime (optional)

    # Financial
    material_cost: Decimal  # Sum of materials used
    labor_cost: Decimal  # Labor charges
    additional_cost: Decimal  # Other costs
    total_cost: Decimal  # material + labor + additional
    customer_price: Decimal  # Price quoted to customer
    margin: Decimal  # customer_price - total_cost
    currency: str = "EUR"

    # Labor Tracking
    estimated_hours: float (optional)
    actual_hours: float (optional)
    hourly_rate: Decimal (optional)

    # Additional
    notes: str (optional)  # Internal notes
    customer_notes: str (optional)  # Customer-facing notes
    attachments: JSON (optional)  # List of file paths/URLs

    # Audit
    created_at: datetime
    created_by: int  # FK to users
    updated_at: datetime (optional)
    updated_by: int (optional)

    # Relationships
    customer: Customer
    order_items: List[OrderItem]
    status_history: List[OrderStatusHistory]
```

### OrderItem Model (Materials Used)

```python
class OrderItem(Base):
    __tablename__ = "order_items"

    id: int
    order_id: int  # FK to orders

    # Material Relationship
    material_id: int  # FK to materials

    # Quantities
    quantity_planned: Decimal  # How much we plan to use
    quantity_used: Decimal  # How much we actually used
    unit: str  # From material

    # Costs (snapshot at time of order)
    unit_price: Decimal  # Price per unit at time of order
    total_cost: Decimal  # quantity_used * unit_price

    # Status
    is_allocated: bool  # Has stock been allocated?
    is_used: bool  # Has material been used/removed from stock?

    # Timestamps
    allocated_at: datetime (optional)
    used_at: datetime (optional)

    # Relationships
    order: Order
    material: Material
```

### OrderStatusHistory Model

```python
class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: int
    order_id: int  # FK to orders

    # Status Change
    old_status: str (optional)  # Previous status
    new_status: str  # New status

    # Change Information
    changed_at: datetime
    changed_by: int  # FK to users
    reason: str (optional)  # Why was status changed?
    notes: str (optional)  # Additional notes

    # Relationships
    order: Order
```

---

## API Endpoints

### Order CRUD

```
GET    /api/v1/orders                      # List orders
GET    /api/v1/orders/search               # Search orders
GET    /api/v1/orders/statistics           # Get order statistics
GET    /api/v1/orders/{id}                 # Get order details
POST   /api/v1/orders                      # Create order
PUT    /api/v1/orders/{id}                 # Update order
DELETE /api/v1/orders/{id}                 # Delete order (soft delete)
```

### Order Status Management

```
POST   /api/v1/orders/{id}/status          # Update order status
GET    /api/v1/orders/{id}/status-history  # Get status history
POST   /api/v1/orders/{id}/start           # Start working on order
POST   /api/v1/orders/{id}/complete        # Mark order as completed
POST   /api/v1/orders/{id}/deliver         # Mark as delivered
POST   /api/v1/orders/{id}/cancel          # Cancel order
```

### Material Allocation

```
POST   /api/v1/orders/{id}/materials       # Add material to order
DELETE /api/v1/orders/{id}/materials/{item_id}  # Remove material
POST   /api/v1/orders/{id}/allocate        # Allocate all materials
POST   /api/v1/orders/{id}/use-materials   # Mark materials as used (deduct stock)
```

### Labor Tracking

```
POST   /api/v1/orders/{id}/time            # Log time spent
GET    /api/v1/orders/{id}/time            # Get time logs
```

### Customer-Specific

```
GET    /api/v1/customers/{id}/orders       # Get customer's orders
GET    /api/v1/customers/{id}/order-history # Get complete order history
```

---

## Frontend Components

### 1. Order List (`OrderList.tsx`)

**Features**:
- Paginated list of orders
- Search by order number, customer name, title
- Filters: status, priority, date range, customer
- Sort by date, priority, status
- Status badges (color-coded)
- Quick actions (view, edit, update status)

**View Options**:
- **Card View**: Large cards with key info
- **Table View**: Compact table for many orders
- **Kanban Board**: Drag-and-drop between statuses

### 2. Order Detail (`OrderDetail.tsx`)

**Sections**:
- **Order Header**: Number, customer, status, dates
- **Specifications**: Title, description, type, priority
- **Materials**: List of materials used with quantities
- **Financial**: Cost breakdown, margin, customer price
- **Labor**: Time tracking, hours logged
- **Status Timeline**: Visual timeline of status changes
- **Notes**: Internal and customer-facing notes
- **Actions**: Edit, change status, allocate materials, etc.

### 3. Order Form (`OrderForm.tsx`)

**Sections**:
- **Customer Selection**: Dropdown with search
- **Order Details**: Title, description, type, priority
- **Material Selection**: Add materials with quantities
- **Financial**: Estimated costs, customer price
- **Timeline**: Estimated dates
- **Notes**: Internal and customer notes

**Smart Features**:
- Auto-calculate material costs
- Check material availability
- Suggest completion dates
- Calculate margin automatically

### 4. Order Status Board (`OrderStatusBoard.tsx`)

**Kanban-style Board**:
```
[Draft]  [Approved]  [In Progress]  [Completed]  [Delivered]
   3         5            8              2            12
```

**Features**:
- Drag-and-drop to change status
- Filter by customer, priority, date
- Quick view on hover
- Click to view details

### 5. Material Allocation Dialog (`MaterialAllocationDialog.tsx`)

**Features**:
- Add materials from inventory
- Check current stock levels
- Input planned quantities
- See cost impact
- Allocate or just plan

---

## Business Logic

### Order Status Workflow

```
Draft → Approved → In Progress → Completed → Delivered
   ↓       ↓            ↓            ↓
   Cancelled (can be cancelled from any status except Delivered)
```

**Status Descriptions**:
- **Draft**: Order created but not confirmed
- **Approved**: Customer approved, ready to start
- **In Progress**: Goldsmith is working on it
- **Completed**: Work finished, ready for delivery
- **Delivered**: Customer received the item
- **Cancelled**: Order was cancelled

### Material Allocation Logic

1. **Planning Phase**: Add materials without affecting stock
2. **Allocation Phase**: Reserve materials (mark as allocated)
3. **Usage Phase**: Deduct from stock when actually used

**Rules**:
- Can't allocate more than current stock
- Allocation warnings if stock low
- Can adjust quantities during work
- Final usage may differ from plan

### Cost Calculation

```python
material_cost = sum(item.quantity_used * item.unit_price for item in order_items)
labor_cost = actual_hours * hourly_rate
total_cost = material_cost + labor_cost + additional_cost
margin = customer_price - total_cost
margin_percentage = (margin / customer_price) * 100
```

---

## UI/UX Considerations

### Dashboard Integration

**Add to Dashboard**:
- **Active Orders Card**: Count of orders in progress
- **Pending Orders**: Orders waiting to start
- **Recent Orders**: Last 5 orders created/updated
- **Revenue This Month**: Sum of completed/delivered orders

### Order Status Colors

```css
Draft:        #9ca3af  (gray)
Approved:     #3b82f6  (blue)
In Progress:  #f59e0b  (amber)
Completed:    #10b981  (green)
Delivered:    #059669  (dark green)
Cancelled:    #dc2626  (red)
```

### Priority Indicators

```css
Low:      🟢 (green dot)
Normal:   🟡 (yellow dot)
High:     🟠 (orange dot)
Urgent:   🔴 (red dot + pulse animation)
```

---

## GDPR Compliance

### Data Processing

**Legal Basis**: Contract (GDPR Art. 6(1)(b))
- Orders are part of contract fulfillment
- No separate consent needed for order processing

**Data Retention**:
- **Active Orders**: Until delivered + warranty period
- **Completed Orders**: 10 years (German tax law: §147 AO)
- **Cancelled Orders**: 10 years (proof of cancellation)

**Data Subject Rights**:
- ✅ Right of Access: Include orders in customer data export
- ✅ Right to Erasure: Anonymize after retention period
- ✅ Right to Data Portability: Export orders with customer data

### Audit Trail

- Order creation logged
- Status changes logged with user and timestamp
- Material allocations logged
- All updates tracked in audit log

---

## Testing Strategy

### Backend Tests

```python
# test_order_repository.py
- test_create_order
- test_update_order
- test_get_order_with_items
- test_soft_delete_order
- test_filter_orders_by_status
- test_filter_orders_by_customer

# test_order_service.py
- test_calculate_order_costs
- test_allocate_materials
- test_use_materials_deducts_stock
- test_status_change_validation
- test_cannot_allocate_insufficient_stock

# test_order_api.py
- test_create_order_endpoint
- test_update_order_status
- test_get_customer_orders
- test_material_allocation_endpoint
```

### Frontend Tests

- Order list displays correctly
- Order form validation works
- Material allocation checks stock
- Status changes update UI
- Cost calculations are accurate

---

## Success Metrics

### Completion Criteria

- ✅ All database models created and migrated
- ✅ All API endpoints functional
- ✅ Order CRUD operations work
- ✅ Material allocation/usage works
- ✅ Status workflow functions correctly
- ✅ Frontend components complete
- ✅ Dashboard integration complete
- ✅ Tests passing (90%+ coverage)

### Performance Targets

- Order list loads in <2s
- Order creation completes in <1s
- Material allocation checks stock in <500ms
- Status updates in <500ms

---

## Implementation Order

### Week 1: Backend Foundation

**Day 1-2**: Database Models
- Create Order, OrderItem, OrderStatusHistory models
- Create migration scripts
- Add indexes for performance

**Day 3-4**: Repository Layer
- OrderRepository with CRUD operations
- Relationship loading (customer, materials)
- Filtering and pagination

**Day 5**: Service Layer
- OrderService with business logic
- Cost calculations
- Status validation
- Material allocation logic

### Week 2: Backend Completion

**Day 6-7**: API Endpoints
- Order CRUD endpoints
- Status management endpoints
- Material allocation endpoints
- Customer order history

**Day 8-9**: Testing
- Repository tests
- Service tests
- API tests
- Integration tests

**Day 10**: Documentation
- API documentation
- Service documentation
- Migration guide

### Week 3: Frontend Implementation

**Day 11-12**: Order List
- Table view with filters
- Search functionality
- Status badges
- Pagination

**Day 13-14**: Order Detail & Form
- Detail view with all sections
- Create/edit form
- Material selection
- Validation

**Day 15**: Dashboard Integration
- Add order statistics
- Recent orders section
- Active orders card
- Quick actions

---

## Risk Analysis

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Complex material allocation logic | High | Thorough testing, clear state management |
| Status workflow edge cases | Medium | Define clear rules, validate transitions |
| Performance with many orders | Medium | Pagination, indexing, caching |
| Stock deduction race conditions | High | Transaction locks, atomic operations |

### Business Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wrong cost calculations | High | Automated tests, manual verification |
| Material overbooking | High | Stock checks, allocation limits |
| Lost order data | Critical | Database backups, audit logging |

---

## Future Enhancements (Post Phase 1.8)

### Phase 1.9 Ideas

- **Advanced Features**:
  - Order templates for common items
  - Recurring orders
  - Bulk order operations
  - Order attachments (photos, CAD files)

- **Customer Portal**:
  - Customers can view their orders
  - Order status notifications
  - Delivery tracking

- **Analytics**:
  - Revenue reports
  - Material usage reports
  - Time tracking reports
  - Margin analysis

- **Integrations**:
  - Invoice generation (PDF)
  - Email notifications
  - Calendar integration
  - Accounting software integration

---

## Dependencies

### External

- **Python Packages**: No new dependencies needed
- **Database**: PostgreSQL (already in use)
- **Frontend**: React, TypeScript (already in use)

### Internal

- ✅ Phase 1.5: Material Management (stock tracking)
- ✅ Phase 1.7: Customer Management (customer data)
- ✅ Auth system (user tracking)
- ✅ Audit logging system (activity tracking)

---

## Conclusion

Phase 1.8 will complete the core business workflow for the goldsmith workshop by connecting customers and materials through an order management system. This enables full tracking from order receipt to delivery, with proper financial tracking and GDPR compliance.

**Key Deliverables**:
- 3 database models (Order, OrderItem, OrderStatusHistory)
- ~15 API endpoints
- 5 frontend components
- Material allocation and stock management
- Complete order lifecycle tracking
- Dashboard integration

**Estimated Completion**: 3-4 weeks
**Priority**: High (core business functionality)
**MVP Impact**: Increases MVP completion to ~70%

---

**Document Version**: 1.0
**Created**: 2025-11-06
**Author**: Claude AI
**Status**: 📋 Planning Phase
