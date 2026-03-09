"""Prometheus integration for querying metrics."""

from typing import Optional, Dict, Any
from datetime import datetime
import structlog
import httpx

from gitops_audit.config.settings import settings

logger = structlog.get_logger()


class PrometheusClient:
    """Client for querying Prometheus metrics."""

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize Prometheus client.

        Args:
            base_url: Prometheus server URL (default from settings)
        """
        self.base_url = (base_url or settings.prometheus_url).rstrip("/")
        self.query_endpoint = f"{self.base_url}/api/v1/query"
        self.range_query_endpoint = f"{self.base_url}/api/v1/query_range"

    async def test_connection(self) -> bool:
        """Test connection to Prometheus."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/v1/status/config")
                return response.status_code == 200
        except Exception as e:
            logger.error("prometheus_connection_failed", error=str(e))
            return False

    async def query(self, query: str, time: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Execute instant query against Prometheus.

        Args:
            query: PromQL query string
            time: Optional timestamp for query (default: now)

        Returns:
            Query result dict or None if error
        """
        params = {"query": query}
        if time:
            params["time"] = time.timestamp()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.query_endpoint, params=params)
                response.raise_for_status()

                data = response.json()

                if data.get("status") != "success":
                    logger.warning(
                        "prometheus_query_failed",
                        query=query,
                        status=data.get("status"),
                        error=data.get("error"),
                    )
                    return None

                return data.get("data", {})

        except httpx.HTTPError as e:
            logger.error("prometheus_http_error", error=str(e), query=query)
            return None
        except Exception as e:
            logger.error("prometheus_query_error", error=str(e), query=query)
            return None

    async def get_app_metrics(
        self, app_name: str, namespace: str = "default", time: Optional[datetime] = None
    ) -> Dict[str, Optional[float]]:
        """
        Get key metrics for an application.

        Args:
            app_name: Application name
            namespace: Kubernetes namespace
            time: Optional timestamp (default: now)

        Returns:
            Dict with metric values (None if metric not available)
        """
        metrics = {}

        error_rate_query = f"""
            sum(rate(http_requests_total{{
                namespace="{namespace}",
                pod=~"{app_name}.*",
                status=~"5.."
            }}[5m]))
        """

        request_rate_query = f"""
            sum(rate(http_requests_total{{
                namespace="{namespace}",
                pod=~"{app_name}.*"
            }}[5m]))
        """

        latency_p95_query = f"""
            histogram_quantile(0.95,
                sum(rate(http_request_duration_seconds_bucket{{
                    namespace="{namespace}",
                    pod=~"{app_name}.*"
                }}[5m])) by (le)
            )
        """

        latency_p50_query = f"""
            histogram_quantile(0.50,
                sum(rate(http_request_duration_seconds_bucket{{
                    namespace="{namespace}",
                    pod=~"{app_name}.*"
                }}[5m])) by (le)
            )
        """

        cpu_query = f"""
            sum(rate(container_cpu_usage_seconds_total{{
                namespace="{namespace}",
                pod=~"{app_name}.*",
                container!=""
            }}[5m]))
        """

        memory_query = f"""
            sum(container_memory_working_set_bytes{{
                namespace="{namespace}",
                pod=~"{app_name}.*",
                container!=""
            }}) / 1024 / 1024
        """

        queries = {
            "error_rate": error_rate_query,
            "request_rate": request_rate_query,
            "latency_p95": latency_p95_query,
            "latency_p50": latency_p50_query,
            "cpu_usage": cpu_query,
            "memory_usage": memory_query,
        }

        for metric_name, query_str in queries.items():
            result = await self.query(query_str, time)

            if result and result.get("resultType") == "vector":
                results = result.get("result", [])
                if results:
                    value = results[0].get("value", [None, None])[1]
                    try:
                        metrics[metric_name] = float(value) if value else None
                    except (ValueError, TypeError):
                        metrics[metric_name] = None
                else:
                    metrics[metric_name] = None
            else:
                metrics[metric_name] = None

        logger.info(
            "fetched_app_metrics",
            app_name=app_name,
            namespace=namespace,
            metrics_found=sum(1 for v in metrics.values() if v is not None),
        )

        return metrics


_prometheus_client: Optional[PrometheusClient] = None


def get_prometheus_client() -> PrometheusClient:
    """Get or create Prometheus client singleton."""
    global _prometheus_client
    if _prometheus_client is None:
        _prometheus_client = PrometheusClient()
    return _prometheus_client
