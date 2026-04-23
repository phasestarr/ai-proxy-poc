"""
Purpose:
- Load and expose non-AI backend application settings from environment variables.

Responsibilities:
- Define runtime, database, auth, and infrastructure settings
- Keep environment loading centralized and predictable
- Leave provider and model-specific configuration to dedicated modules
"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_name: str = "AI Proxy API"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "postgresql+psycopg://postgres:post@localhost:5432/ai_proxy"
    redis_url: str = "redis://localhost:6379/0"

    auth_session_cookie_name: str = "session_id"
    auth_conflict_cookie_name: str = "session_conflict_id"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "strict"
    auth_cookie_path: str = "/"
    auth_cookie_domain: str | None = None
    auth_data_encryption_key: str = ""

    auth_guest_idle_minutes: int = 360
    auth_guest_absolute_hours: int = 24
    auth_guest_max_sessions: int = 2
    auth_microsoft_idle_minutes: int = 1440
    auth_microsoft_absolute_days: int = 1
    auth_microsoft_max_sessions: int = 4
    auth_session_limit_strategy: Literal["reject", "evict_oldest"] = "reject"
    auth_conflict_ticket_minutes: int = 5
    auth_cleanup_interval_minutes: int = 60
    microsoft_oauth_transaction_minutes: int = 10

    chat_inflight_lock_ttl_seconds: int = 180
    chat_rate_limit_per_minute: int = 10
    chat_rate_limit_per_hour: int = 30
    startup_dependency_max_attempts: int = 30
    startup_dependency_retry_seconds: float = 2.0

    microsoft_authority: str = "https://login.microsoftonline.com/common"
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_path: str = "/api/v1/auth/callback/microsoft"
    microsoft_scopes: list[str] = Field(
        default_factory=lambda: ["email"],
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = AppSettings()
