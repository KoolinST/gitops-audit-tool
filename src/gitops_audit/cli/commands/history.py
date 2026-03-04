"""View deployment history."""

import asyncio
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich import box

from gitops_audit.database.connection import AsyncSessionLocal
from gitops_audit.database.queries import get_deployments_by_app, get_all_deployments

console = Console()


async def show_history_async(app_name: Optional[str], limit: int):
    """Async function to fetch and display deployment history."""
    async with AsyncSessionLocal() as session:
        if app_name:
            deployments = await get_deployments_by_app(session, app_name, limit)
            title = f"Deployment History: {app_name}"
        else:
            deployments = await get_all_deployments(session, limit)
            title = "All Deployments"
        
        if not deployments:
            if app_name:
                console.print(f"[yellow]No deployments found for app: {app_name}[/yellow]")
            else:
                console.print("[yellow]No deployments found in database.[/yellow]")
            return

        table = Table(
            title=title,
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )
        
        table.add_column("ID", style="dim", width=6)
        table.add_column("App Name", style="magenta")
        table.add_column("Deployed At", style="green")
        table.add_column("Commit", style="yellow", width=10)
        table.add_column("Health")

        health_formats = {
            "Healthy": ("[green]●[/green]", "green"),
            "Progressing": ("[yellow]◐[/yellow]", "yellow"),
            "Degraded": ("[red]▲[/red]", "red"),
            "Suspended": ("[dim]■[/dim]", "dim"),
            "Missing": ("[red]✗[/red]", "red"),
            "Unknown": ("[dim]?[/dim]", "dim"),
        }

        for dep in deployments:
            symbol, color = health_formats.get(
                dep.health_status, 
                ("[dim]?[/dim]", "dim")
            )
            status_text = dep.health_status or "Unknown"
            health_display = f"{symbol} [{color}]{status_text}[/{color}]"

            commit_short = dep.commit_sha[:8] if dep.commit_sha else "unknown"
            deployed_at = dep.deployed_at.strftime("%Y-%m-%d %H:%M:%S")
            
            table.add_row(
                str(dep.id),
                dep.app_name,
                deployed_at,
                commit_short,
                health_display,
            )
        
        console.print()
        console.print(table)
        console.print()
        console.print(f"[dim]Showing {len(deployments)} deployment(s)[/dim]")


def history_command(
    app_name: Optional[str] = typer.Argument(
        None,
        help="Application name to filter by (optional)"
    ),
    limit: int = typer.Option(
        10,
        "--limit", "-l",
        help="Maximum number of deployments to show"
    ),
):
    """View deployment history."""
    asyncio.run(show_history_async(app_name, limit))
