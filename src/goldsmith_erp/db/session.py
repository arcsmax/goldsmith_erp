# src/goldsmith_erp/db/session.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from goldsmith_erp.core.config import settings

# Build DATABASE_URL if not provided or invalid
database_url = (
    str(settings.DATABASE_URL)
    if settings.DATABASE_URL
    else f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)

# SQL query timeout — only for PostgreSQL (not SQLite used in tests).
# Prevents runaway queries from blocking the connection pool.
connect_args: dict = {}
if "postgresql" in database_url:
    connect_args["server_settings"] = {
        "statement_timeout": "30000"  # 30 seconds (in milliseconds)
    }

# PostgreSQL-Engine mit async Treiber und Connection-Pool-Konfiguration
#
# hide_parameters=True (review fix): SQLAlchemy's DBAPIError.__str__ embeds
# the failing statement's BOUND PARAMETER VALUES by default. Any escaping
# IntegrityError/DBAPIError — e.g. a CustomerUpdate NOT NULL violation, a
# raced unique-index hit — that reaches db/transaction.py's transactional()
# gets logged via ``logger.error(..., extra={"error": str(e)}, ...)``, which
# would otherwise write the raw bound values (customer names, free-text
# subject/body, no-go values, etc.) straight into application logs —
# exactly the class of leak CLAUDE.md's "NEVER log customer PII in
# plaintext" rule forbids. hide_parameters replaces the parameter list with
# a fixed "[SQL parameters hidden due to hide_parameters=True]" marker while
# leaving the SQL text (column/table names only) intact for debugging.
engine = create_async_engine(
    database_url,
    echo=settings.DEBUG,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    connect_args=connect_args,
    hide_parameters=True,
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
