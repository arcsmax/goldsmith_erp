"""
Pytest configuration and shared fixtures for Goldsmith ERP tests.

Provides database sessions, test data fixtures, and authentication helpers.
"""
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient
from datetime import datetime
from typing import AsyncGenerator

from goldsmith_erp.main import app
from goldsmith_erp.db.session import get_db, AsyncSessionLocal
from goldsmith_erp.db.models import (
    User, Customer, Order, MetalPurchase, Material,
    MetalType, CostingMethod, OrderStatusEnum, UserRole
)
from goldsmith_erp.core.security import get_password_hash
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client():
    """HTTP client for API testing"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Database session for tests"""
    async with AsyncSessionLocal() as session:
        yield session
        # Rollback after each test to keep tests isolated
        await session.rollback()


# =============================================================================
# User Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """Create a test user"""
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpassword123"),
        first_name="Test",
        last_name="User",
        role=UserRole.USER,
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
        email="admin@example.com",
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
async def auth_headers(sample_user: User) -> dict:
    """Authentication headers for API requests"""
    # TODO: Generate real JWT token when auth is implemented
    return {"Authorization": f"Bearer fake-token-{sample_user.id}"}


@pytest_asyncio.fixture
async def admin_auth_headers(admin_user: User) -> dict:
    """Admin authentication headers for API requests"""
    # TODO: Generate real JWT token when auth is implemented
    return {"Authorization": f"Bearer fake-admin-token-{admin_user.id}"}


# =============================================================================
# Customer Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sample_customer(db_session: AsyncSession) -> Customer:
    """Create a test customer"""
    customer = Customer(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
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
    """Create a test business customer"""
    customer = Customer(
        first_name="Jane",
        last_name="Smith",
        company_name="Smith Jewelry GmbH",
        email="jane.smith@smithjewelry.com",
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