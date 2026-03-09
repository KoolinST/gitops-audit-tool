"""Rollback command - rollback to a previous deployment."""

import asyncio
import subprocess
import typer
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from gitops_audit.database.connection import AsyncSessionLocal
from gitops_audit.database.queries import get_deployment_by_id
from gitops_audit.database.models import Rollback

console = Console()


async def rollback_deployment_async(deployment_id: int, reason: str, yes: bool):
    """Async function to perform rollback to a specific deployment."""
    async with AsyncSessionLocal() as session:
        deployment = await get_deployment_by_id(session, deployment_id)

        if not deployment:
            console.print(f"[red]✗ Deployment #{deployment_id} not found[/red]")
            raise typer.Exit(1)

        if not deployment.commit_sha or deployment.commit_sha == "unknown":
            console.print(f"[red]✗ Deployment #{deployment_id} has no valid commit SHA[/red]")
            raise typer.Exit(1)

        console.print()
        info = Table.grid(padding=(0, 2))
        info.add_column(style="bold cyan", justify="right")
        info.add_column(style="white")

        info.add_row("App:", deployment.app_name)
        info.add_row("Namespace:", deployment.namespace)
        info.add_row("Target Commit:", deployment.commit_sha[:8])
        info.add_row("Deployed At:", deployment.deployed_at.strftime("%Y-%m-%d %H:%M:%S UTC"))
        if reason:
            info.add_row("Reason:", reason)

        panel = Panel(
            info,
            title=f"[bold yellow]⚠ Rolling back to Deployment #{deployment_id}[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        )
        console.print(panel)
        console.print()

        if not yes:
            confirmed = typer.confirm(
                f"Roll back {deployment.app_name} to commit {deployment.commit_sha[:8]}?"
            )
            if not confirmed:
                console.print("[dim]Rollback cancelled.[/dim]")
                raise typer.Exit(0)

        console.print(f"[cyan]→ Triggering rollback for {deployment.app_name}...[/cyan]")

        try:
            patch = f'{{"operation": {{"sync": {{"revision": "{deployment.commit_sha}"}}}}}}'
            result = subprocess.run(
                [
                    "kubectl",
                    "-n",
                    "argocd",
                    "patch",
                    "application",
                    deployment.app_name,
                    "--type",
                    "merge",
                    "-p",
                    patch,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                console.print(f"[red]✗ kubectl failed: {result.stderr.strip()}[/red]")
                await _record_rollback(
                    session, deployment_id, deployment.commit_sha, reason, success=False
                )
                raise typer.Exit(1)

        except subprocess.TimeoutExpired:
            console.print("[red]✗ kubectl timed out after 30 seconds[/red]")
            await _record_rollback(
                session, deployment_id, deployment.commit_sha, reason, success=False
            )
            raise typer.Exit(1)

        except FileNotFoundError:
            console.print("[red]✗ kubectl not found — is it installed and in PATH?[/red]")
            raise typer.Exit(1)

        await _record_rollback(session, deployment_id, deployment.commit_sha, reason, success=True)

        console.print(f"[green]✓ Rollback triggered successfully for {deployment.app_name}[/green]")
        console.print(f"[dim]ArgoCD is now syncing to commit {deployment.commit_sha[:8]}[/dim]")
        console.print()
        console.print(
            f"[dim]Run: gitops-audit show {deployment_id} for full deployment details[/dim]"
        )
        console.print()


async def _record_rollback(
    session,
    deployment_id: int,
    target_commit_sha: str,
    reason: str,
    success: bool,
):
    """Record rollback event in database."""
    rollback = Rollback(
        deployment_id=deployment_id,
        rolled_back_at=datetime.utcnow(),
        rolled_back_by="cli",
        reason=reason or "Manual rollback via CLI",
        target_commit_sha=target_commit_sha,
        success=success,
    )
    session.add(rollback)
    await session.commit()


def rollback_command(
    deployment_id: int = typer.Argument(
        ...,
        help="Deployment ID to roll back to",
    ),
    reason: str = typer.Option(
        "",
        "--reason",
        "-r",
        help="Reason for rollback (optional)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
):
    """
    Roll back to a previous deployment.

    Triggers an ArgoCD sync to the commit SHA of the specified deployment
    and records the rollback in the audit trail.

    Examples:
        gitops-audit rollback 5
        gitops-audit rollback 5 --reason "High error rate after deploy"
        gitops-audit rollback 5 --yes
    """
    asyncio.run(rollback_deployment_async(deployment_id, reason, yes))
