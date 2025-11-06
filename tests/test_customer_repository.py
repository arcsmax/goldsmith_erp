"""
Tests for CustomerRepository (GDPR-compliant data access layer).

Tests cover:
- Basic CRUD operations
- Soft delete functionality
- Consent management
- Data retention
- Audit logging
- PII encryption/decryption
- Search and filtering

Author: Claude AI
Date: 2025-11-06
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.repositories.customer import CustomerRepository
from goldsmith_erp.db.models import Customer, CustomerAuditLog, User


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create admin user for testing."""
    from goldsmith_erp.core.security import get_password_hash

    user = User(
        email="admin@test.com",
        first_name="Admin",
        last_name="User",
        hashed_password=get_password_hash("password123"),
        is_active=True,
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def customer_repository(db_session: AsyncSession, admin_user: User):
    """Create customer repository for testing."""
    return CustomerRepository(db_session, current_user_id=admin_user.id)


# ═══════════════════════════════════════════════════════════════════════════
# Basic CRUD Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_customer(customer_repository: CustomerRepository):
    """Test creating a new customer."""
    customer = await customer_repository.create(
        customer_number="CUST-202511-0001",
        first_name="Max",
        last_name="Mustermann",
        email="max@example.de",
        phone="+49 123 456789",
        legal_basis="contract",
    )

    assert customer.id is not None
    assert customer.first_name == "Max"
    assert customer.last_name == "Mustermann"
    assert customer.email == "max@example.de"
    assert customer.is_active is True
    assert customer.is_deleted is False
    # Phone should be decrypted after retrieval
    assert customer.phone == "+49 123 456789"


@pytest.mark.asyncio
async def test_get_customer_by_id(customer_repository: CustomerRepository):
    """Test retrieving customer by ID."""
    # Create customer
    created = await customer_repository.create(
        customer_number="CUST-202511-0002",
        first_name="Erika",
        last_name="Musterfrau",
        email="erika@example.de",
        legal_basis="contract",
    )

    # Retrieve customer
    customer = await customer_repository.get_by_id(created.id)

    assert customer is not None
    assert customer.id == created.id
    assert customer.email == "erika@example.de"


@pytest.mark.asyncio
async def test_get_customer_by_email(customer_repository: CustomerRepository):
    """Test retrieving customer by email."""
    # Create customer
    await customer_repository.create(
        customer_number="CUST-202511-0003",
        first_name="Hans",
        last_name="Schmidt",
        email="hans@example.de",
        legal_basis="contract",
    )

    # Retrieve by email
    customer = await customer_repository.get_by_email("hans@example.de")

    assert customer is not None
    assert customer.first_name == "Hans"
    assert customer.last_name == "Schmidt"


@pytest.mark.asyncio
async def test_update_customer(customer_repository: CustomerRepository):
    """Test updating customer information."""
    # Create customer
    customer = await customer_repository.create(
        customer_number="CUST-202511-0004",
        first_name="Anna",
        last_name="Müller",
        email="anna@example.de",
        legal_basis="contract",
    )

    # Update customer
    updated = await customer_repository.update(
        customer.id,
        phone="+49 987 654321",
        city="Berlin",
    )

    assert updated is not None
    assert updated.phone == "+49 987 654321"
    assert updated.city == "Berlin"
    assert updated.updated_at is not None


# ═══════════════════════════════════════════════════════════════════════════
# Soft Delete Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_soft_delete_customer(customer_repository: CustomerRepository):
    """Test soft deleting a customer."""
    # Create customer
    customer = await customer_repository.create(
        customer_number="CUST-202511-0005",
        first_name="Peter",
        last_name="Weber",
        email="peter@example.de",
        legal_basis="contract",
    )

    # Soft delete
    deleted = await customer_repository.delete(
        customer.id,
        hard_delete=False,
        deletion_reason="Test soft delete",
    )

    assert deleted is True

    # Should not be found in normal query
    found = await customer_repository.get_by_id(customer.id, include_deleted=False)
    assert found is None

    # Should be found when including deleted
    found_deleted = await customer_repository.get_by_id(customer.id, include_deleted=True)
    assert found_deleted is not None
    assert found_deleted.is_deleted is True
    assert found_deleted.deletion_reason == "Test soft delete"


@pytest.mark.asyncio
async def test_hard_delete_customer(customer_repository: CustomerRepository):
    """Test hard deleting a customer (GDPR erasure)."""
    # Create customer
    customer = await customer_repository.create(
        customer_number="CUST-202511-0006",
        first_name="Klaus",
        last_name="Fischer",
        email="klaus@example.de",
        legal_basis="contract",
    )

    customer_id = customer.id

    # Hard delete
    deleted = await customer_repository.delete(
        customer_id,
        hard_delete=True,
        deletion_reason="GDPR erasure request",
    )

    assert deleted is True

    # Should not be found even with include_deleted
    found = await customer_repository.get_by_id(customer_id, include_deleted=True)
    assert found is None


# ═══════════════════════════════════════════════════════════════════════════
# Consent Management Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_update_consent(customer_repository: CustomerRepository):
    """Test updating customer consent."""
    # Create customer
    customer = await customer_repository.create(
        customer_number="CUST-202511-0007",
        first_name="Maria",
        last_name="Wagner",
        email="maria@example.de",
        legal_basis="contract",
        consent_marketing=False,
    )

    # Update consent
    updated = await customer_repository.update_consent(
        customer_id=customer.id,
        consent_type="marketing",
        consent_value=True,
        consent_version="1.0",
        ip_address="192.168.1.100",
        consent_method="web_form",
    )

    assert updated is not None
    assert updated.consent_marketing is True
    assert updated.consent_date is not None
    assert updated.consent_version == "1.0"
    assert updated.consent_ip_address == "192.168.1.100"


# ═══════════════════════════════════════════════════════════════════════════
# Search Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_search_customers(customer_repository: CustomerRepository):
    """Test searching customers by name/email."""
    # Create multiple customers
    await customer_repository.create(
        customer_number="CUST-202511-0008",
        first_name="Thomas",
        last_name="Becker",
        email="thomas@example.de",
        legal_basis="contract",
    )

    await customer_repository.create(
        customer_number="CUST-202511-0009",
        first_name="Thomas",
        last_name="Müller",
        email="thomas.mueller@example.de",
        legal_basis="contract",
    )

    # Search by first name
    results = await customer_repository.search("Thomas")

    assert len(results) >= 2
    assert all(c.first_name == "Thomas" for c in results)


# ═══════════════════════════════════════════════════════════════════════════
# PII Encryption Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pii_encryption(customer_repository: CustomerRepository, db_session: AsyncSession):
    """Test that PII fields are encrypted in database."""
    # Create customer with PII
    customer = await customer_repository.create(
        customer_number="CUST-202511-0010",
        first_name="Sophie",
        last_name="Schneider",
        email="sophie@example.de",
        phone="+49 111 222333",
        address_line1="Hauptstraße 123",
        legal_basis="contract",
    )

    # Check that phone is decrypted when retrieved via repository
    assert customer.phone == "+49 111 222333"
    assert customer.address_line1 == "Hauptstraße 123"

    # TODO: Check database directly to verify encryption
    # (requires raw SQL query to bypass repository decryption)


# ═══════════════════════════════════════════════════════════════════════════
# Data Retention Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_get_customers_for_deletion(customer_repository: CustomerRepository):
    """Test retrieving customers past retention deadline."""
    # Create customer with expired retention
    customer = await customer_repository.create(
        customer_number="CUST-202511-0011",
        first_name="Frank",
        last_name="Hoffmann",
        email="frank@example.de",
        legal_basis="contract",
        retention_deadline=datetime.utcnow() - timedelta(days=1),  # Yesterday
    )

    # Get customers for deletion
    expired = await customer_repository.get_customers_for_deletion()

    assert len(expired) > 0
    assert any(c.id == customer.id for c in expired)


@pytest.mark.asyncio
async def test_update_retention_deadline(customer_repository: CustomerRepository):
    """Test updating retention deadline."""
    # Create customer
    customer = await customer_repository.create(
        customer_number="CUST-202511-0012",
        first_name="Julia",
        last_name="Koch",
        email="julia@example.de",
        legal_basis="contract",
    )

    # Update retention
    last_order = datetime.utcnow()
    updated = await customer_repository.update_retention_deadline(
        customer_id=customer.id,
        last_order_date=last_order,
        retention_period_days=365,  # 1 year
    )

    assert updated is not None
    assert updated.last_order_date == last_order
    # Retention deadline should be ~1 year from now
    assert updated.retention_deadline > datetime.utcnow() + timedelta(days=360)


# ═══════════════════════════════════════════════════════════════════════════
# Audit Logging Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_audit_logging_on_create(customer_repository: CustomerRepository):
    """Test that customer creation is logged."""
    # Create customer
    customer = await customer_repository.create(
        customer_number="CUST-202511-0013",
        first_name="Michael",
        last_name="Braun",
        email="michael@example.de",
        legal_basis="contract",
    )

    # Check audit logs
    logs = await customer_repository.get_audit_logs(customer.id)

    assert len(logs) > 0
    assert any(log.action == "created" for log in logs)


@pytest.mark.asyncio
async def test_audit_logging_on_update(customer_repository: CustomerRepository):
    """Test that customer updates are logged with field changes."""
    # Create customer
    customer = await customer_repository.create(
        customer_number="CUST-202511-0014",
        first_name="Laura",
        last_name="Schulz",
        email="laura@example.de",
        legal_basis="contract",
    )

    # Update customer
    await customer_repository.update(
        customer.id,
        phone="+49 555 666777",
    )

    # Check audit logs
    logs = await customer_repository.get_audit_logs(customer.id)

    update_logs = [log for log in logs if log.action == "updated"]
    assert len(update_logs) > 0
    assert any(log.field_name == "phone" for log in update_logs)
