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
    app_name: str
    app_env: str
    app_host: str
    app_port: int

    database_url: str
    redis_url: str

    auth_session_cookie_name: str
    auth_conflict_cookie_name: str
    auth_cookie_secure: bool
    auth_cookie_samesite: Literal["lax", "strict", "none"]
    auth_cookie_path: str
    auth_cookie_domain: str | None
    auth_data_encryption_key: str

    auth_session_ttl_minutes: int
    auth_guest_max_sessions: int
    auth_microsoft_max_sessions: int
    auth_session_limit_strategy: Literal["reject", "evict_oldest"]
    auth_conflict_ticket_minutes: int
    housekeeping_interval_minutes: int
    microsoft_oauth_transaction_minutes: int

    chat_draft_ttl_seconds: int
    chat_attachment_operation_timeout_seconds: int
    chat_provider_first_response_timeout_seconds: int
    chat_provider_stream_timeout_seconds: int
    chat_rate_limit_per_minute: int
    chat_rate_limit_per_hour: int
    chat_attachment_max_files_per_history: int
    chat_attachment_max_files_per_user: int
    chat_attachment_max_file_bytes: int
    chat_attachment_max_total_bytes_per_history: int
    chat_attachment_max_total_tokens_per_provider: int
    chat_attachment_remote_ttl_hours: int
    usage_default_cap_usd: float = 100.0
    startup_dependency_max_attempts: int
    startup_dependency_retry_seconds: float
    deployment_smoke_required: bool = False

    microsoft_authority: str
    microsoft_client_id: str
    microsoft_client_secret: str
    microsoft_redirect_path: str
    microsoft_scopes: list[str]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = AppSettings()
