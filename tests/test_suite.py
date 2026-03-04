"""Comprehensive test suite for gitops-audit."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from gitops_audit.config.settings import settings
from gitops_audit.database.models import Deployment, MetricsSnapshot
from gitops_audit.database.queries import (
    get_deployment_by_id,
    get_deployments_by_app,
    get_all_deployments,
    get_apps_list,
)
from gitops_audit.analysis.metrics_analyzer import MetricsAnalyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
async def db_session():
    """Create a fresh database session for each test."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def sample_deployment(db_session):
    """Create a sample deployment for testing."""
    deployment = Deployment(
        app_name="test-app",
        namespace="default",
        commit_sha="abc123def456abc123def456abc123def456abc1",
        deployed_at=datetime(2026, 3, 1, 12, 0, 0),
        deployed_by="test-user",
        sync_status="Synced",
        health_status="Healthy",
        argocd_revision="abc123def456abc123def456abc123def456abc1",
    )
    db_session.add(deployment)
    await db_session.commit()
    await db_session.refresh(deployment)
    yield deployment

    await db_session.delete(deployment)
    await db_session.commit()


@pytest.fixture
async def sample_snapshots(db_session, sample_deployment):
    """Create before/after metric snapshots for a deployment."""
    before = MetricsSnapshot(
        deployment_id=sample_deployment.id,
        snapshot_time=datetime(2026, 3, 1, 12, 0, 0),
        snapshot_type="before",
        error_rate=0.01,
        request_rate=100.0,
        latency_p50=0.05,
        latency_p95=0.1,
        cpu_usage=0.2,
        memory_usage=256.0,
    )
    after = MetricsSnapshot(
        deployment_id=sample_deployment.id,
        snapshot_time=datetime(2026, 3, 1, 12, 0, 30),
        snapshot_type="after",
        error_rate=0.012,
        request_rate=98.0,
        latency_p50=0.055,
        latency_p95=0.11,
        cpu_usage=0.22,
        memory_usage=260.0,
    )
    db_session.add(before)
    db_session.add(after)
    await db_session.commit()
    yield before, after

    await db_session.delete(before)
    await db_session.delete(after)
    await db_session.commit()


# ---------------------------------------------------------------------------
# Database connection tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_database_connection(db_session):
    """Test that we can connect to the database."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_tables_exist(db_session):
    """Test that all required tables were created."""
    result = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    tables = {row[0] for row in result}

    assert "deployments" in tables
    assert "git_commits" in tables
    assert "metrics_snapshots" in tables
    assert "rollbacks" in tables


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_deployment_by_id(db_session, sample_deployment):
    """Test fetching a deployment by ID."""
    result = await get_deployment_by_id(db_session, sample_deployment.id)

    assert result is not None
    assert result.id == sample_deployment.id
    assert result.app_name == "test-app"
    assert result.commit_sha == "abc123def456abc123def456abc123def456abc1"


@pytest.mark.asyncio
async def test_get_deployment_by_id_not_found(db_session):
    """Test fetching a non-existent deployment returns None."""
    result = await get_deployment_by_id(db_session, 999999)
    assert result is None


@pytest.mark.asyncio
async def test_get_deployments_by_app(db_session, sample_deployment):
    """Test fetching deployments filtered by app name."""
    results = await get_deployments_by_app(db_session, "test-app")

    assert len(results) >= 1
    assert all(d.app_name == "test-app" for d in results)


@pytest.mark.asyncio
async def test_get_deployments_by_app_not_found(db_session):
    """Test fetching deployments for non-existent app returns empty list."""
    results = await get_deployments_by_app(db_session, "nonexistent-app-xyz")
    assert results == []


@pytest.mark.asyncio
async def test_get_all_deployments(db_session, sample_deployment):
    """Test fetching all deployments."""
    results = await get_all_deployments(db_session, limit=50)

    assert len(results) >= 1
    app_names = [d.app_name for d in results]
    assert "test-app" in app_names


@pytest.mark.asyncio
async def test_get_all_deployments_limit(db_session):
    """Test that limit is respected."""
    results = await get_all_deployments(db_session, limit=3)
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_get_apps_list(db_session, sample_deployment):
    """Test fetching list of distinct app names."""
    results = await get_apps_list(db_session)

    assert isinstance(results, list)
    assert "test-app" in results
    assert len(results) == len(set(results))


# ---------------------------------------------------------------------------
# MetricsAnalyzer unit tests
# ---------------------------------------------------------------------------

class TestCalculateChange:
    """Tests for MetricsAnalyzer.calculate_change."""

    def test_positive_change(self):
        result = MetricsAnalyzer.calculate_change(100.0, 150.0)
        assert result["percent_change"] == 50.0
        assert result["absolute_change"] == 50.0

    def test_negative_change(self):
        result = MetricsAnalyzer.calculate_change(100.0, 75.0)
        assert result["percent_change"] == -25.0
        assert result["absolute_change"] == -25.0

    def test_no_change(self):
        result = MetricsAnalyzer.calculate_change(100.0, 100.0)
        assert result["percent_change"] == 0.0
        assert result["absolute_change"] == 0.0

    def test_zero_before_zero_after(self):
        result = MetricsAnalyzer.calculate_change(0.0, 0.0)
        assert result["percent_change"] == 0.0
        assert result["absolute_change"] == 0.0

    def test_zero_before_nonzero_after(self):
        result = MetricsAnalyzer.calculate_change(0.0, 5.0)
        assert result["percent_change"] == float("inf")
        assert result["absolute_change"] == 5.0

    def test_none_values(self):
        result = MetricsAnalyzer.calculate_change(None, 5.0)
        assert result["percent_change"] is None
        assert result["absolute_change"] is None


@pytest.mark.asyncio
async def test_analyze_deployment_healthy(db_session, sample_deployment, sample_snapshots):
    """Test analysis returns healthy when metrics are within thresholds."""
    analysis = await MetricsAnalyzer.analyze_deployment(db_session, sample_deployment.id)

    assert analysis["has_metrics"] is True
    assert analysis["severity"] == "healthy"
    assert isinstance(analysis["issues"], list)
    assert isinstance(analysis["changes"], dict)


@pytest.mark.asyncio
async def test_analyze_deployment_critical_error_rate(db_session):
    """Test analysis detects critical error rate spike."""
    deployment = Deployment(
        app_name="error-spike-app",
        namespace="default",
        commit_sha="aaa111bbb222ccc333ddd444eee555fff666aaa1",
        deployed_at=datetime.utcnow(),
        sync_status="Synced",
        health_status="Healthy",
        argocd_revision="aaa111bbb222ccc333ddd444eee555fff666aaa1",
    )
    db_session.add(deployment)
    await db_session.commit()
    await db_session.refresh(deployment)

    before = MetricsSnapshot(
        deployment_id=deployment.id,
        snapshot_time=datetime.utcnow(),
        snapshot_type="before",
        error_rate=0.01,
    )
    after = MetricsSnapshot(
        deployment_id=deployment.id,
        snapshot_time=datetime.utcnow(),
        snapshot_type="after",
        error_rate=0.05,
    )
    db_session.add(before)
    db_session.add(after)
    await db_session.commit()

    analysis = await MetricsAnalyzer.analyze_deployment(db_session, deployment.id)

    assert analysis["has_metrics"] is True
    assert analysis["severity"] == "critical"
    assert any(i["metric"] == "error_rate" for i in analysis["issues"])

    await db_session.delete(before)
    await db_session.delete(after)
    await db_session.delete(deployment)
    await db_session.commit()


@pytest.mark.asyncio
async def test_analyze_deployment_no_snapshots(db_session, sample_deployment):
    """Test analysis returns has_metrics=False when snapshots are missing."""
    analysis = await MetricsAnalyzer.analyze_deployment(db_session, 999999)

    assert analysis["has_metrics"] is False
    assert "error" in analysis


# ---------------------------------------------------------------------------
# PrometheusClient tests (mocked HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prometheus_get_app_metrics_success():
    """Test Prometheus client parses successful metric response."""
    from gitops_audit.integrations.prometheus import PrometheusClient

    mock_response = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [1234567890, "0.0042"]}],
        },
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response_obj = MagicMock()
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response_obj

        client = PrometheusClient(base_url="http://fake-prometheus:9090")
        metrics = await client.get_app_metrics("test-app", "default")

    assert isinstance(metrics, dict)


@pytest.mark.asyncio
async def test_prometheus_get_app_metrics_connection_failure():
    """Test Prometheus client returns None on connection failure."""
    from gitops_audit.integrations.prometheus import PrometheusClient
    import httpx

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        client = PrometheusClient(base_url="http://fake-prometheus:9090")
        result = await client.query("up")

    assert result is None


@pytest.mark.asyncio
async def test_prometheus_test_connection_success():
    """Test Prometheus connection check returns True on 200."""
    from gitops_audit.integrations.prometheus import PrometheusClient

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        client = PrometheusClient(base_url="http://fake-prometheus:9090")
        result = await client.test_connection()

    assert result is True


@pytest.mark.asyncio
async def test_prometheus_test_connection_failure():
    """Test Prometheus connection check returns False on error."""
    from gitops_audit.integrations.prometheus import PrometheusClient
    import httpx

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = httpx.ConnectError("refused")

        client = PrometheusClient(base_url="http://fake-prometheus:9090")
        result = await client.test_connection()

    assert result is False


# ---------------------------------------------------------------------------
# SlackClient tests (mocked HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slack_disabled_when_no_webhook():
    """Test Slack client is disabled when no webhook URL is configured."""
    from gitops_audit.integrations.slack import SlackClient

    client = SlackClient(webhook_url="")
    assert client.enabled is False

    result = await client.send_deployment_success(
        app_name="test-app",
        deployment_id=1,
        commit_sha="abc123",
        namespace="default",
    )
    assert result is False


@pytest.mark.asyncio
async def test_slack_sends_alert():
    """Test Slack client sends alert payload correctly."""
    from gitops_audit.integrations.slack import SlackClient

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        client = SlackClient(webhook_url="https://hooks.slack.com/fake")
        result = await client.send_deployment_alert(
            app_name="test-app",
            deployment_id=1,
            commit_sha="abc123def",
            namespace="default",
            severity="critical",
            issues=[{"message": "Error rate increased by 400%"}],
            cpu_before=0.1,
            cpu_after=0.4,
            memory_before=256.0,
            memory_after=512.0,
        )

    assert result is True
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs[1]["json"]
    assert "attachments" in payload