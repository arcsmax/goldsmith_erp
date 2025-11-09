"""
Transaction management utilities for ACID guarantees.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@asynccontextmanager
async def transactional(db: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database transactions with automatic rollback on error.

    Ensures ACID properties:
    - Atomicity: All operations succeed or all fail
    - Consistency: Database constraints are maintained
    - Isolation: Concurrent transactions don't interfere
    - Durability: Committed changes are permanent

    Usage:
        async with transactional(db):
            # Multiple database operations
            db.add(obj1)
            db.add(obj2)
            # Automatically commits on success, rolls back on error

    Args:
        db: AsyncSession database session

    Yields:
        AsyncSession: The database session

    Raises:
        Exception: Re-raises any exception after rollback
    """
    try:
        yield db
        await db.commit()
        logger.debug("Transaction committed successfully")
    except Exception as e:
        await db.rollback()
        logger.error(
            "Transaction rolled back due to error",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True
        )
        raise
    finally:
        # Session is managed by FastAPI dependency, don't close here
        pass


async def commit_or_rollback(db: AsyncSession) -> None:
    """
    Explicitly commit or rollback a transaction.

    Use this when you need manual control over transaction boundaries.

    Args:
        db: AsyncSession database session
    """
    try:
        await db.commit()
        logger.debug("Manual commit successful")
    except Exception as e:
        await db.rollback()
        logger.error(
            "Manual commit failed, rolled back",
            extra={"error": str(e)},
            exc_info=True
        )
        raise
