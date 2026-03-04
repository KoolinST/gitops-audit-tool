"""CLI entry point for gitops-audit."""

import uvicorn
import typer
import structlog
from urllib.parse import urlparse
from gitops_audit.config.logging import configure_logging
from gitops_audit.config.settings import settings

# Import command functions
from gitops_audit.cli.commands.history import history_command
from gitops_audit.cli.commands.show import show_command
from gitops_audit.cli.commands.apps import apps_command
from gitops_audit.cli.commands.correlate import correlate_command
from gitops_audit.cli.commands.rollback import rollback_command

app = typer.Typer(
    name="gitops-audit",
    help="GitOps deployment tracking and rollback system",
    add_completion=False,
)

log = structlog.get_logger()


def sanitize_database_url(url: str) -> str:
    """
    Remove credentials from database URL for safe display.

    Args:
        url: Full database URL with possible credentials

    Returns:
        Sanitized URL without username/password

    Example:
        postgresql+asyncpg://user:pass@localhost:5433/mydb
        → localhost:5433/mydb
    """
    try:
        parsed = urlparse(url)
        port = f":{parsed.port}" if parsed.port else ""
        path = parsed.path.lstrip('/') if parsed.path else ""
        return f"{parsed.hostname}{port}/{path}" if path else f"{parsed.hostname}{port}"
    except Exception:
        return "configured"


@app.command()
def watcher():
    """Start the ArgoCD deployment watcher."""
    configure_logging(settings.log_level)

    typer.echo("Starting GitOps Audit watcher...")
    typer.echo(f"Monitoring ArgoCD applications in namespace: argocd")
    typer.echo(f"Database: {sanitize_database_url(settings.database_url)}")
    typer.echo("Press Ctrl+C to stop...")

    log.info(
        "watcher_starting",
        namespace="argocd",
        database_host=urlparse(settings.database_url).hostname,
        log_level=settings.log_level,
    )

    import asyncio
    from gitops_audit.watcher.argocd_watcher import main as watcher_main

    try:
        asyncio.run(watcher_main())
    except KeyboardInterrupt:
        typer.echo("\n\nWatcher stopped gracefully")
        log.info("watcher_stopped", reason="user_interrupt")
        raise typer.Exit(0)
    except Exception as e:
        typer.echo(f"\n\nError: {e}", err=True)
        log.error("watcher_failed", error=str(e), error_type=type(e).__name__)
        raise typer.Exit(1)


app.command(name="history")(history_command)
app.command(name="show")(show_command)
app.command(name="apps")(apps_command)
app.command(name="correlate")(correlate_command)
app.command(name="rollback")(rollback_command)


@app.command()
def api(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload for development"),
):
    """Start the REST API server."""
    configure_logging(settings.log_level)
    typer.echo(f"Starting GitOps Audit API on http://{host}:{port}")
    typer.echo(f"API docs available at http://{host}:{port}/docs")
    uvicorn.run(
        "gitops_audit.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def version():
    """Show version information."""
    typer.echo("gitops-audit v0.1.0")


if __name__ == "__main__":
    app()