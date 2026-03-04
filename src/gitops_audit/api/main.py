"""FastAPI application for GitOps Audit REST API."""

from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text

from gitops_audit.api.schemas import (
    DeploymentBase,
    DeploymentList,
    DeploymentMetrics,
    MetricValue,
    AppList,
    AppSummary,
    RollbackRecord,
    HealthCheck,
)
from gitops_audit.database.connection import AsyncSessionLocal
from gitops_audit.database.models import Deployment, Rollback
from gitops_audit.database.queries import (
    get_deployment_by_id,
    get_deployments_by_app,
    get_all_deployments,
)
from gitops_audit.analysis.metrics_analyzer import MetricsAnalyzer
from gitops_audit.integrations.prometheus import get_prometheus_client

app = FastAPI(
    title="GitOps Audit API",
    description=(
        "REST API for tracking ArgoCD deployments, correlating metrics, "
        "and managing rollbacks."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthCheck, tags=["System"])
async def health_check():
    """Check connectivity to database and Prometheus."""
    db_status = "ok"
    prometheus_status = "ok"

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    try:
        prometheus = get_prometheus_client()
        connected = await prometheus.test_connection()
        prometheus_status = "ok" if connected else "error"
    except Exception:
        prometheus_status = "error"

    overall = "ok" if db_status == "ok" else "degraded"

    return HealthCheck(
        status=overall,
        database=db_status,
        prometheus=prometheus_status,
        version="0.1.0",
    )


@app.get("/api/deployments", response_model=DeploymentList, tags=["Deployments"])
async def list_deployments(
    app_name: Optional[str] = Query(None, description="Filter by app name"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
):
    """List recent deployments, optionally filtered by app name."""
    async with AsyncSessionLocal() as session:
        if app_name:
            deployments = await get_deployments_by_app(session, app_name, limit)
        else:
            deployments = await get_all_deployments(session, limit)

    return DeploymentList(
        deployments=[DeploymentBase.model_validate(d) for d in deployments],
        total=len(deployments),
    )


@app.get(
    "/api/deployments/{deployment_id}",
    response_model=DeploymentBase,
    tags=["Deployments"],
)
async def get_deployment(deployment_id: int):
    """Get detailed information about a specific deployment."""
    async with AsyncSessionLocal() as session:
        deployment = await get_deployment_by_id(session, deployment_id)

    if not deployment:
        raise HTTPException(
            status_code=404,
            detail=f"Deployment #{deployment_id} not found",
        )

    return DeploymentBase.model_validate(deployment)


@app.get(
    "/api/deployments/{deployment_id}/metrics",
    response_model=DeploymentMetrics,
    tags=["Deployments"],
)
async def get_deployment_metrics(deployment_id: int):
    """Get before/after metrics analysis for a specific deployment."""
    async with AsyncSessionLocal() as session:
        deployment = await get_deployment_by_id(session, deployment_id)
        if not deployment:
            raise HTTPException(
                status_code=404,
                detail=f"Deployment #{deployment_id} not found",
            )
        analysis = await MetricsAnalyzer.analyze_deployment(session, deployment_id)

    if not analysis.get("has_metrics"):
        return DeploymentMetrics(
            deployment_id=deployment_id,
            has_metrics=False,
        )

    def make_metric_value(metric_name: str) -> Optional[MetricValue]:
        before = analysis["metrics_before"].get(metric_name)
        after = analysis["metrics_after"].get(metric_name)
        change = analysis["changes"].get(metric_name, {})
        if before is None and after is None:
            return None
        return MetricValue(
            before=before,
            after=after,
            percent_change=change.get("percent_change"),
        )

    return DeploymentMetrics(
        deployment_id=deployment_id,
        has_metrics=True,
        severity=analysis["severity"],
        error_rate=make_metric_value("error_rate"),
        request_rate=make_metric_value("request_rate"),
        latency_p50=make_metric_value("latency_p50"),
        latency_p95=make_metric_value("latency_p95"),
        cpu_usage=make_metric_value("cpu_usage"),
        memory_usage=make_metric_value("memory_usage"),
        issues=analysis.get("issues", []),
    )


@app.get(
    "/api/deployments/{deployment_id}/rollbacks",
    response_model=list[RollbackRecord],
    tags=["Deployments"],
)
async def get_deployment_rollbacks(deployment_id: int):
    """Get rollback history for a specific deployment."""
    async with AsyncSessionLocal() as session:
        deployment = await get_deployment_by_id(session, deployment_id)
        if not deployment:
            raise HTTPException(
                status_code=404,
                detail=f"Deployment #{deployment_id} not found",
            )

        result = await session.execute(
            select(Rollback)
            .where(Rollback.deployment_id == deployment_id)
            .order_by(Rollback.rolled_back_at.desc())
        )
        rollbacks = result.scalars().all()

    return [RollbackRecord.model_validate(r) for r in rollbacks]


@app.get("/api/apps", response_model=AppList, tags=["Apps"])
async def list_apps():
    """List all tracked applications with deployment counts."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                Deployment.app_name,
                func.count(Deployment.id).label("total"),
                func.max(Deployment.deployed_at).label("last_deployed"),
            )
            .group_by(Deployment.app_name)
            .order_by(Deployment.app_name)
        )
        rows = result.all()

    apps = [
        AppSummary(
            app_name=row.app_name,
            total_deployments=row.total,
            last_deployed=row.last_deployed,
        )
        for row in rows
    ]

    return AppList(apps=apps, total=len(apps))


@app.get(
    "/api/apps/{app_name}/deployments",
    response_model=DeploymentList,
    tags=["Apps"],
)
async def get_app_deployments(
    app_name: str,
    limit: int = Query(10, ge=1, le=100),
):
    """Get deployment history for a specific application."""
    async with AsyncSessionLocal() as session:
        deployments = await get_deployments_by_app(session, app_name, limit)

    if not deployments:
        raise HTTPException(
            status_code=404,
            detail=f"No deployments found for app: {app_name}",
        )

    return DeploymentList(
        deployments=[DeploymentBase.model_validate(d) for d in deployments],
        total=len(deployments),
    )
