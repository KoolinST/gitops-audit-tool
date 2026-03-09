"""Watches ArgoCD Application resources for deployment events."""

import asyncio
from datetime import datetime
from kubernetes import client, config, watch
import structlog

from gitops_audit.database.models import Deployment, GitCommit, MetricsSnapshot
from gitops_audit.database.connection import AsyncSessionLocal
from gitops_audit.integrations.github import get_github_client
from gitops_audit.integrations.prometheus import get_prometheus_client
from gitops_audit.integrations.slack import get_slack_client
from gitops_audit.analysis.metrics_analyzer import MetricsAnalyzer

logger = structlog.get_logger()


class ArgoCDWatcher:
    """Watches ArgoCD Application CRDs for deployment events."""

    def __init__(self):
        """Initialize the watcher."""
        try:
            config.load_incluster_config()
            logger.info("loaded_kubernetes_config", type="in-cluster")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("loaded_kubernetes_config", type="local")

        self.custom_api = client.CustomObjectsApi()
        self.group = "argoproj.io"
        self.version = "v1alpha1"
        self.plural = "applications"
        self.namespace = "argocd"
        self.github_client = get_github_client()
        self.prometheus_client = get_prometheus_client()
        self.slack_client = get_slack_client()
        self._processing_locks: dict = {}

    async def watch_applications(self):
        """Watch for ArgoCD Application events."""
        logger.info("starting_argocd_watcher", namespace=self.namespace)

        w = watch.Watch()

        try:
            for event in w.stream(
                self.custom_api.list_namespaced_custom_object,
                group=self.group,
                version=self.version,
                namespace=self.namespace,
                plural=self.plural,
                timeout_seconds=0,
            ):
                event_type = event["type"]
                app = event["object"]

                app_name = app["metadata"]["name"]

                logger.debug(
                    "argocd_event_detected",
                    event_type=event_type,
                    app_name=app_name,
                )

                if event_type in ["ADDED", "MODIFIED"]:
                    await self._handle_application(app)

        except Exception as e:
            logger.error("watcher_error", error=str(e), error_type=type(e).__name__)
            raise

    async def _handle_application(self, app: dict):
        """Process an ArgoCD Application resource."""
        metadata = app["metadata"]
        status = app.get("status", {})
        spec = app.get("spec", {})

        app_name = metadata["name"]
        if app_name not in self._processing_locks:
            self._processing_locks[app_name] = asyncio.Lock()

        async with self._processing_locks[app_name]:
            namespace = metadata.get("namespace", "argocd")
            dest_namespace = spec.get("destination", {}).get("namespace", "default")

            sync_status = status.get("sync", {}).get("status")
            health_status = status.get("health", {}).get("status")

            operation_state = status.get("operationState", {})
            sync_result = operation_state.get("syncResult", {})
            revision = sync_result.get("revision", "")

            if not revision:
                revision = status.get("sync", {}).get("revision", "")

            git_url = spec.get("source", {}).get("repoURL", "")

            if sync_status == "Synced" and health_status in ["Healthy", "Progressing"]:

                if not revision:
                    logger.warning(
                        "no_revision_found",
                        app_name=app_name,
                        sync_status=sync_status,
                        health_status=health_status,
                    )
                    return

                if await self._is_duplicate_deployment(app_name, revision):
                    logger.debug(
                        "skipping_duplicate_deployment",
                        app_name=app_name,
                        revision=revision[:8] if revision else "unknown",
                    )
                    return

                logger.info(
                    "recording_deployment",
                    app_name=app_name,
                    revision=revision[:8] if revision else "unknown",
                    health_status=health_status,
                )

                before_metrics = await self._capture_metrics(app_name, dest_namespace)

                commit_info, pr_info = await self._fetch_git_metadata(git_url, revision)

                deployment_id = await self._record_deployment(
                    app_name=app_name,
                    namespace=namespace,
                    dest_namespace=dest_namespace,
                    commit_sha=revision[:40] if revision else "unknown",
                    sync_status=sync_status,
                    health_status=health_status,
                    argocd_revision=revision,
                    commit_info=commit_info,
                    pr_info=pr_info,
                )

                if before_metrics and deployment_id:
                    await self._store_metrics_snapshot(deployment_id, "before", before_metrics)

                await asyncio.sleep(30)

                after_metrics = await self._capture_metrics(app_name, dest_namespace)
                if after_metrics and deployment_id:
                    await self._store_metrics_snapshot(deployment_id, "after", after_metrics)

                await self._analyze_and_alert(
                    deployment_id=deployment_id,
                    app_name=app_name,
                    commit_sha=revision,
                    dest_namespace=dest_namespace,
                    commit_info=commit_info,
                )

    async def _is_duplicate_deployment(self, app_name: str, revision: str) -> bool:
        """Check if this deployment was already recorded."""
        if not revision:
            return False

        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(Deployment)
                .where(Deployment.app_name == app_name)
                .order_by(Deployment.deployed_at.desc())
                .limit(1)
            )
            last_deployment = result.scalar_one_or_none()

            if last_deployment and last_deployment.commit_sha == revision[:40]:
                return True

        return False

    async def _capture_metrics(self, app_name: str, namespace: str) -> dict:
        """Capture current metrics for an app."""
        try:
            metrics = await self.prometheus_client.get_app_metrics(app_name, namespace)
            logger.info(
                "metrics_captured",
                app_name=app_name,
                namespace=namespace,
                metrics_available=sum(1 for v in metrics.values() if v is not None),
            )
            return metrics
        except Exception as e:
            logger.error("metrics_capture_failed", app_name=app_name, error=str(e))
            return {}

    async def _fetch_git_metadata(self, git_url: str, commit_sha: str) -> tuple:
        """Fetch commit and PR info from GitHub (async wrapper)."""
        if not git_url or not commit_sha:
            return None, None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.github_client.get_commit_and_pr_info, git_url, commit_sha
        )

    async def _record_deployment(
        self,
        app_name: str,
        namespace: str,
        dest_namespace: str,
        commit_sha: str,
        sync_status: str,
        health_status: str,
        argocd_revision: str,
        commit_info: dict = None,
        pr_info: dict = None,
    ) -> int:
        """Record deployment to database and return deployment ID."""
        async with AsyncSessionLocal() as session:
            if commit_info:
                await self._record_git_commit(session, commit_info, pr_info)

            deployment = Deployment(
                app_name=app_name,
                namespace=dest_namespace,
                commit_sha=commit_sha,
                deployed_at=datetime.utcnow(),
                deployed_by=commit_info.get("author") if commit_info else None,
                sync_status=sync_status,
                health_status=health_status,
                argocd_revision=argocd_revision,
            )

            session.add(deployment)
            await session.commit()
            await session.refresh(deployment)

            logger.info(
                "deployment_recorded",
                deployment_id=deployment.id,
                app_name=app_name,
                commit_sha=commit_sha[:8],
                has_git_metadata=commit_info is not None,
            )

            return deployment.id

    async def _record_git_commit(self, session, commit_info: dict, pr_info: dict = None):
        """Record or update Git commit metadata."""
        from sqlalchemy import select

        result = await session.execute(select(GitCommit).where(GitCommit.sha == commit_info["sha"]))
        existing = result.scalar_one_or_none()

        if existing:
            if pr_info:
                existing.pr_number = pr_info.get("number")
                existing.pr_approved_by = pr_info.get("approved_by")
                existing.pr_url = pr_info.get("url")
        else:
            committed_at = commit_info["committed_at"]
            if hasattr(committed_at, "tzinfo") and committed_at.tzinfo is not None:
                committed_at = committed_at.replace(tzinfo=None)

            git_commit = GitCommit(
                sha=commit_info["sha"],
                author=commit_info["author"],
                author_email=commit_info["author_email"],
                commit_message=commit_info["message"],
                committed_at=committed_at,
                pr_number=pr_info.get("number") if pr_info else None,
                pr_approved_by=pr_info.get("approved_by") if pr_info else None,
                pr_url=pr_info.get("url") if pr_info else None,
            )
            session.add(git_commit)

        await session.commit()

    async def _store_metrics_snapshot(self, deployment_id: int, snapshot_type: str, metrics: dict):
        """Store metrics snapshot in database."""
        async with AsyncSessionLocal() as session:
            snapshot = MetricsSnapshot(
                deployment_id=deployment_id,
                snapshot_time=datetime.utcnow(),
                snapshot_type=snapshot_type,
                error_rate=metrics.get("error_rate"),
                latency_p50=metrics.get("latency_p50"),
                latency_p95=metrics.get("latency_p95"),
                latency_p99=None,
                request_rate=metrics.get("request_rate"),
                cpu_usage=metrics.get("cpu_usage"),
                memory_usage=metrics.get("memory_usage"),
            )

            session.add(snapshot)
            await session.commit()

    async def _analyze_and_alert(
        self,
        deployment_id: int,
        app_name: str,
        commit_sha: str,
        dest_namespace: str,
        commit_info: dict = None,
    ):
        """Analyze deployment metrics and send Slack alert if needed."""
        try:
            async with AsyncSessionLocal() as session:
                analysis = await MetricsAnalyzer.analyze_deployment(session, deployment_id)

            if not analysis.get("has_metrics"):
                return

            if analysis["severity"] in ("warning", "critical"):
                await self.slack_client.send_deployment_alert(
                    app_name=app_name,
                    deployment_id=deployment_id,
                    commit_sha=commit_sha,
                    namespace=dest_namespace,
                    severity=analysis["severity"],
                    issues=analysis["issues"],
                    cpu_before=analysis["metrics_before"].get("cpu_usage"),
                    cpu_after=analysis["metrics_after"].get("cpu_usage"),
                    memory_before=analysis["metrics_before"].get("memory_usage"),
                    memory_after=analysis["metrics_after"].get("memory_usage"),
                )
            else:
                await self.slack_client.send_deployment_success(
                    app_name=app_name,
                    deployment_id=deployment_id,
                    commit_sha=commit_sha,
                    namespace=dest_namespace,
                    deployed_by=commit_info.get("author") if commit_info else None,
                    cpu_after=analysis["metrics_after"].get("cpu_usage"),
                    memory_after=analysis["metrics_after"].get("memory_usage"),
                )

        except Exception as e:
            logger.error("slack_alert_failed", error=str(e), deployment_id=deployment_id)


async def main():
    """Main entry point for watcher."""
    from gitops_audit.config.logging import configure_logging
    from gitops_audit.config.settings import settings

    configure_logging(settings.log_level)

    watcher = ArgoCDWatcher()
    await watcher.watch_applications()


if __name__ == "__main__":
    asyncio.run(main())
