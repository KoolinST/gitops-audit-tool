"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/gitops_audit"
    github_token: str = ""
    prometheus_url: str = "http://localhost:9090"
    argocd_url: str = "http://localhost:8080"
    log_level: str = "INFO"
    slack_webhook_url: str = ""


settings = Settings()
