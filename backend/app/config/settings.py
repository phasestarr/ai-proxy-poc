"""
Purpose:
- Load and expose non-AI backend application settings from environment variables.

Responsibilities:
- Define runtime, database, auth, and infrastructure settings
- Keep environment loading centralized and predictable
- Leave provider and model-specific configuration to dedicated modules
"""

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_name: str
    app_env: str

    database_url: str
    redis_url: str

    auth_session_cookie_name: str
    auth_conflict_cookie_name: str
    auth_cookie_secure: bool
    auth_cookie_path: str
    auth_cookie_domain: str | None
    auth_data_encryption_key: str

    auth_session_ttl_minutes: int = Field(gt=0)
    auth_guest_max_sessions: int = Field(gt=0)
    auth_microsoft_max_sessions: int = Field(gt=0)
    auth_session_limit_strategy: Literal["reject", "evict_oldest"]
    auth_conflict_ticket_minutes: int = Field(gt=0)
    housekeeping_interval_minutes: int = Field(gt=0)
    microsoft_oauth_transaction_minutes: int = Field(gt=0)

    chat_draft_ttl_seconds: int = Field(gt=0)
    chat_validating_operation_timeout_seconds: int = Field(gt=0)
    chat_provider_event_idle_timeout_seconds: int = Field(gt=0)
    chat_provider_max_runtime_seconds: int = Field(gt=0)
    chat_rate_limit_per_minute: int = Field(gt=0)
    chat_rate_limit_per_hour: int = Field(gt=0)
    chat_attachment_max_files_per_history: int = Field(gt=0)
    chat_attachment_max_files_per_user: int = Field(gt=0)
    chat_attachment_max_file_bytes: int = Field(gt=0)
    chat_attachment_max_total_bytes_per_history: int = Field(gt=0)
    chat_attachment_max_total_tokens_per_provider: int = Field(gt=0)
    chat_attachment_remote_ttl_hours: int = Field(gt=0)
    usage_default_cap_usd: float = Field(ge=0)
    startup_dependency_max_attempts: int = Field(gt=0)
    startup_dependency_retry_seconds: float = Field(gt=0)
    deployment_smoke_required: bool

    microsoft_authority: str
    microsoft_client_id: str
    microsoft_client_secret: str
    microsoft_redirect_path: str
    microsoft_scopes: list[str]

    model_config = SettingsConfigDict(
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_related_limits(self) -> "AppSettings":
        if self.chat_attachment_max_files_per_history > self.chat_attachment_max_files_per_user:
            raise ValueError(
                "CHAT_ATTACHMENT_MAX_FILES_PER_HISTORY must not exceed "
                "CHAT_ATTACHMENT_MAX_FILES_PER_USER"
            )
        if self.chat_attachment_max_file_bytes > self.chat_attachment_max_total_bytes_per_history:
            raise ValueError(
                "CHAT_ATTACHMENT_MAX_FILE_BYTES must not exceed "
                "CHAT_ATTACHMENT_MAX_TOTAL_BYTES_PER_HISTORY"
            )
        return self


settings = AppSettings()
