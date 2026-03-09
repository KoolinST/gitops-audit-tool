"""Database models for GitOps audit system."""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Deployment(Base):
    """Tracks ArgoCD deployment events."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    git_branch: Mapped[str] = mapped_column(String(255), nullable=True)
    deployed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    deployed_by: Mapped[str] = mapped_column(String(255), nullable=True)

    # ArgoCD specific
    argocd_revision: Mapped[str] = mapped_column(String(255), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(50), nullable=True)
    health_status: Mapped[str] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class GitCommit(Base):
    """Stores Git commit metadata."""

    __tablename__ = "git_commits"

    sha: Mapped[str] = mapped_column(String(40), primary_key=True)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    author_email: Mapped[str] = mapped_column(String(255), nullable=True)
    commit_message: Mapped[str] = mapped_column(Text, nullable=False)
    committed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # GitHub/GitLab specific
    pr_number: Mapped[int] = mapped_column(Integer, nullable=True)
    pr_approved_by: Mapped[str] = mapped_column(String(255), nullable=True)
    pr_url: Mapped[str] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MetricsSnapshot(Base):
    """Stores Prometheus metrics before/after deployments."""

    __tablename__ = "metrics_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'before' or 'after'

    # Metrics
    error_rate: Mapped[float] = mapped_column(Float, nullable=True)
    latency_p50: Mapped[float] = mapped_column(Float, nullable=True)
    latency_p95: Mapped[float] = mapped_column(Float, nullable=True)
    latency_p99: Mapped[float] = mapped_column(Float, nullable=True)
    request_rate: Mapped[float] = mapped_column(Float, nullable=True)
    cpu_usage: Mapped[float] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[float] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Rollback(Base):
    """Tracks rollback operations."""

    __tablename__ = "rollbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rolled_back_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    rolled_back_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    target_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
