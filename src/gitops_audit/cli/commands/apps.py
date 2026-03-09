"""Apps command - list all tracked applications."""

import asyncio
from rich.console import Console
from rich.table import Table
from rich import box
from sqlalchemy import func, select

from gitops_audit.database.connection import AsyncSessionLocal
from gitops_audit.database.models import Deployment

console = Console()


async def list_apps_async():
    """Async function to list all applications."""
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

        if not rows:
            console.print("[yellow]No applications found in database.[/yellow]")
            return

        table = Table(
            title="Tracked Applications",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )

        table.add_column("App Name", style="magenta")
        table.add_column("Total Deployments", style="green", justify="right")
        table.add_column("Last Deployed", style="yellow")

        for row in rows:
            last_deployed = (
                row.last_deployed.strftime("%Y-%m-%d %H:%M") if row.last_deployed else "Never"
            )
            table.add_row(
                row.app_name,
                str(row.total),
                last_deployed,
            )

        console.print()
        console.print(table)
        console.print()
        console.print(f"[dim]Tracking {len(rows)} application(s)[/dim]")


def apps_command():
    """List all tracked applications."""
    asyncio.run(list_apps_async())
