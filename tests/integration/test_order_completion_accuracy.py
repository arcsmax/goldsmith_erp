import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    EstimateAccuracy, Order, Quote, QuoteLineItem, TimeEntry,
    Activity, Customer, User, QuoteLineType, UserRole,
)
from goldsmith_erp.services.estimate_accuracy_service import (
    safe_record_on_completion,
)


@pytest.mark.integration
async def test_accuracy_row_written_for_estimator_sourced_labor(
    db_session: AsyncSession,
):
    """An order whose quote has an estimator-sourced LABOR line writes
    an EstimateAccuracy row on completion. estimated_hours comes from
    metadata; actual_hours from sum of billable TimeEntries."""
    # Seed: user + customer + order with completed_at set, linked quote,
    # labor line with estimator_metadata, and a billable TimeEntry with hours=4.0
    user = User(
        email="test_accuracy_user@example.com",
        hashed_password="dummy",
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
        email="test_accuracy_cust@example.com",
        phone="+49123456789",
        street="Teststr. 1",
        city="Berlin",
        postal_code="10115",
        customer_type="private",
    )
    db_session.add(customer)
    await db_session.flush()

    completed_time = datetime.utcnow()
    order = Order(
        title="ORD-TEST-ACC-001",
        order_type="ring",
        status="COMPLETED",
        completed_at=completed_time,
    )
    db_session.add(order)
    await db_session.flush()

    quote = Quote(
        quote_number=f"KV-TEST-ACC-001",
        order_id=order.id,
        customer_id=customer.id,
        created_by=user.id,
        status="ACCEPTED",
        valid_until=datetime.utcnow() + timedelta(days=14),
        subtotal=575.25,
        tax_rate=19.0,
        tax_amount=109.30,
        total=684.55,
    )
    db_session.add(quote)
    await db_session.flush()

    line = QuoteLineItem(
        quote_id=quote.id,
        line_type=QuoteLineType.LABOR,
        description="Arbeitszeit (Schatzung)",
        quantity=3.17,
        unit_price=181.5,
        total=575.25,
        estimator_metadata={
            "suggested_hours": 3.17,
            "quoted_hours": 3.17,
            "similarity_level": "workshop",
            "sample_size": 5,
            "similar_orders": [42, 57, 63, 71, 88],
            "estimator_version": "labor_estimator_v1",
        },
    )
    db_session.add(line)
    await db_session.flush()

    activity = Activity(
        name="Sagen",
        category="fabrication",
        icon="✂",
        color="#FF6B6B",
        is_billable=True,
        hourly_rate=181.5,
    )
    db_session.add(activity)
    await db_session.flush()

    start = completed_time - timedelta(hours=4)
    entry = TimeEntry(
        id="test-entry-acc-001",
        order_id=order.id,
        user_id=user.id,
        activity_id=activity.id,
        start_time=start,
        end_time=completed_time,
        duration_minutes=240,
    )
    db_session.add(entry)
    await db_session.commit()

    # Act — new signature takes only db + order; all values derived internally
    await safe_record_on_completion(db_session, order)

    # Assert: an EstimateAccuracy row exists
    rows = (await db_session.execute(
        select(EstimateAccuracy).where(EstimateAccuracy.order_id == order.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].estimated_hours == 3.17
    assert rows[0].actual_hours == 4.0


@pytest.mark.integration
async def test_no_accuracy_row_for_manual_labor_line(
    db_session: AsyncSession,
):
    """An order whose labor line has estimator_metadata=NULL writes
    no EstimateAccuracy row (no trust signal to record)."""
    user = User(
        email="test_accuracy_user2@example.com",
        hashed_password="dummy",
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
        email="test_accuracy_cust2@example.com",
        phone="+49123456789",
        street="Teststr. 2",
        city="Berlin",
        postal_code="10115",
        customer_type="private",
    )
    db_session.add(customer)
    await db_session.flush()

    completed_time = datetime.utcnow()
    order = Order(
        title="ORD-TEST-ACC-002",
        order_type="chain",
        status="COMPLETED",
        completed_at=completed_time,
    )
    db_session.add(order)
    await db_session.flush()

    quote = Quote(
        quote_number=f"KV-TEST-ACC-002",
        order_id=order.id,
        customer_id=customer.id,
        created_by=user.id,
        status="ACCEPTED",
        valid_until=datetime.utcnow() + timedelta(days=14),
        subtotal=360.0,
        tax_rate=19.0,
        tax_amount=68.4,
        total=428.4,
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
        estimator_metadata=None,
    )
    db_session.add(line)
    await db_session.commit()

    await safe_record_on_completion(db_session, order)

    rows = (await db_session.execute(
        select(EstimateAccuracy).where(EstimateAccuracy.order_id == order.id)
    )).scalars().all()
    assert len(rows) == 0
