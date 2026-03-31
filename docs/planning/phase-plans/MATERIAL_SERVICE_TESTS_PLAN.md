# MaterialService Unit Tests - Detailed Implementation Plan
**Created:** 2025-11-10
**Phase:** Day 3 of Phase 1
**Estimated Time:** 6-8 hours

---

## Objective

Create comprehensive unit and integration tests for MaterialService to bring test coverage from ~65% to ~70% and ensure material management is production-ready.

---

## Current MaterialService Analysis

### Service Location
`src/goldsmith_erp/services/material_service.py`

### Key Methods to Test (from reading the service file)
Based on standard CRUD patterns and the MaterialsPage implementation:
1. `create_material()` - Create new material
2. `get_material_by_id()` - Retrieve single material
3. `get_all_materials()` - List all materials with optional filters
4. `update_material()` - Update existing material
5. `delete_material()` - Delete material (soft or hard)
6. `search_materials()` - Search by name/description
7. `get_low_stock_materials()` - Filter by stock threshold

---

## Test File Structure

### File: `tests/unit/test_material_service.py`

**Total Test Count Target:** 25-30 tests

### Test Categories:

1. **Material Creation Tests** (6 tests)
2. **Material Retrieval Tests** (5 tests)
3. **Material Update Tests** (6 tests)
4. **Material Search & Filter Tests** (4 tests)
5. **Material Deletion Tests** (4 tests)
6. **Stock Calculation Tests** (3 tests)

---

## Detailed Test Specifications

### Category 1: Material Creation Tests (6 tests)

#### Test 1.1: `test_create_material_success`
**Purpose:** Verify successful material creation with all valid fields
```python
def test_create_material_success(db_session):
    # Arrange
    material_data = {
        "name": "Gold Ring Setting",
        "description": "18K gold ring setting for 1ct stone",
        "unit_price": 45.50,
        "stock": 25.5,
        "unit": "Stück"
    }

    # Act
    material = material_service.create_material(db_session, material_data)

    # Assert
    assert material.id is not None
    assert material.name == "Gold Ring Setting"
    assert material.unit_price == 45.50
    assert material.stock == 25.5
    assert material.created_at is not None
```

#### Test 1.2: `test_create_material_minimal_fields`
**Purpose:** Verify creation with only required fields
```python
def test_create_material_minimal_fields(db_session):
    material_data = {
        "name": "Simple Clasp",
        "unit_price": 2.50,
        "stock": 100,
        "unit": "Stück"
    }
    # description is optional, should be None
```

#### Test 1.3: `test_create_material_duplicate_name_allowed`
**Purpose:** Verify duplicate names are allowed (or rejected if uniqueness constraint exists)
```python
def test_create_material_duplicate_name(db_session):
    # Create first material
    # Attempt to create second with same name
    # Assert based on business logic (allowed or rejected)
```

#### Test 1.4: `test_create_material_negative_price_rejected`
**Purpose:** Verify negative prices are rejected
```python
def test_create_material_negative_price_rejected(db_session):
    material_data = {
        "name": "Invalid Material",
        "unit_price": -10.00,  # INVALID
        "stock": 10,
        "unit": "Stück"
    }

    with pytest.raises(ValueError, match="Price must be positive"):
        material_service.create_material(db_session, material_data)
```

#### Test 1.5: `test_create_material_negative_stock_rejected`
**Purpose:** Verify negative stock is rejected
```python
def test_create_material_negative_stock_rejected(db_session):
    material_data = {
        "name": "Invalid Material",
        "unit_price": 10.00,
        "stock": -5,  # INVALID
        "unit": "Stück"
    }

    with pytest.raises(ValueError, match="Stock cannot be negative"):
        material_service.create_material(db_session, material_data)
```

#### Test 1.6: `test_create_material_missing_required_fields`
**Purpose:** Verify required field validation
```python
def test_create_material_missing_required_fields(db_session):
    material_data = {
        "name": "Incomplete Material",
        # Missing: unit_price, stock, unit
    }

    with pytest.raises(ValueError):
        material_service.create_material(db_session, material_data)
```

---

### Category 2: Material Retrieval Tests (5 tests)

#### Test 2.1: `test_get_material_by_id_success`
**Purpose:** Verify retrieving existing material by ID
```python
def test_get_material_by_id_success(db_session, sample_material):
    material = material_service.get_material_by_id(db_session, sample_material.id)

    assert material is not None
    assert material.id == sample_material.id
    assert material.name == sample_material.name
```

#### Test 2.2: `test_get_material_by_id_not_found`
**Purpose:** Verify behavior when material doesn't exist
```python
def test_get_material_by_id_not_found(db_session):
    material = material_service.get_material_by_id(db_session, 99999)

    assert material is None
    # OR raises NotFoundException depending on implementation
```

#### Test 2.3: `test_get_all_materials_empty`
**Purpose:** Verify behavior with no materials in database
```python
def test_get_all_materials_empty(db_session):
    materials = material_service.get_all_materials(db_session)

    assert materials == []
    assert len(materials) == 0
```

#### Test 2.4: `test_get_all_materials_returns_all`
**Purpose:** Verify all materials are returned
```python
def test_get_all_materials_returns_all(db_session):
    # Create 5 materials
    for i in range(5):
        create_test_material(db_session, name=f"Material {i}")

    materials = material_service.get_all_materials(db_session)

    assert len(materials) == 5
```

#### Test 2.5: `test_get_all_materials_with_pagination`
**Purpose:** Verify pagination parameters work
```python
def test_get_all_materials_with_pagination(db_session):
    # Create 10 materials
    for i in range(10):
        create_test_material(db_session, name=f"Material {i}")

    # Get first page (limit 5)
    materials = material_service.get_all_materials(db_session, skip=0, limit=5)
    assert len(materials) == 5

    # Get second page
    materials = material_service.get_all_materials(db_session, skip=5, limit=5)
    assert len(materials) == 5
```

---

### Category 3: Material Update Tests (6 tests)

#### Test 3.1: `test_update_material_name`
**Purpose:** Verify name can be updated
```python
def test_update_material_name(db_session, sample_material):
    update_data = {"name": "Updated Material Name"}

    updated = material_service.update_material(db_session, sample_material.id, update_data)

    assert updated.name == "Updated Material Name"
    assert updated.id == sample_material.id  # ID unchanged
```

#### Test 3.2: `test_update_material_price`
**Purpose:** Verify price can be updated
```python
def test_update_material_price(db_session, sample_material):
    original_price = sample_material.unit_price
    update_data = {"unit_price": original_price + 10.00}

    updated = material_service.update_material(db_session, sample_material.id, update_data)

    assert updated.unit_price == original_price + 10.00
```

#### Test 3.3: `test_update_material_stock_adjustment`
**Purpose:** Verify stock can be adjusted (add/subtract)
```python
def test_update_material_stock_add(db_session, sample_material):
    original_stock = sample_material.stock

    # Add 10 units
    updated = material_service.adjust_stock(db_session, sample_material.id, quantity=10)

    assert updated.stock == original_stock + 10

def test_update_material_stock_subtract(db_session, sample_material):
    # Subtract 5 units
    updated = material_service.adjust_stock(db_session, sample_material.id, quantity=-5)

    assert updated.stock == original_stock - 5
```

#### Test 3.4: `test_update_material_prevent_negative_stock`
**Purpose:** Verify stock cannot go negative during adjustment
```python
def test_update_material_prevent_negative_stock(db_session, sample_material):
    # Material has stock of 10
    sample_material.stock = 10

    # Try to subtract 15 (would result in -5)
    with pytest.raises(ValueError, match="Insufficient stock"):
        material_service.adjust_stock(db_session, sample_material.id, quantity=-15)
```

#### Test 3.5: `test_update_material_multiple_fields`
**Purpose:** Verify multiple fields can be updated at once
```python
def test_update_material_multiple_fields(db_session, sample_material):
    update_data = {
        "name": "New Name",
        "description": "New Description",
        "unit_price": 99.99
    }

    updated = material_service.update_material(db_session, sample_material.id, update_data)

    assert updated.name == "New Name"
    assert updated.description == "New Description"
    assert updated.unit_price == 99.99
```

#### Test 3.6: `test_update_material_not_found`
**Purpose:** Verify error when updating non-existent material
```python
def test_update_material_not_found(db_session):
    update_data = {"name": "New Name"}

    with pytest.raises(NotFoundException):
        material_service.update_material(db_session, 99999, update_data)
```

---

### Category 4: Material Search & Filter Tests (4 tests)

#### Test 4.1: `test_search_materials_by_name`
**Purpose:** Verify search by name (partial match)
```python
def test_search_materials_by_name(db_session):
    # Create materials with different names
    create_test_material(db_session, name="Gold Ring")
    create_test_material(db_session, name="Silver Ring")
    create_test_material(db_session, name="Gold Necklace")

    # Search for "Gold"
    results = material_service.search_materials(db_session, query="Gold")

    assert len(results) == 2
    assert all("Gold" in m.name for m in results)
```

#### Test 4.2: `test_search_materials_by_description`
**Purpose:** Verify search by description
```python
def test_search_materials_by_description(db_session):
    create_test_material(db_session, name="Item 1", description="Premium quality")
    create_test_material(db_session, name="Item 2", description="Standard quality")

    results = material_service.search_materials(db_session, query="Premium")

    assert len(results) == 1
```

#### Test 4.3: `test_filter_materials_by_low_stock`
**Purpose:** Verify filtering by low stock threshold
```python
def test_filter_materials_by_low_stock(db_session):
    create_test_material(db_session, name="Low Stock Item", stock=5)
    create_test_material(db_session, name="Normal Stock Item", stock=50)
    create_test_material(db_session, name="High Stock Item", stock=500)

    # Filter for stock < 10
    low_stock = material_service.get_low_stock_materials(db_session, threshold=10)

    assert len(low_stock) == 1
    assert low_stock[0].name == "Low Stock Item"
```

#### Test 4.4: `test_search_materials_case_insensitive`
**Purpose:** Verify search is case-insensitive
```python
def test_search_materials_case_insensitive(db_session):
    create_test_material(db_session, name="GOLD RING")

    results = material_service.search_materials(db_session, query="gold")

    assert len(results) == 1
```

---

### Category 5: Material Deletion Tests (4 tests)

#### Test 5.1: `test_delete_material_success`
**Purpose:** Verify material can be deleted
```python
def test_delete_material_success(db_session, sample_material):
    material_id = sample_material.id

    material_service.delete_material(db_session, material_id)

    # Verify material is deleted
    deleted = material_service.get_material_by_id(db_session, material_id)
    assert deleted is None
```

#### Test 5.2: `test_delete_material_not_found`
**Purpose:** Verify error when deleting non-existent material
```python
def test_delete_material_not_found(db_session):
    with pytest.raises(NotFoundException):
        material_service.delete_material(db_session, 99999)
```

#### Test 5.3: `test_delete_material_used_in_orders_prevented`
**Purpose:** Verify material cannot be deleted if used in orders
```python
def test_delete_material_used_in_orders_prevented(db_session, sample_material, sample_order):
    # Associate material with order
    sample_order.materials.append(sample_material)
    db_session.commit()

    # Try to delete material
    with pytest.raises(ValueError, match="Material is used in orders"):
        material_service.delete_material(db_session, sample_material.id)
```

#### Test 5.4: `test_soft_delete_material`
**Purpose:** Verify soft delete sets is_active=False (if implemented)
```python
def test_soft_delete_material(db_session, sample_material):
    material_service.soft_delete_material(db_session, sample_material.id)

    material = material_service.get_material_by_id(db_session, sample_material.id)
    assert material.is_active == False
    # Material still exists in DB but marked inactive
```

---

### Category 6: Stock Calculation Tests (3 tests)

#### Test 6.1: `test_calculate_total_stock_value`
**Purpose:** Verify total stock value calculation
```python
def test_calculate_total_stock_value(db_session):
    create_test_material(db_session, unit_price=10.00, stock=5)   # 50.00
    create_test_material(db_session, unit_price=25.00, stock=10)  # 250.00

    total_value = material_service.calculate_total_stock_value(db_session)

    assert total_value == 300.00
```

#### Test 6.2: `test_calculate_stock_value_per_material`
**Purpose:** Verify individual material stock value
```python
def test_calculate_stock_value_per_material(db_session, sample_material):
    sample_material.unit_price = 15.00
    sample_material.stock = 20

    value = material_service.calculate_material_value(sample_material)

    assert value == 300.00
```

#### Test 6.3: `test_get_stock_statistics`
**Purpose:** Verify stock statistics calculation
```python
def test_get_stock_statistics(db_session):
    create_test_material(db_session, stock=5)
    create_test_material(db_session, stock=50)
    create_test_material(db_session, stock=100)

    stats = material_service.get_stock_statistics(db_session)

    assert stats["total_materials"] == 3
    assert stats["low_stock_count"] == 1  # stock < 10
    assert stats["average_stock"] == 51.67  # (5+50+100)/3
```

---

## Integration Tests

### File: `tests/integration/test_material_api.py`

**Total Test Count Target:** 10-12 tests

### Test Categories:

1. **POST /api/v1/materials** - Create material (2 tests)
2. **GET /api/v1/materials** - List materials (2 tests)
3. **GET /api/v1/materials/{id}** - Get single material (2 tests)
4. **PATCH /api/v1/materials/{id}** - Update material (2 tests)
5. **DELETE /api/v1/materials/{id}** - Delete material (2 tests)
6. **Permissions Testing** - USER vs ADMIN (2 tests)

### Example Integration Test:

```python
def test_create_material_api_success(client, auth_headers):
    # POST /api/v1/materials
    response = client.post(
        "/api/v1/materials",
        json={
            "name": "Test Material",
            "unit_price": 10.50,
            "stock": 25,
            "unit": "Stück"
        },
        headers=auth_headers
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Material"
    assert data["id"] is not None
```

---

## Fixtures Required

### Test Fixtures (in `conftest.py`)

```python
@pytest.fixture
def sample_material(db_session):
    """Create a sample material for testing"""
    material = Material(
        name="Test Material",
        description="Test Description",
        unit_price=15.50,
        stock=100,
        unit="Stück"
    )
    db_session.add(material)
    db_session.commit()
    db_session.refresh(material)
    return material

@pytest.fixture
def multiple_materials(db_session):
    """Create multiple materials for list/filter tests"""
    materials = []
    for i in range(5):
        material = Material(
            name=f"Material {i}",
            unit_price=10.00 + i,
            stock=50 - (i * 10),
            unit="Stück"
        )
        db_session.add(material)
        materials.append(material)
    db_session.commit()
    return materials
```

---

## Implementation Steps

### Step 1: Read MaterialService (10 min)
- Read `src/goldsmith_erp/services/material_service.py`
- Identify all methods
- Understand validation logic
- Note any special business rules

### Step 2: Create Test File Structure (15 min)
- Create `tests/unit/test_material_service.py`
- Add imports
- Add docstring
- Create test class structure

### Step 3: Implement Creation Tests (45 min)
- Write 6 creation tests
- Run tests, fix any issues
- Verify coverage

### Step 4: Implement Retrieval Tests (30 min)
- Write 5 retrieval tests
- Test pagination logic
- Verify edge cases

### Step 5: Implement Update Tests (60 min)
- Write 6 update tests
- Test stock adjustment logic
- Test validation

### Step 6: Implement Search Tests (30 min)
- Write 4 search/filter tests
- Test case sensitivity
- Test partial matches

### Step 7: Implement Deletion Tests (30 min)
- Write 4 deletion tests
- Test constraint violations
- Test soft delete (if applicable)

### Step 8: Implement Calculation Tests (30 min)
- Write 3 calculation tests
- Test value calculations
- Test statistics

### Step 9: Run Full Test Suite (15 min)
```bash
poetry run pytest tests/unit/test_material_service.py -v --cov=src/goldsmith_erp/services/material_service.py
```

### Step 10: Integration Tests (90 min)
- Create `tests/integration/test_material_api.py`
- Write 10-12 API endpoint tests
- Test permissions

### Step 11: Coverage Report (10 min)
```bash
poetry run pytest tests/ -v --cov=src/goldsmith_erp --cov-report=html
```
- Verify coverage increased to ~70%
- Identify any missed lines

### Step 12: Documentation (15 min)
- Add docstrings to all tests
- Update test coverage in README
- Document any findings

---

## Success Criteria

- [ ] 25-30 unit tests written and passing
- [ ] 10-12 integration tests written and passing
- [ ] All tests have clear docstrings
- [ ] Test coverage for MaterialService: 90%+
- [ ] Overall project test coverage: 70%+
- [ ] No flaky tests (all pass consistently)
- [ ] All edge cases covered
- [ ] Documentation updated

---

## Time Breakdown

| Task | Estimated Time |
|------|----------------|
| Read MaterialService code | 10 min |
| Set up test file structure | 15 min |
| Creation tests (6) | 45 min |
| Retrieval tests (5) | 30 min |
| Update tests (6) | 60 min |
| Search tests (4) | 30 min |
| Deletion tests (4) | 30 min |
| Calculation tests (3) | 30 min |
| Run & debug unit tests | 15 min |
| Integration tests (10-12) | 90 min |
| Coverage report & analysis | 10 min |
| Documentation | 15 min |
| **Total** | **6 hours** |

---

## Next Steps After Completion

Once MaterialService tests are complete:
1. Commit changes with detailed commit message
2. Push to remote branch
3. Move to **Day 4: MetalInventoryPage UI** (from implementation plan)
4. OR continue with **Day 3 Extension: TimeTrackingService Tests** if more test coverage is desired

---

**Ready to Start Implementation!** 🚀
