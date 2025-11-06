"""
GDPR Compliance Tests for Customer Management.

Tests verify GDPR requirements:
- Article 6: Legal basis tracking
- Article 7: Consent management
- Article 15: Right of access (data export)
- Article 17: Right to erasure
- Article 30: Audit logging
- Article 32: Security of processing (encryption)

Author: Claude AI
Date: 2025-11-06
"""

import pytest
from datetime import datetime, timedelta

from goldsmith_erp.db.repositories.customer import CustomerRepository
from goldsmith_erp.services.customer_service import CustomerService


@pytest.fixture
async def customer_service(customer_repository: CustomerRepository):
    """Create customer service for testing."""
    return CustomerService(customer_repository)


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Article 6: Legal Basis
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_legal_basis_tracking(customer_service: CustomerService):
    """Test that legal basis for processing is tracked (GDPR Article 6)."""
    customer = await customer_service.create_customer(
        first_name="Test",
        last_name="User",
        email="test@gdpr.de",
        legal_basis="contract",
    )

    assert customer.legal_basis == "contract"


@pytest.mark.asyncio
async def test_legal_basis_validation(customer_service: CustomerService):
    """Test that invalid legal basis is rejected."""
    with pytest.raises(Exception):  # Should raise HTTPException
        await customer_service.create_customer(
            first_name="Test",
            last_name="User",
            email="test2@gdpr.de",
            legal_basis="invalid_basis",
        )


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Article 7: Consent Management
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_consent_with_metadata(customer_service: CustomerService):
    """Test consent tracking with metadata (GDPR Article 7)."""
    customer = await customer_service.create_customer(
        first_name="Consent",
        last_name="Test",
        email="consent@gdpr.de",
        consent_marketing=True,
        consent_version="1.0",
        consent_ip_address="192.168.1.100",
        consent_method="web_form",
    )

    assert customer.consent_marketing is True
    assert customer.consent_date is not None
    assert customer.consent_version == "1.0"
    assert customer.consent_ip_address == "192.168.1.100"
    assert customer.consent_method == "web_form"


@pytest.mark.asyncio
async def test_consent_withdrawal(customer_service: CustomerService):
    """Test right to withdraw consent (GDPR Article 7(3))."""
    # Create customer with consent
    customer = await customer_service.create_customer(
        first_name="Withdraw",
        last_name="Test",
        email="withdraw@gdpr.de",
        consent_marketing=True,
    )

    assert customer.consent_marketing is True

    # Withdraw consent
    updated = await customer_service.update_consent(
        customer_id=customer.id,
        consent_type="marketing",
        consent_value=False,
        consent_version="1.0",
    )

    assert updated.consent_marketing is False


@pytest.mark.asyncio
async def test_revoke_all_consents(customer_service: CustomerService):
    """Test revoking all consents at once."""
    # Create customer with all consents
    customer = await customer_service.create_customer(
        first_name="RevokeAll",
        last_name="Test",
        email="revokeall@gdpr.de",
        consent_marketing=True,
        email_communication_consent=True,
        phone_communication_consent=True,
    )

    # Revoke all
    updated = await customer_service.revoke_all_consents(customer.id)

    assert updated.consent_marketing is False
    assert updated.email_communication_consent is False
    assert updated.phone_communication_consent is False


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Article 15: Right of Access
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_data_export(customer_service: CustomerService):
    """Test data export for subject access request (GDPR Article 15)."""
    # Create customer
    customer = await customer_service.create_customer(
        first_name="Export",
        last_name="Test",
        email="export@gdpr.de",
        phone="+49 123 456789",
        city="Berlin",
    )

    # Export data
    export_data = await customer_service.export_customer_data(customer.id)

    # Verify export contains required information
    assert "customer_information" in export_data
    assert "gdpr_information" in export_data
    assert "consent_preferences" in export_data
    assert "audit_trail" in export_data
    assert "export_metadata" in export_data

    # Verify personal data is included
    assert export_data["customer_information"]["email"] == "export@gdpr.de"
    assert export_data["customer_information"]["phone"] == "+49 123 456789"


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Article 17: Right to Erasure
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_soft_delete_erasure(customer_service: CustomerService):
    """Test soft delete (reversible erasure)."""
    customer = await customer_service.create_customer(
        first_name="SoftDelete",
        last_name="Test",
        email="softdelete@gdpr.de",
    )

    # Soft delete
    result = await customer_service.delete_customer(
        customer_id=customer.id,
        hard_delete=False,
        deletion_reason="Customer request",
    )

    assert result is True


@pytest.mark.asyncio
async def test_hard_delete_erasure(customer_service: CustomerService):
    """Test hard delete (permanent erasure for GDPR Article 17)."""
    customer = await customer_service.create_customer(
        first_name="HardDelete",
        last_name="Test",
        email="harddelete@gdpr.de",
    )

    customer_id = customer.id

    # Hard delete
    result = await customer_service.delete_customer(
        customer_id=customer_id,
        hard_delete=True,
        deletion_reason="GDPR erasure request",
    )

    assert result is True

    # Verify customer is gone
    with pytest.raises(Exception):
        await customer_service.get_customer(customer_id)


@pytest.mark.asyncio
async def test_anonymization(customer_service: CustomerService):
    """Test data anonymization (alternative to deletion)."""
    customer = await customer_service.create_customer(
        first_name="Anonymize",
        last_name="Test",
        email="anonymize@gdpr.de",
        phone="+49 123 456789",
        address_line1="Secret Street 123",
    )

    # Anonymize
    anonymized = await customer_service.anonymize_customer(
        customer_id=customer.id,
        reason="Retention period expired",
    )

    assert anonymized.first_name == "ANONYMIZED"
    assert anonymized.last_name.startswith("USER-")
    assert anonymized.email.startswith("anonymized-")
    assert anonymized.phone is None
    assert anonymized.address_line1 is None


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Article 5(1)(e): Storage Limitation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_retention_deadline_tracking(customer_service: CustomerService):
    """Test retention deadline tracking (GDPR Article 5(1)(e))."""
    customer = await customer_service.create_customer(
        first_name="Retention",
        last_name="Test",
        email="retention@gdpr.de",
    )

    # Should have retention deadline set (10 years default)
    assert customer.retention_deadline is not None
    assert customer.retention_deadline > datetime.utcnow()


@pytest.mark.asyncio
async def test_retention_review_list(customer_service: CustomerService):
    """Test getting customers needing retention review."""
    # Create customer with expired retention
    customer = await customer_service.create_customer(
        first_name="Expired",
        last_name="Retention",
        email="expired@gdpr.de",
    )

    # Manually set expired retention (bypass service logic)
    from goldsmith_erp.db.models import Customer
    customer.retention_deadline = datetime.utcnow() - timedelta(days=1)

    # Get retention review list
    expired_customers = await customer_service.get_customers_for_retention_review()

    # Should include our expired customer
    assert len(expired_customers) > 0


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Article 30: Records of Processing
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_audit_trail_logging(customer_service: CustomerService):
    """Test audit trail logging (GDPR Article 30)."""
    customer = await customer_service.create_customer(
        first_name="Audit",
        last_name="Test",
        email="audit@gdpr.de",
    )

    # Perform some actions
    await customer_service.update_customer(customer.id, city="Munich")
    await customer_service.update_consent(
        customer_id=customer.id,
        consent_type="marketing",
        consent_value=True,
    )

    # Get audit trail
    audit_logs = await customer_service.get_customer_audit_trail(customer.id)

    # Should have logs for create, update, consent
    assert len(audit_logs) >= 3
    actions = [log.action for log in audit_logs]
    assert "created" in actions
    assert "updated" in actions
    assert "consent_updated" in actions


# ═══════════════════════════════════════════════════════════════════════════
# GDPR Article 32: Security of Processing
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pii_encryption_at_rest(customer_service: CustomerService):
    """Test that PII is encrypted at rest (GDPR Article 32)."""
    customer = await customer_service.create_customer(
        first_name="Encryption",
        last_name="Test",
        email="encryption@gdpr.de",
        phone="+49 987 654321",
        address_line1="Secure Street 456",
    )

    # Retrieve customer
    retrieved = await customer_service.get_customer(customer.id)

    # Phone and address should be decrypted when retrieved
    assert retrieved.phone == "+49 987 654321"
    assert retrieved.address_line1 == "Secure Street 456"

    # Note: To fully test encryption, we would need to query the database
    # directly to verify that the stored values are encrypted


# ═══════════════════════════════════════════════════════════════════════════
# Customer Number Generation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_customer_number_format(customer_service: CustomerService):
    """Test customer number generation format (CUST-YYYYMM-XXXX)."""
    customer = await customer_service.create_customer(
        first_name="Number",
        last_name="Test",
        email="number@gdpr.de",
    )

    # Check format: CUST-YYYYMM-XXXX
    assert customer.customer_number.startswith("CUST-")
    parts = customer.customer_number.split("-")
    assert len(parts) == 3
    assert len(parts[1]) == 6  # YYYYMM
    assert len(parts[2]) == 4  # XXXX


@pytest.mark.asyncio
async def test_customer_number_uniqueness(customer_service: CustomerService):
    """Test that customer numbers are unique."""
    customer1 = await customer_service.create_customer(
        first_name="Unique1",
        last_name="Test",
        email="unique1@gdpr.de",
    )

    customer2 = await customer_service.create_customer(
        first_name="Unique2",
        last_name="Test",
        email="unique2@gdpr.de",
    )

    assert customer1.customer_number != customer2.customer_number
