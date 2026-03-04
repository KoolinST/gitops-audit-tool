"""Pydantic schemas for API responses."""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class DeploymentBase(BaseModel):
    id: int
    app_name: str
    namespace: str
    commit_sha: str
    deployed_at: datetime
    deployed_by: Optional[str] = None
    sync_status: Optional[str] = None
    health_status: Optional[str] = None
    argocd_revision: Optional[str] = None
    model_config = {"from_attributes": True}


class DeploymentList(BaseModel):
    deployments: List[DeploymentBase]
    total: int


class MetricValue(BaseModel):
    before: Optional[float] = None
    after: Optional[float] = None
    percent_change: Optional[float] = None


class DeploymentMetrics(BaseModel):
    deployment_id: int
    has_metrics: bool
    severity: Optional[str] = None
    error_rate: Optional[MetricValue] = None
    request_rate: Optional[MetricValue] = None
    latency_p50: Optional[MetricValue] = None
    latency_p95: Optional[MetricValue] = None
    cpu_usage: Optional[MetricValue] = None
    memory_usage: Optional[MetricValue] = None
    issues: List[dict] = []


class AppSummary(BaseModel):
    app_name: str
    total_deployments: int
    last_deployed: Optional[datetime] = None


class AppList(BaseModel):
    apps: List[AppSummary]
    total: int


class RollbackRecord(BaseModel):
    id: int
    deployment_id: int
    rolled_back_at: datetime
    rolled_back_by: str
    reason: Optional[str] = None
    target_commit_sha: str
    success: bool
    model_config = {"from_attributes": True}


class HealthCheck(BaseModel):
    status: str
    database: str
    prometheus: str
    version: str
