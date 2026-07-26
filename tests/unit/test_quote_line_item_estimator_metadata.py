import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import QuoteLineItem, Quote, Customer, User, QuoteLineType, UserRole
from goldsmith_erp.core.security import get_password_hash


@pytest.mark.unit
async def test_estimator_metadata_persists_as_jsonb(db_session: AsyncSession):
    """A QuoteLineItem created with estimator_metadata round-trips it intact."""
    # Setup: create a User + Customer + Quote + LineItem with estimator_metadata
    user = User(
        email="test_user_meta@example.com",
        hashed_password=get_password_hash("testpassword123"),
        first_name="Test",
        last_name="User",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    customer = Customer(
        first_name="Test",
        last_name="Customer",
        email="test_customer_meta@example.com",
        phone="+49123456789",
        street="Teststr. 1",
        city="Berlin",
        postal_code="10115",
        customer_type="private",
    )
    db_session.add(customer)
    await db_session.flush()

    quote = Quote(
        quote_number=f"KV-TEST-META-001",
        customer_id=customer.id,
        created_by=user.id,
        status="DRAFT",
        valid_until=datetime.utcnow() + timedelta(days=14),
        subtotal=0.0,
        tax_rate=19.0,
        tax_amount=0.0,
        total=0.0,
    )
    db_session.add(quote)
    await db_session.flush()

    metadata = {
        "suggested_hours": 3.17,
        "quoted_hours": 3.5,
        "similarity_level": "workshop",
        "sample_size": 5,
        "similar_orders": [42, 57, 63, 71, 88],
        "estimator_version": "labor_estimator_v1",
    }
    line = QuoteLineItem(
        quote_id=quote.id,
        line_type=QuoteLineType.LABOR,
        description="Arbeitszeit (Schatzung: workshop-Tier, 5 Auftrage)",
        quantity=3.5,
        unit_price=164.36,
        total=575.25,
        estimator_metadata=metadata,
    )
    db_session.add(line)
    await db_session.commit()
    await db_session.refresh(line)

    assert line.estimator_metadata == metadata
    assert line.estimator_metadata["suggested_hours"] == 3.17


@pytest.mark.unit
async def test_estimator_metadata_null_for_manual_entry(db_session: AsyncSession):
    """A QuoteLineItem without estimator_metadata persists as NULL."""
    user = User(
        email="test_user_meta2@example.com",
        hashed_password=get_password_hash("testpassword123"),
        first_name="Test",
        last_name="User",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    customer = Customer(
        first_name="Test",
        last_name="Customer",
        email="test_customer_meta2@example.com",
        phone="+49123456789",
        street="Teststr. 2",
        city="Berlin",
        postal_code="10115",
        customer_type="private",
    )
    db_session.add(customer)
    await db_session.flush()

    quote = Quote(
        quote_number=f"KV-TEST-META-002",
        customer_id=customer.id,
        created_by=user.id,
        status="DRAFT",
        valid_until=datetime.utcnow() + timedelta(days=14),
        subtotal=0.0,
        tax_rate=19.0,
        tax_amount=0.0,
        total=0.0,
    )
    db_session.add(quote)
    await db_session.flush()

    line = QuoteLineItem(
        quote_id=quote.id,
        line_type=QuoteLineType.LABOR,
        description="Arbeitszeit manuell",
        quantity=2.0,
        unit_price=180.0,
        total=360.0,
    )
    db_session.add(line)
    await db_session.commit()
    await db_session.refresh(line)

    assert line.estimator_metadata is None
