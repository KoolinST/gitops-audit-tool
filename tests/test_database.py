"""Test database connection."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from gitops_audit.config.settings import settings


@pytest.fixture(scope="function")
async def db_session():
    """Create a fresh database session for each test."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_database_connection(db_session):
    """Test that we can connect to database."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_tables_exist(db_session):
    """Test that tables were created."""
    result = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    tables = {row[0] for row in result}

    assert "deployments" in tables
    assert "git_commits" in tables
    assert "metrics_snapshots" in tables
    assert "rollbacks" in tables
