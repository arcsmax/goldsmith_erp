import asyncio
import pytest
from httpx import AsyncClient
from goldsmith_erp.main import app
from sqlalchemy.ext.asyncio import AsyncSession
from goldsmith_erp.db.session import get_db, AsyncSessionLocal

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session