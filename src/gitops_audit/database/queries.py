"""Database queries for deployments."""

from typing import List, Optional
from sqlalchemy import select, desc, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from gitops_audit.database.models import Deployment


async def get_deployments_by_app(
    session: AsyncSession, app_name: str, limit: int = 10
) -> List[Deployment]:
    """Get recent deployments for a specific app."""
    result = await session.execute(
        select(Deployment)
        .where(Deployment.app_name == app_name)
        .order_by(desc(Deployment.deployed_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_all_deployments(session: AsyncSession, limit: int = 20) -> List[Deployment]:
    """Get all recent deployments across all apps."""
    result = await session.execute(
        select(Deployment).order_by(desc(Deployment.deployed_at)).limit(limit)
    )
    return list(result.scalars().all())


async def get_deployment_by_id(session: AsyncSession, deployment_id: int) -> Optional[Deployment]:
    """Get a specific deployment by ID."""
    result = await session.execute(select(Deployment).where(Deployment.id == deployment_id))
    return result.scalar_one_or_none()


async def get_apps_list(session: AsyncSession) -> List[str]:
    """Get list of all tracked applications."""
    result = await session.execute(
        select(distinct(Deployment.app_name)).order_by(Deployment.app_name)
    )
    return list(result.scalars().all())
