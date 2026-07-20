"""
Purpose:
- Load and expose OpenAI provider settings from environment variables.

Responsibilities:
- Keep OpenAI-specific runtime configuration out of generic app settings
- Bind credentials and external OpenAI resource identifiers
"""

from __future__ import annotations

import json
import re

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAIProviderSettings(BaseSettings):
    api_key: str = Field(validation_alias="OPENAI_API_KEY")
    vector_store_ids_value: str = Field(
        validation_alias="OPENAI_VECTOR_STORE_IDS",
        exclude=True,
    )
    model_config = SettingsConfigDict(
        extra="ignore",
    )

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("vector_store_ids_value", mode="before")
    @classmethod
    def normalize_vector_store_ids_value(cls, value: object) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, (list, tuple, set)):
            return ",".join(str(item).strip() for item in value if str(item).strip())

        raise ValueError("OPENAI_VECTOR_STORE_IDS must be a comma-separated string or list")

    @property
    def vector_store_ids(self) -> list[str]:
        trimmed = self.vector_store_ids_value.strip()
        if not trimmed:
            return []
        if trimmed.startswith("["):
            parsed = json.loads(trimmed)
            if not isinstance(parsed, list):
                raise ValueError("OPENAI_VECTOR_STORE_IDS JSON value must be a list")
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in re.split(r"[\r\n,]+", trimmed) if item.strip()]


openai_settings = OpenAIProviderSettings()
