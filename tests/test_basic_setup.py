"""
Basic setup tests to verify test infrastructure.

Author: Claude AI
Date: 2025-11-06
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient


# ═══════════════════════════════════════════════════════════════════════════
# Infrastructure Tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_database_session(db_session: AsyncSession):
    """Test that database session is created properly."""
    assert db_session is not None
    assert isinstance(db_session, AsyncSession)


@pytest.mark.asyncio
async def test_http_client(client: AsyncClient):
    """Test that HTTP client is created properly."""
    assert client is not None
    assert isinstance(client, AsyncClient)


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════
# Encryption Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_encryption_service_import():
    """Test that encryption service can be imported."""
    from goldsmith_erp.core.encryption import get_encryption_service, EncryptionService

    assert get_encryption_service is not None
    assert EncryptionService is not None


def test_encryption_key_configured():
    """Test that encryption key is configured."""
    from goldsmith_erp.core.config import settings

    assert hasattr(settings, "ENCRYPTION_KEY")
    assert settings.ENCRYPTION_KEY is not None
    assert len(settings.ENCRYPTION_KEY) > 0


def test_encryption_decrypt():
    """Test encryption and decryption."""
    from goldsmith_erp.core.encryption import get_encryption_service

    encryption = get_encryption_service()

    # Test data
    plaintext = "Hello, GDPR!"

    # Encrypt
    encrypted = encryption.encrypt(plaintext)
    assert encrypted is not None
    assert encrypted != plaintext

    # Decrypt
    decrypted = encryption.decrypt(encrypted)
    assert decrypted == plaintext


# ═══════════════════════════════════════════════════════════════════════════
# Model Import Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_customer_model_import():
    """Test that Customer model can be imported."""
    from goldsmith_erp.db.models import Customer

    assert Customer is not None
    assert hasattr(Customer, "__tablename__")
    assert Customer.__tablename__ == "customers"


def test_customer_audit_log_model_import():
    """Test that CustomerAuditLog model can be imported."""
    from goldsmith_erp.db.models import CustomerAuditLog

    assert CustomerAuditLog is not None
    assert hasattr(CustomerAuditLog, "__tablename__")
    assert CustomerAuditLog.__tablename__ == "customer_audit_logs"


# ═══════════════════════════════════════════════════════════════════════════
# Repository Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_customer_repository_import():
    """Test that CustomerRepository can be imported."""
    from goldsmith_erp.db.repositories.customer import CustomerRepository

    assert CustomerRepository is not None


# ═══════════════════════════════════════════════════════════════════════════
# Service Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_customer_service_import():
    """Test that CustomerService can be imported."""
    from goldsmith_erp.services.customer_service import CustomerService

    assert CustomerService is not None


# ═══════════════════════════════════════════════════════════════════════════
# Schema Tests
# ═══════════════════════════════════════════════════════════════════════════

def test_customer_schemas_import():
    """Test that customer Pydantic schemas can be imported."""
    from goldsmith_erp.models.customer import (
        CustomerCreate,
        CustomerUpdate,
        CustomerResponse,
        ConsentUpdate,
    )

    assert CustomerCreate is not None
    assert CustomerUpdate is not None
    assert CustomerResponse is not None
    assert ConsentUpdate is not None
