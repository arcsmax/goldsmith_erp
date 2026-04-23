"""
Integration test configuration and fixtures.

Provides:
- Async SQLite test database (file-backed, unique per session)
- httpx AsyncClient with ASGITransport for testing the FastAPI app
- Authenticated client fixtures for ADMIN and GOLDSMITH roles
- Shared test data (user, customer) for integration tests

The real get_db dependency is overridden so no running PostgreSQL is needed.
Redis publish_event is patched to a no-op so tests don't need Redis.

Isolation strategy:
  Tables are created once per session and dropped at teardown.
  Every user/customer fixture creates rows with uuid-suffixed e-mail addresses
  so they never collide across tests even when commits are permanent.
"""
import asyncio
import os
import uuid
from datetime import timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from goldsmith_erp.core.security import create_access_token, get_password_hash
from goldsmith_erp.db.models import Base, Customer, User, UserRole
from goldsmith_erp.db.session import get_db
from goldsmith_erp.main import app

# ---------------------------------------------------------------------------
# Test database — honors TEST_DATABASE_URL env var so CI can point integration
# tests at real Postgres while local runs default to file-backed SQLite.
#
# Fallback: unique SQLite filename so parallel local runs don't collide.
# CI sets TEST_DATABASE_URL=postgresql+asyncpg://... — see F1 fix spec
# (docs/fix-plan/2026-04-23/F1-pg-test-target.md). SQLite fallback is OK for
# the majority of integration tests; a handful (concurrent metal consumption)
# are gated with explicit skipif-on-SQLite markers — they become executable
# once TEST_DATABASE_URL points at Postgres.
# ---------------------------------------------------------------------------

_DB_FILENAME = f"integration_test_{uuid.uuid4().hex}.db"
_SQLITE_FALLBACK_URL = f"sqlite+aiosqlite:///{_DB_FILENAME}"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", _SQLITE_FALLBACK_URL)
_IS_SQLITE = TEST_DATABASE_URL.startswith("sqlite")

# ``check_same_thread`` is a SQLite-only kwarg; passing it to asyncpg raises.
_engine_kwargs: dict = {"echo": False}
if _IS_SQLITE:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # asyncpg connections are bound to the event loop they were created on.
    # The session-scoped event_loop fixture used here means a pooled connection
    # opened during one test can leak into the next test's loop context,
    # tripping "Future attached to a different loop". NullPool disables
    # connection reuse so each checkout creates a fresh connection.
    _engine_kwargs["poolclass"] = NullPool

test_engine = create_async_engine(TEST_DATABASE_URL, **_engine_kwargs)

TestSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Event loop (session-scoped so all async fixtures share it)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole integration test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database lifecycle
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create tables once per session; drop tables at teardown.

    For the SQLite fallback we also delete the on-disk file. On Postgres the
    database is provisioned by the CI job (or by `make test-integration-pg`
    locally); we only manage our own schema within it.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    if _IS_SQLITE and os.path.exists(_DB_FILENAME):
        os.remove(_DB_FILENAME)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session for a single test.

    Yields a session and then truncates all tables after each test so that
    committed rows do not leak between tests.
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


# ---------------------------------------------------------------------------
# Dependency override helpers
# ---------------------------------------------------------------------------

def _override_get_db_factory(session: AsyncSession):
    """Return a get_db override that always yields the provided session."""
    async def _get_db_override():
        yield session
    return _get_db_override


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """
    Unauthenticated AsyncClient backed by the SQLite test database.
    Redis publish_event is patched to a no-op.
    """
    app.dependency_overrides[get_db] = _override_get_db_factory(db_session)
    with patch(
        "goldsmith_erp.services.order_service.publish_event",
        new=AsyncMock(return_value=None),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User fixtures — each call creates a user with a unique e-mail address
# so tests that commit never collide with each other.
# ---------------------------------------------------------------------------

def _unique(prefix: str) -> str:
    """Return a unique e-mail-safe string prefixed by prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create a fresh ADMIN user for this test."""
    user = User(
        email=f"{_unique('admin')}@integration-test.example.com",
        hashed_password=get_password_hash("AdminPass123!"),
        first_name="Integration",
        last_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def goldsmith_user(db_session: AsyncSession) -> User:
    """Create a fresh GOLDSMITH user for this test."""
    user = User(
        email=f"{_unique('goldsmith')}@integration-test.example.com",
        hashed_password=get_password_hash("GoldPass123!"),
        first_name="Integration",
        last_name="Goldsmith",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    """Create a fresh VIEWER user for this test."""
    user = User(
        email=f"{_unique('viewer')}@integration-test.example.com",
        hashed_password=get_password_hash("ViewPass123!"),
        first_name="Integration",
        last_name="Viewer",
        role=UserRole.VIEWER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_customer(db_session: AsyncSession) -> Customer:
    """Create a fresh customer for order tests."""
    customer = Customer(
        first_name="Maria",
        last_name="Mustermann",
        email=f"{_unique('customer')}@integration-test.example.com",
        phone="+49 89 123456",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


# ---------------------------------------------------------------------------
# Auth header helpers
# ---------------------------------------------------------------------------

def _make_bearer_headers(user: User) -> dict:
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(hours=1),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_auth_headers(admin_user: User) -> dict:
    """Bearer token headers for the ADMIN test user."""
    return _make_bearer_headers(admin_user)


@pytest_asyncio.fixture
async def goldsmith_auth_headers(goldsmith_user: User) -> dict:
    """Bearer token headers for the GOLDSMITH test user."""
    return _make_bearer_headers(goldsmith_user)


@pytest_asyncio.fixture
async def viewer_auth_headers(viewer_user: User) -> dict:
    """Bearer token headers for the VIEWER test user."""
    return _make_bearer_headers(viewer_user)


@pytest_asyncio.fixture
async def authenticated_client(db_session: AsyncSession, admin_user: User):
    """
    AsyncClient pre-configured with an ADMIN JWT token.
    Convenience fixture for tests that just need any authenticated client.
    """
    app.dependency_overrides[get_db] = _override_get_db_factory(db_session)
    headers = _make_bearer_headers(admin_user)
    with patch(
        "goldsmith_erp.services.order_service.publish_event",
        new=AsyncMock(return_value=None),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=headers,
        ) as ac:
            yield ac
    app.dependency_overrides.clear()
