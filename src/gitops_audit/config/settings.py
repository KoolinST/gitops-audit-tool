"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/gitops_audit"
    
    # GitHub
    github_token: str = ""
    
    # Prometheus
    prometheus_url: str = "http://localhost:9090"
    
    # ArgoCD
    argocd_url: str = "http://localhost:8080"
    
    # Logging
    log_level: str = "INFO"

    # Slack
    slack_webhook_url: str = ""

settings = Settings()
