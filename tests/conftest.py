"""
Pytest configuration and shared fixtures for Goldsmith ERP tests.

Provides database sessions, test data fixtures, and authentication helpers.
Uses an in-memory async SQLite database so unit tests run without PostgreSQL.
"""
import asyncio
import os
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from datetime import datetime, timedelta
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from goldsmith_erp.main import app
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import (
    Base, User, Customer, Order, MetalPurchase, Material,
    MetalType, CostingMethod, OrderStatusEnum, UserRole
)
from goldsmith_erp.core.security import get_password_hash


# ---------------------------------------------------------------------------
# Test database — file-backed SQLite, unique per session to allow parallel runs
# ---------------------------------------------------------------------------

_DB_FILENAME = f"unit_test_{uuid.uuid4().hex}.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{_DB_FILENAME}"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

TestSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create tables once per session; drop and delete the DB file afterwards."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    if os.path.exists(_DB_FILENAME):
        os.remove(_DB_FILENAME)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async SQLite session for a single test.

    Yields a session and then truncates all tables after each test so that
    committed rows (written by service-layer commits) do not leak between tests.
    Using DELETE rather than TRUNCATE because SQLite does not support TRUNCATE.
    """
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()

    # Wipe all rows after each test so the next test starts with an empty DB.
    # This runs outside the session to ensure it executes even if the test fails.
    async with TestSessionLocal() as cleanup:
        for table in reversed(Base.metadata.sorted_tables):
            await cleanup.execute(table.delete())
        await cleanup.commit()


@pytest.fixture(autouse=True)
def mock_publish_event(monkeypatch):
    """
    Replace publish_event with a no-op async function for all unit tests.

    Unit tests must never connect to Redis. Any service that calls
    publish_event after a DB operation will silently succeed.
    """
    async def _noop(*args, **kwargs):
        pass

    monkeypatch.setattr("goldsmith_erp.core.pubsub.publish_event", _noop)
    monkeypatch.setattr("goldsmith_erp.services.order_service.publish_event", _noop)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """HTTP client for API testing backed by the SQLite test database."""
    app.dependency_overrides[get_db] = _override_get_db_factory(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _override_get_db_factory(session: AsyncSession):
    async def _get_db_override():
        yield session
    return _get_db_override


# =============================================================================
# User Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """Create a test user with GOLDSMITH role"""
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("testpassword123"),
        first_name="Test",
        last_name="User",
        role=UserRole.GOLDSMITH,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create a test admin user"""
    user = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("adminpassword123"),
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
def sample_user_password() -> str:
    """Known password for test users (for login tests)"""
    return "testpassword123"


@pytest_asyncio.fixture
async def auth_headers(sample_user: User) -> dict:
    """Authentication headers for API requests with real JWT token"""
    from goldsmith_erp.core.security import create_access_token

    token = create_access_token(
        data={"sub": str(sample_user.id)},
        expires_delta=timedelta(hours=1)
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_auth_headers(admin_user: User) -> dict:
    """Admin authentication headers for API requests with real JWT token"""
    from goldsmith_erp.core.security import create_access_token

    token = create_access_token(
        data={"sub": str(admin_user.id)},
        expires_delta=timedelta(hours=1)
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def inactive_user(db_session: AsyncSession) -> User:
    """Create an inactive user for testing"""
    user = User(
        email=f"inactive_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("testpassword123"),
        first_name="Inactive",
        last_name="User",
        role=UserRole.GOLDSMITH,
        is_active=False  # Inactive!
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# =============================================================================
# Customer Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sample_customer(db_session: AsyncSession) -> Customer:
    """Create a test customer — first_name/last_name match test search assertions"""
    customer = Customer(
        first_name="Max",
        last_name="Mustermann",
        email=f"max.mustermann_{uuid.uuid4().hex[:8]}@example.com",
        phone="+49 123 456789",
        customer_type="private",
        is_active=True
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def business_customer(db_session: AsyncSession) -> Customer:
    """Create a test business customer — company_name matches test search assertions"""
    customer = Customer(
        first_name="Jane",
        last_name="Smith",
        company_name="Edelmetall GmbH",
        email=f"jane.smith_{uuid.uuid4().hex[:8]}@smithjewelry.com",
        phone="+49 987 654321",
        customer_type="business",
        is_active=True
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


# =============================================================================
# Metal Inventory Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sample_metal_purchase(db_session: AsyncSession) -> MetalPurchase:
    """Create a test metal purchase (100g of 18K gold @ 45 EUR/g)"""
    purchase = MetalPurchase(
        date_purchased=datetime.utcnow(),
        metal_type=MetalType.GOLD_18K,
        weight_g=100.0,
        remaining_weight_g=100.0,
        price_total=4500.00,
        price_per_gram=45.00,
        supplier="Test Supplier",
        invoice_number="TEST-001"
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    return purchase


@pytest_asyncio.fixture
async def multiple_metal_purchases(db_session: AsyncSession) -> list[MetalPurchase]:
    """Create multiple metal purchases for testing FIFO/LIFO"""
    purchases = [
        MetalPurchase(
            date_purchased=datetime(2025, 1, 1),  # Oldest
            metal_type=MetalType.GOLD_18K,
            weight_g=100.0,
            remaining_weight_g=100.0,
            price_total=4400.00,
            price_per_gram=44.00,
            supplier="Supplier A"
        ),
        MetalPurchase(
            date_purchased=datetime(2025, 6, 1),  # Middle
            metal_type=MetalType.GOLD_18K,
            weight_g=100.0,
            remaining_weight_g=100.0,
            price_total=4500.00,
            price_per_gram=45.00,
            supplier="Supplier B"
        ),
        MetalPurchase(
            date_purchased=datetime(2025, 11, 1),  # Newest
            metal_type=MetalType.GOLD_18K,
            weight_g=100.0,
            remaining_weight_g=100.0,
            price_total=4600.00,
            price_per_gram=46.00,
            supplier="Supplier C"
        ),
    ]

    for purchase in purchases:
        db_session.add(purchase)

    await db_session.commit()

    for purchase in purchases:
        await db_session.refresh(purchase)

    return purchases


@pytest_asyncio.fixture
async def silver_purchase(db_session: AsyncSession) -> MetalPurchase:
    """Create a test silver purchase (500g of 925 silver @ 0.80 EUR/g)"""
    purchase = MetalPurchase(
        date_purchased=datetime.utcnow(),
        metal_type=MetalType.SILVER_925,
        weight_g=500.0,
        remaining_weight_g=500.0,
        price_total=400.00,
        price_per_gram=0.80,
        supplier="Silver Supplier",
        invoice_number="SILVER-001"
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    return purchase


# =============================================================================
# Order Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sample_order(
    db_session: AsyncSession,
    sample_customer: Customer
) -> Order:
    """Create a test order"""
    order = Order(
        title="Wedding Ring",
        description="18K Gold Wedding Ring",
        customer_id=sample_customer.id,
        status=OrderStatusEnum.NEW,
        estimated_weight_g=25.0,
        scrap_percentage=5.0,
        profit_margin_percent=40.0,
        vat_rate=19.0
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def order_with_metal_type(
    db_session: AsyncSession,
    sample_customer: Customer
) -> Order:
    """Create a test order with metal type specified"""
    order = Order(
        title="Gold Bracelet",
        description="18K Gold Bracelet with gemstones",
        customer_id=sample_customer.id,
        status=OrderStatusEnum.NEW,
        estimated_weight_g=30.0,
        metal_type=MetalType.GOLD_18K,
        costing_method_used=CostingMethod.FIFO,
        scrap_percentage=5.0,
        labor_hours=4.0,
        hourly_rate=75.00,
        profit_margin_percent=40.0,
        vat_rate=19.0
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


# =============================================================================
# Material Fixtures (Legacy)
# =============================================================================


@pytest_asyncio.fixture
async def sample_material(db_session: AsyncSession) -> Material:
    """Create a test material (legacy material system)"""
    material = Material(
        name="Test Material",
        description="Test material for legacy system",
        unit_price=10.0,
        stock=100.0,
        unit="g"
    )
    db_session.add(material)
    await db_session.commit()
    await db_session.refresh(material)
    return material


# =============================================================================
# Activity & Time Tracking Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sample_activity(db_session: AsyncSession):
    """Create a sample activity for testing"""
    from goldsmith_erp.db.models import Activity

    activity = Activity(
        name="Fabrication",
        category="fabrication",
        icon="hammer",
        color="#3498db",
        usage_count=0,
        is_custom=False,
        created_at=datetime.utcnow()
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest_asyncio.fixture
async def polishing_activity(db_session: AsyncSession):
    """Create a polishing activity for testing"""
    from goldsmith_erp.db.models import Activity

    activity = Activity(
        name="Polishing",
        category="finishing",
        icon="sparkles",
        color="#2ecc71",
        usage_count=0,
        is_custom=False,
        created_at=datetime.utcnow()
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest_asyncio.fixture
async def sample_time_entry(
    db_session: AsyncSession,
    sample_order: Order,
    sample_activity,
    sample_user: User
):
    """Create a completed time entry for testing"""
    from goldsmith_erp.db.models import TimeEntry

    start_time = datetime.utcnow() - timedelta(hours=2)
    end_time = datetime.utcnow()

    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=sample_order.id,
        user_id=sample_user.id,
        activity_id=sample_activity.id,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=120,
        location="Werkbank 1",
        notes="Test work session",
        complexity_rating=3,
        quality_rating=5,
        rework_required=False,
        created_at=datetime.utcnow()
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


@pytest_asyncio.fixture
async def active_time_entry(
    db_session: AsyncSession,
    sample_order: Order,
    sample_activity,
    sample_user: User
):
    """Create an active (running) time entry"""
    from goldsmith_erp.db.models import TimeEntry

    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=sample_order.id,
        user_id=sample_user.id,
        activity_id=sample_activity.id,
        start_time=datetime.utcnow() - timedelta(minutes=30),
        end_time=None,  # Still running
        duration_minutes=None,
        location="Werkbank 2",
        created_at=datetime.utcnow()
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry
