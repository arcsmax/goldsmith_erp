from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from goldsmith_erp.core.config import settings

# PostgreSQL-Engine mit async Treiber
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# Asynchrone Session-Factory
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db() -> AsyncSession:
    """Dependency für FastAPI, die eine DB-Session liefert."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()