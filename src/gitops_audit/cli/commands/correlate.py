"""Correlate command - analyze deployment impact on metrics."""

import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich import box

from gitops_audit.database.connection import AsyncSessionLocal
from gitops_audit.database.queries import get_deployment_by_id
from gitops_audit.analysis.metrics_analyzer import MetricsAnalyzer

console = Console()


async def correlate_deployment_async(deployment_id: int):
    """Analyze deployment metrics correlation."""
    async with AsyncSessionLocal() as session:
        deployment = await get_deployment_by_id(session, deployment_id)

        if not deployment:
            console.print(f"[red]✗ Deployment #{deployment_id} not found[/red]")
            raise typer.Exit(1)

        analysis = await MetricsAnalyzer.analyze_deployment(session, deployment_id)

        if not analysis.get("has_metrics"):
            console.print(
                f"[yellow]⚠ No metrics data available for deployment #{deployment_id}[/yellow]"
            )
            console.print("[dim]Metrics are captured 30 seconds after deployment.[/dim]")
            raise typer.Exit(0)

        console.print()
        console.print(f"[bold cyan]Deployment #{deployment_id}: {deployment.app_name}[/bold cyan]")
        console.print(
            f"[dim]Deployed at: {deployment.deployed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]"
        )
        console.print()

        table = Table(
            title="Metrics Analysis",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )

        table.add_column("Metric", style="white")
        table.add_column("Before", style="green", justify="right")
        table.add_column("After", style="yellow", justify="right")
        table.add_column("Change", justify="right")

        def format_metric(name, value):
            if value is None:
                return "No data"
            if name.startswith("latency"):
                return f"{value*1000:.2f} ms"
            elif name == "memory_usage":
                return f"{value:.2f} MB"
            elif name == "error_rate":
                return f"{value:.4f}"
            else:
                return f"{value:.4f}"

        def format_change(change_data):
            if not change_data or change_data.get("percent_change") is None:
                return "[dim]N/A[/dim]"

            pct = change_data["percent_change"]

            if pct > 0:
                color = "red" if pct > 50 else "yellow"
                return f"[{color}]+{pct:.1f}%[/{color}]"
            elif pct < 0:
                return f"[green]{pct:.1f}%[/green]"
            else:
                return "[dim]0%[/dim]"

        metrics_order = [
            "error_rate",
            "request_rate",
            "latency_p50",
            "latency_p95",
            "cpu_usage",
            "memory_usage",
        ]

        for metric in metrics_order:
            before = analysis["metrics_before"].get(metric)
            after = analysis["metrics_after"].get(metric)
            change = analysis["changes"].get(metric, {})

            table.add_row(
                metric.replace("_", " ").title(),
                format_metric(metric, before),
                format_metric(metric, after),
                format_change(change),
            )

        console.print(table)
        console.print()

        issues = analysis.get("issues", [])

        if issues:
            console.print("[bold red]⚠ Issues Detected:[/bold red]")
            console.print()

            for issue in issues:
                severity_color = "red" if issue["severity"] == "critical" else "yellow"
                console.print(f"  [{severity_color}]●[/{severity_color}] {issue['message']}")

            console.print()
            console.print("[bold]Recommendation:[/bold] Consider investigating this deployment")
            console.print(
                "[dim]Run: gitops-audit show {} for full details[/dim]".format(deployment_id)
            )
        else:
            console.print("[green]✓ No significant issues detected[/green]")
            console.print("[dim]Metrics are within normal thresholds[/dim]")

        console.print()


def correlate_command(
    deployment_id: int = typer.Argument(..., help="Deployment ID to analyze"),
):
    """
    Analyze deployment's impact on system metrics.

    Shows before/after metrics comparison and detects anomalies.

    Examples:
        gitops-audit correlate 3
        gitops-audit correlate 42
    """
    asyncio.run(correlate_deployment_async(deployment_id))
