"""Configuration loading and validation using Pydantic."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- GitLab Source ---
    gitlab_url: str = Field(..., description="Base URL of the GitLab instance")
    gitlab_token: str = Field(..., description="GitLab Personal Access Token")
    gitlab_target_group: str = Field(
        ...,
        description="Group ID or URL-encoded full path (e.g. 'mon-equipe/projets')",
    )

    # --- Gitea Target ---
    gitea_url: str = Field(..., description="Base URL of the Gitea instance")
    gitea_token: str = Field(..., description="Gitea Personal Access Token")
    gitea_target_org: str = Field(
        "gitlab-backup",
        description="Root Gitea organisation where mirrors will be created",
    )

    # --- TLS / SSL ---
    ssl_verify: bool = Field(
        True,
        description="Verify TLS certificates. Set to false to allow self-signed certificates.",
    )

    # --- Service ---
    poll_interval_seconds: int = Field(
        600, ge=30, description="How often to scan GitLab (seconds)"
    )
    web_port: int = Field(8000, description="Port for the web dashboard")
    log_level: str = Field("INFO", description="Logging level")
    request_timeout: int = Field(30, ge=5, description="HTTP request timeout (seconds)")

    @field_validator("gitlab_url", "gitea_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()