"""Slack integration for deployment alerts."""

from typing import Optional, List, Dict
import structlog
import httpx

from gitops_audit.config.settings import settings

logger = structlog.get_logger()


class SlackClient:
    """Client for sending Slack notifications via webhooks."""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or settings.slack_webhook_url
        self.enabled = bool(self.webhook_url)

        if not self.enabled:
            logger.info("slack_disabled", message="No webhook URL configured — alerts disabled")

    async def _send(self, payload: dict) -> bool:
        """Send payload to Slack webhook."""
        if not self.enabled:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
                logger.info("slack_message_sent")
                return True
        except httpx.HTTPError as e:
            logger.error("slack_http_error", error=str(e))
            return False
        except Exception as e:
            logger.error("slack_send_error", error=str(e))
            return False

    async def send_deployment_alert(
        self,
        app_name: str,
        deployment_id: int,
        commit_sha: str,
        namespace: str,
        severity: str,
        issues: List[Dict],
        cpu_before: Optional[float] = None,
        cpu_after: Optional[float] = None,
        memory_before: Optional[float] = None,
        memory_after: Optional[float] = None,
    ) -> bool:
        """Send alert when deployment causes metric degradation."""
        color = "#FF0000" if severity == "critical" else "#FFA500"
        severity_label = severity.upper()
        header = f"[{severity_label}] Deployment Issue: {app_name}"

        issues_text = (
            "\n".join(f"• {issue['message']}" for issue in issues) if issues else "Unknown issue"
        )

        metrics_lines = []
        if cpu_before is not None and cpu_after is not None:
            metrics_lines.append(f"CPU: {cpu_before:.4f} -> {cpu_after:.4f}")
        if memory_before is not None and memory_after is not None:
            metrics_lines.append(f"Memory: {memory_before:.1f}MB -> {memory_after:.1f}MB")
        metrics_text = "\n".join(metrics_lines) if metrics_lines else "No metrics available"

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": header,
                            },
                        },
                        {
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": f"*App:*\n{app_name}"},
                                {"type": "mrkdwn", "text": f"*Namespace:*\n{namespace}"},
                                {"type": "mrkdwn", "text": f"*Commit:*\n`{commit_sha[:8]}`"},
                                {"type": "mrkdwn", "text": f"*Deployment ID:*\n#{deployment_id}"},
                            ],
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Issues Detected:*\n{issues_text}",
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Metrics:*\n{metrics_text}",
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"*To rollback:*\n"
                                    f"`gitops-audit rollback {deployment_id} "
                                    f'--reason "Auto-detected {severity}"`'
                                ),
                            },
                        },
                        {"type": "divider"},
                    ],
                }
            ]
        }

        logger.info(
            "sending_deployment_alert",
            app_name=app_name,
            deployment_id=deployment_id,
            severity=severity,
            issues_count=len(issues),
        )
        return await self._send(payload)

    async def send_deployment_success(
        self,
        app_name: str,
        deployment_id: int,
        commit_sha: str,
        namespace: str,
        deployed_by: Optional[str] = None,
        cpu_after: Optional[float] = None,
        memory_after: Optional[float] = None,
    ) -> bool:
        """Send success notification when deployment is healthy."""
        metrics_lines = []
        if cpu_after is not None:
            metrics_lines.append(f"CPU: {cpu_after:.4f}")
        if memory_after is not None:
            metrics_lines.append(f"Memory: {memory_after:.1f}MB")
        metrics_text = " | ".join(metrics_lines) if metrics_lines else "No metrics"

        payload = {
            "attachments": [
                {
                    "color": "#36A64F",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"[OK] Deployment Healthy: {app_name}",
                            },
                        },
                        {
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": f"*App:*\n{app_name}"},
                                {"type": "mrkdwn", "text": f"*Namespace:*\n{namespace}"},
                                {"type": "mrkdwn", "text": f"*Commit:*\n`{commit_sha[:8]}`"},
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Deployed By:*\n{deployed_by or 'unknown'}",
                                },
                            ],
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"*Metrics:* {metrics_text}"},
                        },
                        {"type": "divider"},
                    ],
                }
            ]
        }

        logger.info(
            "sending_deployment_success",
            app_name=app_name,
            deployment_id=deployment_id,
        )
        return await self._send(payload)


_slack_client: Optional[SlackClient] = None


def get_slack_client() -> SlackClient:
    """Get or create Slack client singleton."""
    global _slack_client
    if _slack_client is None:
        _slack_client = SlackClient()
    return _slack_client
