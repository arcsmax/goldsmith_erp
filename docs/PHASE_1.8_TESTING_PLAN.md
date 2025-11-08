# Phase 1.8 - Order Management Testing Plan

**Document Version**: 1.0
**Date**: 2025-11-06
**Status**: Ready for Implementation

## Overview

This document outlines comprehensive testing requirements for Phase 1.8 Order Management System. All tests must pass before deployment to ensure system reliability and data integrity.

---

## Table of Contents

1. [Test Environment Setup](#test-environment-setup)
2. [Database Layer Tests](#database-layer-tests)
3. [Repository Layer Tests](#repository-layer-tests)
4. [Service Layer Tests](#service-layer-tests)
5. [API Layer Tests](#api-layer-tests)
6. [Integration Tests](#integration-tests)
7. [Business Logic Tests](#business-logic-tests)
8. [Performance Tests](#performance-tests)
9. [Test Data](#test-data)
10. [Testing Checklist](#testing-checklist)

---

## Test Environment Setup

### Prerequisites
```bash
# Install test dependencies
poetry add --group dev pytest pytest-asyncio pytest-cov httpx

# Set up test database
export DATABASE_URL=postgresql://test_user:test_pass@localhost:5432/goldsmith_erp_test

# Run migrations
poetry run alembic upgrade head
```

### Test Configuration
```python
# tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from goldsmith_erp.db.models import Base

@pytest.fixture
async def test_db():
    """Create test database and clean up after tests"""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

---

## Database Layer Tests

### Migration Tests

#### Test 003_order_management Migration

**Test**: Migration applies successfully
```bash
alembic upgrade head
```

**Expected**:
- ✅ OrderItem table created
- ✅ OrderStatusHistory table created
- ✅ Order table enhanced with new columns
- ✅ All indexes created
- ✅ Foreign keys established
- ✅ No SQL errors

**Test**: Migration rollback works
```bash
alembic downgrade -1
```

**Expected**:
- ✅ All changes reverted
- ✅ Data preserved where possible
- ✅ No orphaned records

#### Test Model Definitions

**Test**: Order model attributes
```python
def test_order_model_attributes():
    """Verify Order model has all required attributes"""
    assert hasattr(Order, 'order_number')
    assert hasattr(Order, 'customer_id')
    assert hasattr(Order, 'order_type')
    assert hasattr(Order, 'status')
    assert hasattr(Order, 'priority')
    assert hasattr(Order, 'material_cost')
    assert hasattr(Order, 'labor_cost')
    assert hasattr(Order, 'total_cost')
    assert hasattr(Order, 'customer_price')
    assert hasattr(Order, 'margin')
```

**Test**: OrderItem model relationships
```python
def test_order_item_relationships():
    """Verify OrderItem relationships work"""
    # Create order item
    # Verify order relationship loads
    # Verify material relationship loads
```

**Test**: OrderStatusHistory cascade delete
```python
def test_status_history_cascade():
    """Verify status history is deleted when order is deleted"""
    # Create order with status history
    # Delete order
    # Verify status history entries are also deleted
```

---

## Repository Layer Tests

### OrderRepository Tests

#### CRUD Operations

**Test**: `create_order` generates unique order number
```python
async def test_create_order_generates_unique_number(repository):
    """Test order number generation (ORD-YYYYMM-XXXX)"""
    order1 = await repository.create_order(customer_id=1, title="Order 1")
    order2 = await repository.create_order(customer_id=1, title="Order 2")

    assert order1.order_number.startswith("ORD-")
    assert order2.order_number.startswith("ORD-")
    assert order1.order_number != order2.order_number
```

**Expected**: Order numbers increment (ORD-202511-0001, ORD-202511-0002, ...)

**Test**: `get_by_id_with_items` loads relationships
```python
async def test_get_by_id_with_items_loads_relationships(repository):
    """Test that relationships are eagerly loaded"""
    order_id = 1  # Pre-created order with items
    order = await repository.get_by_id_with_items(order_id)

    assert order.order_items is not None
    assert len(order.order_items) > 0
    assert order.status_history is not None
    assert order.customer is not None
```

**Expected**: All relationships loaded without additional queries

**Test**: `list_orders` filtering works
```python
async def test_list_orders_filtering(repository):
    """Test order listing with various filters"""
    # Filter by status
    draft_orders = await repository.list_orders(status="draft")
    assert all(o.status == "draft" for o in draft_orders)

    # Filter by priority
    urgent_orders = await repository.list_orders(priority="urgent")
    assert all(o.priority == "urgent" for o in urgent_orders)

    # Filter by customer
    customer_orders = await repository.list_orders(customer_id=1)
    assert all(o.customer_id == 1 for o in customer_orders)
```

**Expected**: Filters applied correctly, results match criteria

**Test**: `soft_delete_order` doesn't hard delete
```python
async def test_soft_delete_preserves_record(repository):
    """Test that soft delete sets is_deleted flag"""
    order = await repository.create_order(customer_id=1, title="Test")
    await repository.soft_delete_order(order.id)

    # Should not find by default
    found = await repository.get_by_id(order.id)
    assert found is None

    # Should find with include_deleted=True
    found_deleted = await repository.get_by_id(order.id, include_deleted=True)
    assert found_deleted is not None
    assert found_deleted.is_deleted is True
```

**Expected**: Record marked as deleted, not removed from database

#### OrderItem Operations

**Test**: `add_order_item` recalculates costs
```python
async def test_add_order_item_recalculates_costs(repository):
    """Test that adding items triggers cost recalculation"""
    order = await repository.create_order(
        customer_id=1,
        title="Test",
        customer_price=1000.0
    )

    initial_material_cost = order.material_cost

    await repository.add_order_item(
        order_id=order.id,
        material_id=1,
        quantity_planned=10.0,
        unit="g",
        unit_price=5.0
    )

    # Mark as used to trigger cost calculation
    # ... (set quantity_used and recalculate)

    updated_order = await repository.get_by_id(order.id)
    assert updated_order.material_cost > initial_material_cost
```

**Expected**: Material costs updated automatically

**Test**: `allocate_material` sets timestamps
```python
async def test_allocate_material_sets_timestamp(repository):
    """Test material allocation tracking"""
    item_id = 1  # Pre-created order item

    allocated_item = await repository.allocate_material(item_id)

    assert allocated_item.is_allocated is True
    assert allocated_item.allocated_at is not None
```

**Expected**: Allocation status and timestamp recorded

**Test**: `mark_material_used` calculates cost
```python
async def test_mark_material_used_calculates_cost(repository):
    """Test that marking material as used calculates total cost"""
    item_id = 1  # Order item with unit_price=10.0

    used_item = await repository.mark_material_used(
        order_item_id=item_id,
        quantity_used=5.0
    )

    assert used_item.quantity_used == 5.0
    assert used_item.is_used is True
    assert used_item.total_cost == 50.0  # 5.0 * 10.0
    assert used_item.used_at is not None
```

**Expected**: Total cost = quantity_used * unit_price

#### Status History Operations

**Test**: `change_order_status` creates history entry
```python
async def test_change_order_status_creates_history(repository):
    """Test that status changes are recorded"""
    order = await repository.create_order(customer_id=1, title="Test")

    await repository.change_order_status(
        order_id=order.id,
        new_status="approved",
        reason="Customer approved"
    )

    order_with_history = await repository.get_by_id_with_items(order.id)

    assert len(order_with_history.status_history) >= 2  # draft + approved
    last_history = order_with_history.status_history[-1]
    assert last_history.old_status == "draft"
    assert last_history.new_status == "approved"
    assert last_history.reason == "Customer approved"
```

**Expected**: Status history entry created with old/new status

**Test**: Status change updates date fields
```python
async def test_status_change_updates_dates(repository):
    """Test that status transitions update relevant date fields"""
    order = await repository.create_order(customer_id=1, title="Test")

    # Draft → Approved
    await repository.change_order_status(order.id, "approved")

    # Approved → In Progress
    await repository.change_order_status(order.id, "in_progress")
    order = await repository.get_by_id(order.id)
    assert order.started_at is not None

    # In Progress → Completed
    await repository.change_order_status(order.id, "completed")
    order = await repository.get_by_id(order.id)
    assert order.completed_at is not None
    assert order.actual_completion_date is not None
```

**Expected**: Date fields populated on status transitions

#### Cost Calculation Tests

**Test**: `_recalculate_order_costs` computes correctly
```python
async def test_cost_calculation(repository):
    """Test comprehensive cost calculation"""
    order = await repository.create_order(
        customer_id=1,
        title="Test",
        estimated_hours=10.0,
        hourly_rate=50.0,
        customer_price=1000.0,
        tax_rate=19.0
    )

    # Add material (will be used)
    item = await repository.add_order_item(
        order_id=order.id,
        material_id=1,
        quantity_planned=10.0,
        unit="g",
        unit_price=5.0
    )

    # Mark as used
    await repository.mark_material_used(item.id, quantity_used=10.0)

    # Get updated order
    order = await repository.get_by_id(order.id)

    # Verify calculations
    assert order.material_cost == 50.0  # 10g * 5.0
    assert order.labor_cost == 500.0  # 10h * 50.0
    assert order.total_cost == 550.0  # material + labor
    assert order.margin == 450.0  # 1000 - 550
    assert order.tax_amount == 190.0  # 1000 * 0.19
    assert order.total_amount == 1190.0  # 1000 + 190
```

**Expected**: All cost fields calculated correctly

#### Statistics Tests

**Test**: `get_order_statistics` returns correct data
```python
async def test_order_statistics(repository):
    """Test statistics calculation"""
    # Create test orders in various statuses
    # ...

    stats = await repository.get_order_statistics()

    assert isinstance(stats['total_orders'], int)
    assert isinstance(stats['draft_orders'], int)
    assert isinstance(stats['total_revenue'], float)
    assert isinstance(stats['average_margin'], float)
```

**Expected**: Statistics match actual database state

---

## Service Layer Tests

### OrderService Tests

#### Validation Tests

**Test**: `create_order` validates order type
```python
async def test_create_order_invalid_type_raises_error(service):
    """Test that invalid order type is rejected"""
    with pytest.raises(HTTPException) as exc:
        await service.create_order(
            customer_id=1,
            title="Test",
            order_type="invalid_type"
        )

    assert exc.value.status_code == 400
    assert "Invalid order type" in exc.value.detail
```

**Expected**: HTTPException with 400 status

**Test**: `create_order` validates dates not in past
```python
async def test_create_order_rejects_past_dates(service):
    """Test that past dates are rejected"""
    past_date = datetime.utcnow() - timedelta(days=1)

    with pytest.raises(HTTPException) as exc:
        await service.create_order(
            customer_id=1,
            title="Test",
            estimated_completion_date=past_date
        )

    assert exc.value.status_code == 400
    assert "cannot be in the past" in exc.value.detail
```

**Expected**: HTTPException with validation error

**Test**: `create_order` validates numeric constraints
```python
async def test_create_order_validates_numbers(service):
    """Test numeric validation"""
    # Negative price
    with pytest.raises(HTTPException):
        await service.create_order(
            customer_id=1,
            title="Test",
            customer_price=-100.0
        )

    # Zero estimated hours
    with pytest.raises(HTTPException):
        await service.create_order(
            customer_id=1,
            title="Test",
            estimated_hours=0.0
        )

    # Invalid tax rate
    with pytest.raises(HTTPException):
        await service.create_order(
            customer_id=1,
            title="Test",
            tax_rate=150.0  # > 100%
        )
```

**Expected**: All invalid inputs rejected

#### Status Workflow Tests

**Test**: Status transitions follow state machine
```python
async def test_status_transitions_enforce_workflow(service):
    """Test that invalid transitions are blocked"""
    order = await service.create_order(customer_id=1, title="Test")

    # Valid: draft → approved
    await service.change_order_status(order.id, "approved")

    # Invalid: approved → delivered (must go through in_progress, completed)
    with pytest.raises(HTTPException) as exc:
        await service.change_order_status(order.id, "delivered")

    assert exc.value.status_code == 400
    assert "Invalid status transition" in exc.value.detail
```

**Expected**: Invalid transitions blocked with clear error

**Test**: Cannot start order without allocated materials
```python
async def test_cannot_start_without_allocated_materials(service):
    """Test prerequisite validation for in_progress status"""
    order = await service.create_order(customer_id=1, title="Test")
    await service.change_order_status(order.id, "approved")

    # Add material but don't allocate
    await service.add_order_item(
        order_id=order.id,
        material_id=1,
        quantity_planned=10.0,
        unit="g",
        unit_price=5.0
    )

    # Try to start order
    with pytest.raises(HTTPException) as exc:
        await service.change_order_status(order.id, "in_progress")

    assert "not all materials are allocated" in exc.value.detail
```

**Expected**: Status change blocked until materials allocated

**Test**: Cannot complete order without used materials
```python
async def test_cannot_complete_without_used_materials(service):
    """Test prerequisite validation for completed status"""
    # ... Create order, approve, allocate materials, start

    # Try to complete without marking materials as used
    with pytest.raises(HTTPException) as exc:
        await service.change_order_status(order.id, "completed")

    assert "not all materials are marked as used" in exc.value.detail
```

**Expected**: Status change blocked until materials marked as used

#### Business Logic Tests

**Test**: Cannot add materials to in-progress order
```python
async def test_cannot_add_materials_to_started_order(service):
    """Test that materials can only be added to draft/approved orders"""
    order = await service.create_order(customer_id=1, title="Test")
    await service.change_order_status(order.id, "approved")
    await service.change_order_status(order.id, "in_progress")

    with pytest.raises(HTTPException) as exc:
        await service.add_order_item(
            order_id=order.id,
            material_id=1,
            quantity_planned=10.0,
            unit="g",
            unit_price=5.0
        )

    assert exc.value.status_code == 400
    assert "Cannot add materials to order in 'in_progress' status" in exc.value.detail
```

**Expected**: Material addition blocked for in-progress orders

**Test**: Cannot delete delivered orders
```python
async def test_cannot_delete_delivered_order(service):
    """Test protection of delivered orders"""
    # ... Create and deliver order

    with pytest.raises(HTTPException) as exc:
        await service.delete_order(order.id)

    assert exc.value.status_code == 400
    assert "Cannot delete delivered orders" in exc.value.detail
```

**Expected**: Delivered orders protected from deletion

---

## API Layer Tests

### API Endpoint Tests

#### Test GET /orders

**Test**: List orders with pagination
```python
async def test_list_orders_pagination(client):
    """Test order listing with pagination"""
    response = await client.get("/api/v1/orders?skip=0&limit=10")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "has_more" in data
    assert len(data["items"]) <= 10
```

**Expected**: Paginated response with correct structure

**Test**: List orders with filters
```python
async def test_list_orders_with_filters(client):
    """Test filtering orders"""
    response = await client.get("/api/v1/orders?status=draft&priority=urgent")

    assert response.status_code == 200
    data = response.json()
    for order in data["items"]:
        assert order["status"] == "draft"
        assert order["priority"] == "urgent"
```

**Expected**: Only orders matching filters returned

#### Test POST /orders

**Test**: Create order with validation
```python
async def test_create_order_success(client):
    """Test successful order creation"""
    order_data = {
        "customer_id": 1,
        "title": "Custom Gold Ring",
        "order_type": "custom_jewelry",
        "priority": "normal",
        "customer_price": 1500.0
    }

    response = await client.post("/api/v1/orders", json=order_data)

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Custom Gold Ring"
    assert data["order_number"].startswith("ORD-")
    assert data["status"] == "draft"
```

**Expected**: Order created with auto-generated order_number

**Test**: Create order validation errors
```python
async def test_create_order_validation_errors(client):
    """Test validation error responses"""
    invalid_data = {
        "customer_id": 1,
        "title": "Test",
        "order_type": "invalid",  # Invalid
        "customer_price": -100.0  # Negative
    }

    response = await client.post("/api/v1/orders", json=invalid_data)

    assert response.status_code == 400
```

**Expected**: 400 error with validation details

#### Test PUT /orders/{id}/status

**Test**: Change order status
```python
async def test_change_order_status(client):
    """Test status change endpoint"""
    # Create draft order
    order = await create_test_order(client)

    # Change to approved
    response = await client.put(
        f"/api/v1/orders/{order['id']}/status",
        json={"new_status": "approved", "reason": "Customer confirmed"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
```

**Expected**: Status updated, history entry created

---

## Integration Tests

### End-to-End Order Lifecycle

**Test**: Complete order workflow
```python
async def test_complete_order_workflow(client, repository, service):
    """Test full order lifecycle from draft to delivered"""

    # 1. Create order (draft)
    order = await service.create_order(
        customer_id=1,
        title="Custom Wedding Ring",
        order_type="custom_jewelry",
        priority="high",
        estimated_hours=20.0,
        hourly_rate=75.0,
        customer_price=2500.0
    )
    assert order.status == "draft"

    # 2. Add materials
    item1 = await service.add_order_item(
        order_id=order.id,
        material_id=1,  # Gold
        quantity_planned=15.0,
        unit="g",
        unit_price=60.0
    )

    # 3. Approve order
    order = await service.change_order_status(
        order.id,
        "approved",
        reason="Design approved by customer"
    )
    assert order.status == "approved"

    # 4. Allocate materials
    await service.allocate_material(item1.id)

    # 5. Start production
    order = await service.change_order_status(
        order.id,
        "in_progress",
        reason="Production started"
    )
    assert order.status == "in_progress"
    assert order.started_at is not None

    # 6. Mark materials as used
    await service.mark_material_used(
        order_item_id=item1.id,
        quantity_used=14.5  # Actual usage
    )

    # 7. Complete order
    order = await service.change_order_status(
        order.id,
        "completed",
        reason="Finished production"
    )
    assert order.status == "completed"
    assert order.completed_at is not None

    # 8. Deliver to customer
    order = await service.change_order_status(
        order.id,
        "delivered",
        reason="Customer picked up"
    )
    assert order.status == "delivered"
    assert order.delivered_at is not None

    # 9. Verify cost calculations
    order_full = await repository.get_by_id_with_items(order.id)
    assert order_full.material_cost == 870.0  # 14.5g * 60.0
    assert order_full.labor_cost == 1500.0  # 20h * 75.0
    assert order_full.total_cost == 2370.0
    assert order_full.margin == 130.0  # 2500 - 2370

    # 10. Verify status history
    assert len(order_full.status_history) == 6
    statuses = [h.new_status for h in order_full.status_history]
    assert statuses == ["draft", "approved", "in_progress", "completed", "delivered"]
```

**Expected**: Complete workflow executes without errors, all calculations correct

---

## Performance Tests

### Load Tests

**Test**: Create 1000 orders
```python
async def test_bulk_order_creation(service):
    """Test system performance with bulk order creation"""
    import time

    start = time.time()

    for i in range(1000):
        await service.create_order(
            customer_id=1,
            title=f"Order {i}",
            customer_price=1000.0
        )

    duration = time.time() - start

    assert duration < 60.0  # Should complete in less than 60 seconds
    print(f"Created 1000 orders in {duration:.2f} seconds")
```

**Expected**: Acceptable performance (< 60s for 1000 orders)

**Test**: Query performance with large dataset
```python
async def test_query_performance(repository):
    """Test query performance with 10000 orders"""
    # ... Create 10000 test orders

    import time
    start = time.time()

    orders = await repository.list_orders(
        status="in_progress",
        limit=100
    )

    duration = time.time() - start

    assert duration < 1.0  # Should complete in less than 1 second
```

**Expected**: Queries remain fast even with large datasets

---

## Test Data

### Required Test Data

#### Users
```python
test_users = [
    {"id": 1, "email": "admin@example.com", "role": "admin"},
    {"id": 2, "email": "goldsmith@example.com", "role": "goldsmith"},
]
```

#### Customers
```python
test_customers = [
    {"id": 1, "customer_number": "CUST-202511-0001", "first_name": "Max", "last_name": "Mustermann"},
    {"id": 2, "customer_number": "CUST-202511-0002", "first_name": "Erika", "last_name": "Musterfrau"},
]
```

#### Materials
```python
test_materials = [
    {"id": 1, "name": "Gold 585", "unit_price": 60.0, "unit": "g", "stock": 1000.0},
    {"id": 2, "name": "Silver 925", "unit_price": 0.80, "unit": "g", "stock": 5000.0},
    {"id": 3, "name": "Diamond 0.5ct", "unit_price": 500.0, "unit": "pcs", "stock": 20.0},
]
```

---

## Testing Checklist

### Pre-Deployment Testing

- [ ] All migration tests pass
- [ ] All repository tests pass (100% coverage)
- [ ] All service tests pass (100% coverage)
- [ ] All API endpoint tests pass
- [ ] Integration tests pass
- [ ] Performance tests meet benchmarks
- [ ] Manual testing completed
- [ ] Edge cases tested
- [ ] Error handling verified
- [ ] Validation rules confirmed

### Test Coverage Requirements

| Layer | Min Coverage | Current |
|-------|-------------|---------|
| Models | 90% | - |
| Repository | 95% | - |
| Service | 95% | - |
| API | 90% | - |
| **Overall** | **90%** | - |

### Run All Tests
```bash
# Run full test suite
poetry run pytest tests/ -v --cov=goldsmith_erp --cov-report=html

# Run specific test categories
poetry run pytest tests/test_repository.py -v
poetry run pytest tests/test_service.py -v
poetry run pytest tests/test_api.py -v

# Run integration tests
poetry run pytest tests/test_integration.py -v

# Run performance tests
poetry run pytest tests/test_performance.py -v
```

---

## Test Execution Results

### Expected Test Output
```
tests/test_repository.py::test_create_order_generates_unique_number PASSED
tests/test_repository.py::test_get_by_id_with_items_loads_relationships PASSED
tests/test_repository.py::test_list_orders_filtering PASSED
tests/test_repository.py::test_soft_delete_preserves_record PASSED
...
tests/test_service.py::test_create_order_invalid_type_raises_error PASSED
tests/test_service.py::test_status_transitions_enforce_workflow PASSED
...
tests/test_integration.py::test_complete_order_workflow PASSED

========== 127 passed in 12.34s ==========

Coverage Report:
goldsmith_erp/db/repositories/order.py    809    12    98%
goldsmith_erp/services/order_service.py   825    15    98%
goldsmith_erp/models/order.py             435     0   100%
---------------------------------------------------------
TOTAL                                    2069    27    98%
```

---

## Continuous Integration

### GitHub Actions Workflow
```yaml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: goldsmith_erp_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      - name: Run migrations
        run: poetry run alembic upgrade head
      - name: Run tests
        run: poetry run pytest tests/ -v --cov=goldsmith_erp --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Conclusion

This comprehensive testing plan ensures that Phase 1.8 Order Management System is thoroughly tested before deployment. All tests must pass with minimum 90% coverage before considering the phase complete.

**Next Steps**:
1. Implement all repository tests
2. Implement all service tests
3. Create API endpoint tests
4. Run full integration tests
5. Performance benchmark
6. Document any deviations or issues

**Test Execution Owner**: Development Team
**Review Required**: Tech Lead, QA Team
**Estimated Testing Time**: 2-3 days
