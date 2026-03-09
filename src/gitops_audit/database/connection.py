"""Database connection management."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from gitops_audit.config.settings import settings


def get_engine():
    """Create async engine."""
    return create_async_engine(
        settings.database_url,
        echo=settings.log_level == "DEBUG",
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )


engine = get_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session (for dependency injection)."""
    async with AsyncSessionLocal() as session:
        yield session
