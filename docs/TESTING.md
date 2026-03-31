# Testing Guide - Goldsmith ERP

## Table of Contents

1. [Overview](#overview)
2. [Test Setup](#test-setup)
3. [Running Tests](#running-tests)
4. [Test Coverage](#test-coverage)
5. [Writing Tests](#writing-tests)
6. [CI/CD Integration](#cicd-integration)

---

## Overview

The Goldsmith ERP system has comprehensive test coverage including:
- **Unit tests** - Repository and service layer
- **Integration tests** - API endpoints
- **GDPR compliance tests** - Verify all GDPR requirements
- **Security tests** - Encryption, audit logging, rate limiting

**Test Framework:** pytest + pytest-asyncio
**Test Database:** SQLite (in-memory for fast tests)
**HTTP Client:** httpx (async)

---

## Test Setup

### Prerequisites

Install test dependencies:

```bash
poetry install --with dev
```

This installs:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `httpx` - HTTP client for API tests
- `aiosqlite` - Async SQLite for test database

### Configuration

Test configuration is in `pytest.ini`:

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
addopts = -v --tb=short
```

### Environment

Tests use in-memory SQLite database (no external dependencies required).

For encryption tests, ensure `ENCRYPTION_KEY` is set in `.env`:

```bash
ENCRYPTION_KEY=XrK7x5qN9YvP8mT2wF6jH4eR1uG3sL0bV9nC8kA7zI5=
```

---

## Running Tests

### Run All Tests

```bash
# Run all tests
poetry run pytest

# Run with verbose output
poetry run pytest -v

# Run with coverage
poetry run pytest --cov=goldsmith_erp --cov-report=html
```

### Run Specific Test Files

```bash
# Basic setup tests
poetry run pytest tests/test_basic_setup.py

# Customer repository tests
poetry run pytest tests/test_customer_repository.py

# GDPR compliance tests
poetry run pytest tests/test_customer_gdpr.py
```

### Run Specific Tests

```bash
# Run single test
poetry run pytest tests/test_basic_setup.py::test_health_endpoint

# Run tests matching pattern
poetry run pytest -k "encryption"

# Run tests with marker
poetry run pytest -m asyncio
```

### Run with Different Verbosity

```bash
# Minimal output
poetry run pytest -q

# Verbose output
poetry run pytest -v

# Very verbose (show test function names)
poetry run pytest -vv
```

---

## Test Coverage

### Current Test Files

#### 1. `test_basic_setup.py` (12 tests)

Infrastructure and import tests:

- ✅ Database session creation
- ✅ HTTP client creation
- ✅ Health endpoint
- ✅ Encryption service import and functionality
- ✅ Model imports (Customer, CustomerAuditLog)
- ✅ Repository imports
- ✅ Service imports
- ✅ Schema imports

**Run:** `poetry run pytest tests/test_basic_setup.py`

#### 2. `test_customer_repository.py` (18 tests)

Data access layer tests:

**CRUD Operations:**
- ✅ Create customer
- ✅ Get customer by ID
- ✅ Get customer by email
- ✅ Update customer
- ✅ Search customers

**Soft Delete:**
- ✅ Soft delete customer (is_deleted=True)
- ✅ Hard delete customer (permanent erasure)
- ✅ Exclude deleted from queries
- ✅ Include deleted with flag

**Consent Management:**
- ✅ Update consent with metadata
- ✅ Track consent version, IP, method

**PII Encryption:**
- ✅ Encrypt phone and address on create
- ✅ Decrypt on retrieval
- ✅ Verify encryption in database

**Data Retention:**
- ✅ Get customers past retention deadline
- ✅ Update retention deadline
- ✅ Calculate retention from last order

**Audit Logging:**
- ✅ Log customer creation
- ✅ Log customer updates with field changes
- ✅ Track who, what, when, where

**Run:** `poetry run pytest tests/test_customer_repository.py`

#### 3. `test_customer_gdpr.py` (15 tests)

GDPR compliance verification tests:

**Article 6 - Legal Basis:**
- ✅ Legal basis tracking (contract, consent, legitimate_interest)
- ✅ Legal basis validation (reject invalid values)

**Article 7 - Consent:**
- ✅ Consent with metadata (version, IP, timestamp, method)
- ✅ Consent withdrawal (revoke single consent)
- ✅ Revoke all consents

**Article 15 - Right of Access:**
- ✅ Complete data export (JSON format)
- ✅ Include personal data, consents, audit trail
- ✅ Export metadata

**Article 17 - Right to Erasure:**
- ✅ Soft delete (reversible)
- ✅ Hard delete (permanent, GDPR erasure)
- ✅ Anonymization (remove PII, keep statistics)

**Article 30 - Audit Logging:**
- ✅ Log all data access
- ✅ Track create, update, consent changes

**Article 32 - Security:**
- ✅ PII encryption at rest
- ✅ Decrypt on retrieval

**Article 5(1)(e) - Storage Limitation:**
- ✅ Retention deadline tracking
- ✅ Retention review list

**Customer Number Generation:**
- ✅ Format validation (CUST-YYYYMM-XXXX)
- ✅ Uniqueness guarantee

**Run:** `poetry run pytest tests/test_customer_gdpr.py`

### Coverage Summary

| Component | Tests | Status |
|-----------|-------|--------|
| Infrastructure | 12 | ✅ Complete |
| Repository Layer | 18 | ✅ Complete |
| GDPR Compliance | 15 | ✅ Complete |
| **TOTAL** | **45** | **✅** |

### Expected Coverage

When running with coverage:

```bash
poetry run pytest --cov=goldsmith_erp --cov-report=term-missing
```

Expected coverage:
- **Repository:** >90%
- **Service:** >85%
- **Models:** >80%
- **Overall:** >85%

---

## Writing Tests

### Test Structure

```python
"""
Test module docstring explaining what is tested.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.repositories.customer import CustomerRepository


@pytest.fixture
async def customer_repository(db_session: AsyncSession):
    """Fixture to create repository for testing."""
    return CustomerRepository(db_session, current_user_id=1)


@pytest.mark.asyncio
async def test_something(customer_repository: CustomerRepository):
    """Test that something works correctly."""
    # Arrange
    data = {"first_name": "Test", "last_name": "User"}

    # Act
    result = await customer_repository.create(**data)

    # Assert
    assert result is not None
    assert result.first_name == "Test"
```

### Async Tests

All database and API tests must be async:

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

### Using Fixtures

Available fixtures from `conftest.py`:

```python
# Database session
async def test_with_db(db_session: AsyncSession):
    ...

# HTTP client
async def test_with_client(client: AsyncClient):
    response = await client.get("/api/v1/customers")
    ...

# Both together
async def test_with_both(db_session: AsyncSession, client: AsyncClient):
    ...
```

### Testing GDPR Features

Example GDPR test:

```python
@pytest.mark.asyncio
async def test_gdpr_erasure(customer_service: CustomerService):
    """Test GDPR Article 17 - Right to Erasure."""
    # Create customer
    customer = await customer_service.create_customer(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
    )

    # Request erasure
    deleted = await customer_service.delete_customer(
        customer_id=customer.id,
        hard_delete=True,
        deletion_reason="GDPR erasure request",
    )

    assert deleted is True

    # Verify customer is gone
    with pytest.raises(Exception):
        await customer_service.get_customer(customer.id)
```

---

## Test Data

### Creating Test Users

```python
from goldsmith_erp.db.models import User
from goldsmith_erp.core.security import get_password_hash

user = User(
    email="test@example.com",
    first_name="Test",
    last_name="User",
    hashed_password=get_password_hash("password123"),
    is_active=True,
    role="admin",
)
db_session.add(user)
await db_session.commit()
```

### Creating Test Customers

```python
from goldsmith_erp.db.repositories.customer import CustomerRepository

repo = CustomerRepository(db_session, current_user_id=1)

customer = await repo.create(
    customer_number="CUST-202511-0001",
    first_name="Max",
    last_name="Mustermann",
    email="max@example.de",
    legal_basis="contract",
)
```

---

## CI/CD Integration

### GitHub Actions

Example `.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install Poetry
        run: |
          curl -sSL https://install.python-poetry.org | python3 -

      - name: Install dependencies
        run: poetry install --with dev

      - name: Run tests
        run: poetry run pytest --cov=goldsmith_erp --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

### Pre-commit Hooks

Add to `.pre-commit-config.yaml`:

```yaml
- repo: local
  hooks:
    - id: pytest
      name: pytest
      entry: poetry run pytest
      language: system
      pass_filenames: false
      always_run: true
```

---

## Debugging Tests

### Run Single Test with Debugging

```bash
# Add breakpoint in test
import pdb; pdb.set_trace()

# Or use pytest debugging
poetry run pytest --pdb tests/test_customer_repository.py::test_create_customer
```

### Show Print Statements

```bash
# Show print() output
poetry run pytest -s

# Show logging output
poetry run pytest --log-cli-level=DEBUG
```

### Show Slow Tests

```bash
# Show slowest 10 tests
poetry run pytest --durations=10
```

---

## Troubleshooting

### Issue: Tests fail with "no event loop"

**Solution:** Make sure test is marked with `@pytest.mark.asyncio`

### Issue: Database errors

**Solution:** Each test gets fresh database (in-memory SQLite). No cleanup needed.

### Issue: Import errors

**Solution:** Make sure Poetry environment is active:

```bash
poetry shell
pytest
```

### Issue: Encryption tests fail

**Solution:** Set ENCRYPTION_KEY in `.env`:

```bash
echo "ENCRYPTION_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" >> .env
```

---

## Best Practices

### ✅ DO

- Use descriptive test names (`test_creates_customer_with_gdpr_consent`)
- Test one thing per test
- Use arrange-act-assert pattern
- Mock external dependencies
- Clean up resources (handled automatically by fixtures)
- Test edge cases and error conditions
- Add docstrings to tests

### ❌ DON'T

- Share state between tests
- Depend on test execution order
- Use production database
- Skip cleanup
- Test implementation details
- Write overly complex tests

---

## Example Test Session

```bash
$ poetry run pytest -v

============================= test session starts ==============================
tests/test_basic_setup.py::test_database_session PASSED                  [  2%]
tests/test_basic_setup.py::test_http_client PASSED                       [  4%]
tests/test_basic_setup.py::test_health_endpoint PASSED                   [  6%]
tests/test_basic_setup.py::test_encryption_service_import PASSED         [  8%]
tests/test_basic_setup.py::test_encryption_decrypt PASSED                [ 11%]
tests/test_customer_repository.py::test_create_customer PASSED           [ 13%]
tests/test_customer_repository.py::test_get_customer_by_id PASSED        [ 15%]
tests/test_customer_repository.py::test_soft_delete_customer PASSED      [ 17%]
tests/test_customer_repository.py::test_update_consent PASSED            [ 20%]
tests/test_customer_gdpr.py::test_legal_basis_tracking PASSED            [ 22%]
tests/test_customer_gdpr.py::test_consent_with_metadata PASSED           [ 24%]
tests/test_customer_gdpr.py::test_data_export PASSED                     [ 26%]
tests/test_customer_gdpr.py::test_anonymization PASSED                   [ 28%]
...
============================= 45 passed in 12.34s ==============================
```

---

## Quick Reference

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=goldsmith_erp

# Run specific file
poetry run pytest tests/test_customer_gdpr.py

# Run specific test
poetry run pytest tests/test_basic_setup.py::test_health_endpoint

# Run tests matching keyword
poetry run pytest -k "gdpr"

# Verbose output
poetry run pytest -vv

# Stop on first failure
poetry run pytest -x

# Run last failed tests
poetry run pytest --lf

# Show slow tests
poetry run pytest --durations=10
```

---

**Last Updated:** 2025-11-06
**Version:** 1.0.0
**Test Count:** 45 tests
