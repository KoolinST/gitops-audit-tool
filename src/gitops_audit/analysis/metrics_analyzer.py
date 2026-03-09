"""Analyze metrics to detect deployment issues."""

from typing import Optional, Dict, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gitops_audit.database.models import MetricsSnapshot


class MetricsAnalyzer:
    """Analyzes metrics to detect anomalies and deployment impact."""

    THRESHOLDS = {
        "error_rate_increase": 100,
        "latency_increase": 50,
        "request_rate_drop": 30,
        "cpu_increase": 100,
        "memory_increase": 50,
    }

    @staticmethod
    async def get_snapshots(
        session: AsyncSession, deployment_id: int
    ) -> Tuple[Optional[MetricsSnapshot], Optional[MetricsSnapshot]]:
        """Get before/after snapshots for a deployment."""

        result = await session.execute(
            select(MetricsSnapshot)
            .where(
                MetricsSnapshot.deployment_id == deployment_id,
                MetricsSnapshot.snapshot_type == "before",
            )
            .limit(1)
        )
        before = result.scalar_one_or_none()

        result = await session.execute(
            select(MetricsSnapshot)
            .where(
                MetricsSnapshot.deployment_id == deployment_id,
                MetricsSnapshot.snapshot_type == "after",
            )
            .limit(1)
        )
        after = result.scalar_one_or_none()

        return before, after

    @staticmethod
    def calculate_change(before: float, after: float) -> Dict[str, float]:
        """Calculate percentage change and absolute difference."""
        if before is None or after is None:
            return {"percent_change": None, "absolute_change": None}

        if before == 0:
            if after == 0:
                return {"percent_change": 0.0, "absolute_change": 0.0}
            else:
                return {"percent_change": float("inf"), "absolute_change": after}

        percent_change = ((after - before) / before) * 100
        absolute_change = after - before

        return {
            "percent_change": round(percent_change, 2),
            "absolute_change": round(absolute_change, 4),
        }

    @classmethod
    async def analyze_deployment(cls, session: AsyncSession, deployment_id: int) -> Dict:
        """
        Analyze a deployment's metric changes.

        Returns:
            Dict with analysis results including:
            - metrics_before: Before snapshot values
            - metrics_after: After snapshot values
            - changes: Calculated changes
            - issues: Detected issues
            - severity: Overall severity (healthy, warning, critical)
        """
        before, after = await cls.get_snapshots(session, deployment_id)

        if not before or not after:
            return {"has_metrics": False, "error": "Missing metrics snapshots"}

        metrics_before = {
            "error_rate": before.error_rate,
            "request_rate": before.request_rate,
            "latency_p50": before.latency_p50,
            "latency_p95": before.latency_p95,
            "cpu_usage": before.cpu_usage,
            "memory_usage": before.memory_usage,
        }

        metrics_after = {
            "error_rate": after.error_rate,
            "request_rate": after.request_rate,
            "latency_p50": after.latency_p50,
            "latency_p95": after.latency_p95,
            "cpu_usage": after.cpu_usage,
            "memory_usage": after.memory_usage,
        }

        changes = {}
        issues = []

        if before.error_rate is not None and after.error_rate is not None:
            change = cls.calculate_change(before.error_rate, after.error_rate)
            changes["error_rate"] = change

            if (
                change["percent_change"]
                and change["percent_change"] > cls.THRESHOLDS["error_rate_increase"]
            ):
                issues.append(
                    {
                        "metric": "error_rate",
                        "severity": "critical",
                        "message": f"Error rate increased by {change['percent_change']}%",
                        "before": before.error_rate,
                        "after": after.error_rate,
                    }
                )

        if before.request_rate is not None and after.request_rate is not None:
            change = cls.calculate_change(before.request_rate, after.request_rate)
            changes["request_rate"] = change

            if (
                change["percent_change"]
                and change["percent_change"] < -cls.THRESHOLDS["request_rate_drop"]
            ):
                issues.append(
                    {
                        "metric": "request_rate",
                        "severity": "warning",
                        "message": f"Request rate dropped by {abs(change['percent_change'])}%",
                        "before": before.request_rate,
                        "after": after.request_rate,
                    }
                )

        if before.latency_p95 is not None and after.latency_p95 is not None:
            change = cls.calculate_change(before.latency_p95, after.latency_p95)
            changes["latency_p95"] = change

            if (
                change["percent_change"]
                and change["percent_change"] > cls.THRESHOLDS["latency_increase"]
            ):
                issues.append(
                    {
                        "metric": "latency_p95",
                        "severity": "warning",
                        "message": f"P95 latency increased by {change['percent_change']}%",
                        "before": before.latency_p95,
                        "after": after.latency_p95,
                    }
                )

        if before.latency_p50 is not None and after.latency_p50 is not None:
            change = cls.calculate_change(before.latency_p50, after.latency_p50)
            changes["latency_p50"] = change

            if (
                change["percent_change"]
                and change["percent_change"] > cls.THRESHOLDS["latency_increase"]
            ):
                issues.append(
                    {
                        "metric": "latency_p50",
                        "severity": "warning",
                        "message": f"P50 latency increased by {change['percent_change']}%",
                        "before": before.latency_p50,
                        "after": after.latency_p50,
                    }
                )

        if before.cpu_usage is not None and after.cpu_usage is not None:
            change = cls.calculate_change(before.cpu_usage, after.cpu_usage)
            changes["cpu_usage"] = change

            if (
                change["percent_change"]
                and change["percent_change"] > cls.THRESHOLDS["cpu_increase"]
            ):
                issues.append(
                    {
                        "metric": "cpu_usage",
                        "severity": "warning",
                        "message": f"CPU usage increased by {change['percent_change']}%",
                        "before": before.cpu_usage,
                        "after": after.cpu_usage,
                    }
                )

        if before.memory_usage is not None and after.memory_usage is not None:
            change = cls.calculate_change(before.memory_usage, after.memory_usage)
            changes["memory_usage"] = change

            if (
                change["percent_change"]
                and change["percent_change"] > cls.THRESHOLDS["memory_increase"]
            ):
                issues.append(
                    {
                        "metric": "memory_usage",
                        "severity": "warning",
                        "message": f"Memory usage increased by {change['percent_change']}%",
                        "before": before.memory_usage,
                        "after": after.memory_usage,
                    }
                )

        if any(i["severity"] == "critical" for i in issues):
            severity = "critical"
        elif any(i["severity"] == "warning" for i in issues):
            severity = "warning"
        else:
            severity = "healthy"

        return {
            "has_metrics": True,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "changes": changes,
            "issues": issues,
            "severity": severity,
            "snapshot_before_time": before.snapshot_time,
            "snapshot_after_time": after.snapshot_time,
        }
