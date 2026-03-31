# TimeTrackingService Unit Tests Plan (Day 7)

## Overview
Write comprehensive unit tests for TimeTrackingService following existing patterns from test_material_service.py and pytest-asyncio best practices (2025).

**Target:** 20-25 unit tests, 75%+ code coverage
**Time Estimate:** 6-8 hours

---

## Test Categories & Coverage

### 1. Time Entry Creation (5 tests)
- `test_create_time_entry_success` - Full entry with all fields
- `test_create_time_entry_minimal_fields` - Only required fields
- `test_create_time_entry_with_end_time` - Completed entry (start + end)
- `test_create_time_entry_without_end_time` - Active entry (running)
- `test_create_time_entry_calculates_duration` - Auto-calculate duration_minutes

### 2. Time Entry Retrieval (5 tests)
- `test_get_time_entry_by_id_success` - Retrieve existing entry
- `test_get_time_entry_by_id_not_found` - Non-existent ID raises error
- `test_get_all_time_entries` - List all entries
- `test_get_time_entries_pagination` - Skip/limit parameters
- `test_get_time_entries_by_order_id` - Filter by order

### 3. Time Entry Updates (4 tests)
- `test_update_time_entry_success` - Update multiple fields
- `test_update_time_entry_end_time` - Stop running entry
- `test_update_time_entry_partial` - Update single field
- `test_update_time_entry_recalculates_duration` - Duration auto-updates

### 4. Time Entry Deletion (2 tests)
- `test_delete_time_entry_success` - Delete entry
- `test_delete_time_entry_not_found` - Delete non-existent entry

### 5. Active Time Tracking (3 tests)
- `test_get_active_time_entry` - Get currently running entry
- `test_stop_active_time_entry` - Stop running entry (set end_time)
- `test_no_active_time_entry` - Returns None when no active entry

### 6. Analytics & Reporting (4 tests)
- `test_get_summary_statistics` - Total hours, billable hours, etc.
- `test_get_weekly_report` - Hours by week
- `test_get_activity_breakdown` - Time per activity
- `test_get_daily_distribution` - Hours by day of week

### 7. Edge Cases & Validation (3 tests)
- `test_create_entry_invalid_order_id` - Foreign key validation
- `test_create_entry_invalid_activity_id` - Foreign key validation
- `test_create_entry_end_before_start` - Validation error

---

## Test Structure (Following Existing Patterns)

```python
"""
Unit tests for TimeTrackingService

Tests cover:
- Time entry creation with validation
- Time entry retrieval (by ID, by order, listing with filters)
- Time entry updates (including stopping active entries)
- Active time tracking
- Analytics and reporting
- Error handling and edge cases
"""
import pytest
from datetime import datetime, timedelta

from goldsmith_erp.services.time_tracking_service import TimeTrackingService
from goldsmith_erp.models.time_entry import TimeEntryCreate, TimeEntryUpdate
from goldsmith_erp.db.models import TimeEntry, Activity, Order


@pytest.mark.asyncio
class TestTimeEntryCreation:
    """Test time entry creation and validation"""

    async def test_create_time_entry_success(self, db_session, sample_order, sample_activity):
        """Test creating a time entry with all fields"""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=2)

        entry_data = TimeEntryCreate(
            order_id=sample_order.id,
            activity_id=sample_activity.id,
            start_time=start_time,
            end_time=end_time,
            location="Werkbank 1",
            notes="Setting stones on ring",
            complexity_rating=3,
            quality_rating=5
        )

        entry = await TimeTrackingService.create_time_entry(db_session, entry_data)

        assert entry.id is not None
        assert entry.order_id == sample_order.id
        assert entry.activity_id == sample_activity.id
        assert entry.duration_minutes == 120  # 2 hours
        assert entry.location == "Werkbank 1"
        assert entry.notes == "Setting stones on ring"
        assert entry.complexity_rating == 3
        assert entry.quality_rating == 5
```

---

## Fixtures Required

### New Fixtures (in conftest.py)

```python
@pytest.fixture
async def sample_activity(db_session):
    """Create a sample activity for testing"""
    activity = Activity(
        name="Fabrication",
        category="fabrication",
        icon="🔨",
        color="#3498db",
        usage_count=0,
        is_custom=False
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity

@pytest.fixture
async def sample_time_entry(db_session, sample_order, sample_activity, sample_user):
    """Create a sample time entry for testing"""
    start_time = datetime.utcnow() - timedelta(hours=2)
    end_time = datetime.utcnow()

    entry = TimeEntry(
        order_id=sample_order.id,
        user_id=sample_user.id,
        activity_id=sample_activity.id,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=120,
        location="Werkbank 1",
        notes="Test work session"
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry

@pytest.fixture
async def active_time_entry(db_session, sample_order, sample_activity, sample_user):
    """Create an active (running) time entry"""
    entry = TimeEntry(
        order_id=sample_order.id,
        user_id=sample_user.id,
        activity_id=sample_activity.id,
        start_time=datetime.utcnow() - timedelta(minutes=30),
        end_time=None,  # Still running
        duration_minutes=None,
        location="Werkbank 2"
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry
```

---

## Key Testing Patterns (2025 Best Practices)

### 1. Async Test Decorator
```python
@pytest.mark.asyncio
async def test_name(db_session):
    # Test implementation
```

### 2. Arrange-Act-Assert Pattern
```python
async def test_something(self, db_session):
    # Arrange
    data = TimeEntryCreate(...)

    # Act
    result = await TimeTrackingService.create_time_entry(db_session, data)

    # Assert
    assert result.id is not None
```

### 3. DateTime Handling
```python
from datetime import datetime, timedelta

start_time = datetime.utcnow()
end_time = start_time + timedelta(hours=2, minutes=30)
```

### 4. Error Testing
```python
async def test_invalid_data(self, db_session):
    with pytest.raises(ValueError, match="error message"):
        await TimeTrackingService.method(db_session, invalid_data)
```

### 5. Floating Point Comparisons
```python
# For durations in minutes
assert entry.duration_minutes == 120

# For hours (if needed)
assert abs(calculated_hours - expected_hours) < 0.01
```

---

## Coverage Goals

**Target Coverage:** 75%+

**Critical Paths to Cover:**
1. ✅ CRUD operations (Create, Read, Update, Delete)
2. ✅ Active time tracking (start, stop)
3. ✅ Duration calculations
4. ✅ Analytics methods (summary, reports)
5. ✅ Error handling
6. ✅ Edge cases (null values, invalid IDs)

**Not Required to Cover:**
- Database connection errors (handled by framework)
- Authorization checks (covered by integration tests)

---

## Expected Test Results

When running: `pytest tests/unit/test_time_tracking_service.py -v`

```
tests/unit/test_time_tracking_service.py::TestTimeEntryCreation::test_create_time_entry_success PASSED
tests/unit/test_time_tracking_service.py::TestTimeEntryCreation::test_create_time_entry_minimal_fields PASSED
tests/unit/test_time_tracking_service.py::TestTimeEntryCreation::test_create_time_entry_with_end_time PASSED
...
========================= 25 passed in 2.34s =========================
```

---

## Implementation Order

1. **Setup** (30 min)
   - Add fixtures to conftest.py
   - Import necessary modules

2. **Basic CRUD Tests** (2 hours)
   - Creation tests (5)
   - Retrieval tests (5)
   - Update tests (4)
   - Deletion tests (2)

3. **Active Tracking Tests** (1 hour)
   - Active entry tests (3)

4. **Analytics Tests** (2 hours)
   - Summary statistics
   - Reporting methods
   - Aggregations

5. **Edge Cases** (1 hour)
   - Validation errors
   - Edge cases

6. **Cleanup & Documentation** (30 min)
   - Code review
   - Documentation strings
   - Coverage report

**Total Time:** 6-8 hours

---

## Success Criteria

✅ **All tests pass**
✅ **75%+ code coverage** for TimeTrackingService
✅ **Follows existing test patterns** (test_material_service.py)
✅ **Uses pytest-asyncio best practices** (2025)
✅ **Clear test documentation** (docstrings)
✅ **No flaky tests** (deterministic results)
✅ **Fast execution** (< 5 seconds total)

---

## Notes

- Use `datetime.utcnow()` for all timestamps (UTC)
- UUID primary keys for TimeEntry (not integer)
- Duration is in minutes (integer)
- Follow existing naming conventions
- Test both success and failure cases
- Mock external dependencies if needed
