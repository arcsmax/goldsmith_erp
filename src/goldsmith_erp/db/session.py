# src/goldsmith_erp/db/session.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from goldsmith_erp.core.config import settings

# Build DATABASE_URL if not provided or invalid
database_url = str(settings.DATABASE_URL) if settings.DATABASE_URL else \
    f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"

# PostgreSQL-Engine mit async Treiber und Connection-Pool-Konfiguration
engine = create_async_engine(
    database_url,
    echo=settings.DEBUG,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
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