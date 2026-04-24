"""
Purpose:
- Load and expose Anthropic provider settings from environment variables.

Responsibilities:
- Keep Anthropic-specific runtime configuration out of generic app settings
- Hold Messages API hosted tool configuration in the provider namespace
"""

from __future__ import annotations

import json
import re

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AnthropicProviderSettings(BaseSettings):
    api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    api_version: str = Field(default="2023-06-01", validation_alias="ANTHROPIC_VERSION")
    web_search_max_uses: int = Field(default=5, validation_alias="ANTHROPIC_WEB_SEARCH_MAX_USES")
    web_search_allowed_domains_value: str = Field(
        default="",
        validation_alias="ANTHROPIC_WEB_SEARCH_ALLOWED_DOMAINS",
        exclude=True,
    )
    web_search_blocked_domains_value: str = Field(
        default="",
        validation_alias="ANTHROPIC_WEB_SEARCH_BLOCKED_DOMAINS",
        exclude=True,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ANTHROPIC_VERSION must not be blank")
        return normalized

    @field_validator("web_search_max_uses")
    @classmethod
    def validate_web_search_max_uses(cls, value: int) -> int:
        if value < 1:
            raise ValueError("ANTHROPIC_WEB_SEARCH_MAX_USES must be at least 1")
        return value

    @field_validator("web_search_allowed_domains_value", "web_search_blocked_domains_value", mode="before")
    @classmethod
    def normalize_domain_list_value(cls, value: object) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, (list, tuple, set)):
            return ",".join(str(item).strip() for item in value if str(item).strip())

        raise ValueError("Anthropic web search domain lists must be comma-separated strings or lists")

    @property
    def web_search_allowed_domains(self) -> list[str]:
        return _parse_list_value(self.web_search_allowed_domains_value)

    @property
    def web_search_blocked_domains(self) -> list[str]:
        return _parse_list_value(self.web_search_blocked_domains_value)


def _parse_list_value(value: str) -> list[str]:
    trimmed = value.strip()
    if not trimmed:
        return []
    if trimmed.startswith("["):
        parsed = json.loads(trimmed)
        if not isinstance(parsed, list):
            raise ValueError("Anthropic domain list JSON value must be a list")
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in re.split(r"[\r\n,]+", trimmed) if item.strip()]


anthropic_settings = AnthropicProviderSettings()
