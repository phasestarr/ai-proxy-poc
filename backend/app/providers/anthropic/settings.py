"""
Purpose:
- Load and expose Anthropic provider settings from environment variables.

Responsibilities:
- Keep Anthropic-specific runtime configuration out of generic app settings
- Bind the Anthropic API credential
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AnthropicProviderSettings(BaseSettings):
    api_key: str = Field(validation_alias="ANTHROPIC_API_KEY")

    model_config = SettingsConfigDict(
        extra="ignore",
    )

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str) -> str:
        return value.strip()

anthropic_settings = AnthropicProviderSettings()
