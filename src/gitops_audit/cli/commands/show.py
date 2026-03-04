"""Show command - view detailed deployment information."""

import asyncio
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from sqlalchemy import select

from gitops_audit.database.connection import AsyncSessionLocal
from gitops_audit.database.queries import get_deployment_by_id
from gitops_audit.database.models import GitCommit

console = Console()


async def show_deployment_async(deployment_id: int):
    """Async function to fetch and display deployment details."""
    async with AsyncSessionLocal() as session:
        deployment = await get_deployment_by_id(session, deployment_id)
        
        if not deployment:
            console.print(f"[red]✗ Deployment #{deployment_id} not found[/red]")
            raise typer.Exit(1)

        git_commit = None
        if deployment.commit_sha and deployment.commit_sha != "unknown":
            result = await session.execute(
                select(GitCommit).where(GitCommit.sha == deployment.commit_sha)
            )
            git_commit = result.scalar_one_or_none()

        health_formats = {
            "Healthy": ("[green]●[/green]", "green"),
            "Progressing": ("[yellow]◐[/yellow]", "yellow"),
            "Degraded": ("[red]▲[/red]", "red"),
            "Suspended": ("[dim]■[/dim]", "dim"),
            "Missing": ("[red]✗[/red]", "red"),
            "Unknown": ("[dim]?[/dim]", "dim"),
        }
        
        symbol, color = health_formats.get(
            deployment.health_status,
            ("[dim]?[/dim]", "dim")
        )
        status_text = deployment.health_status or "Unknown"
        health_display = f"{symbol} [{color}]{status_text}[/{color}]"

        info = Table.grid(padding=(0, 2))
        info.add_column(style="bold cyan", justify="right")
        info.add_column(style="white")
        
        info.add_row("ID:", str(deployment.id))
        info.add_row("App Name:", deployment.app_name)
        info.add_row("Namespace:", deployment.namespace)
        info.add_row("Deployed At:", deployment.deployed_at.strftime("%Y-%m-%d %H:%M:%S UTC"))
        info.add_row("", "")

        if git_commit:
            info.add_row("Commit SHA:", git_commit.sha[:40])
            info.add_row("Author:", git_commit.author)
            info.add_row("Author Email:", git_commit.author_email or "unknown")
            info.add_row("Message:", git_commit.commit_message.split('\n')[0][:80])
            info.add_row("Committed:", git_commit.committed_at.strftime("%Y-%m-%d %H:%M:%S UTC"))

            if git_commit.pr_number:
                info.add_row("", "")
                info.add_row("PR Number:", f"#{git_commit.pr_number}")
                if git_commit.pr_approved_by:
                    info.add_row("Approved By:", git_commit.pr_approved_by)
                if git_commit.pr_url:
                    info.add_row("PR URL:", git_commit.pr_url)
        else:
            info.add_row("Commit SHA:", deployment.commit_sha or "unknown")
            info.add_row("Git Branch:", deployment.git_branch or "unknown")
            info.add_row("Deployed By:", deployment.deployed_by or "unknown")

        info.add_row("", "")
        info.add_row("Sync Status:", deployment.sync_status or "unknown")
        info.add_row("Health Status:", health_display)

        panel = Panel(
            info,
            title=f"[bold]Deployment #{deployment.id}: {deployment.app_name}[/bold]",
            border_style="cyan",
            box=box.ROUNDED,
        )
        
        console.print()
        console.print(panel)
        console.print()


def show_command(
    deployment_id: int = typer.Argument(
        ...,
        help="Deployment ID to display"
    ),
):
    """Show detailed information about a specific deployment."""
    asyncio.run(show_deployment_async(deployment_id))
