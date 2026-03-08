"""Async PostgreSQL database configuration."""
import logging
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Worker process gets a smaller pool — it only runs scheduled tasks.
_is_scheduler = os.environ.get("RUN_SCHEDULER", "false").lower() == "true"
_pool_size = 3 if _is_scheduler else 5
_max_overflow = 2 if _is_scheduler else 10

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_pre_ping=True,
    pool_recycle=300,     # Recycle connections every 5 min — prevents stale conn buildup
    pool_timeout=10,      # Fail fast (10s) instead of blocking 30s then crashing
    pool_reset_on_return="rollback",  # Always rollback on return — clears "idle in transaction"
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session.

    Always closes the transaction after the endpoint returns — prevents
    "idle in transaction" connection leaks that exhausted the pool on
    election day (2026-03-05).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            # Close the transaction so the connection returns to the pool
            # immediately, not after response serialization/sending.
            await session.close()
