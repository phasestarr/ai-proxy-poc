"""
Purpose:
- Load and expose OpenAI provider settings from environment variables.

Responsibilities:
- Keep OpenAI-specific runtime configuration out of generic app settings
- Hold Responses API hosted tool configuration in the provider namespace
"""

from __future__ import annotations

import json
import re

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAIProviderSettings(BaseSettings):
    api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    vector_store_ids_value: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_VECTOR_STORE_IDS", "OPENAI_FILE_SEARCH_VECTOR_STORE_IDS"),
        exclude=True,
    )
    file_search_max_num_results: int = Field(default=5, validation_alias="OPENAI_FILE_SEARCH_MAX_NUM_RESULTS")
    file_search_score_threshold: float | None = Field(
        default=None,
        validation_alias="OPENAI_FILE_SEARCH_SCORE_THRESHOLD",
    )
    code_interpreter_memory_limit: str = Field(default="4g", validation_alias="OPENAI_CODE_INTERPRETER_MEMORY_LIMIT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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

    @field_validator("file_search_max_num_results")
    @classmethod
    def validate_file_search_max_num_results(cls, value: int) -> int:
        if value < 1 or value > 50:
            raise ValueError("OPENAI_FILE_SEARCH_MAX_NUM_RESULTS must be between 1 and 50")
        return value

    @field_validator("file_search_score_threshold", mode="before")
    @classmethod
    def parse_file_search_score_threshold(cls, value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        parsed = float(value)
        if parsed < 0 or parsed > 1:
            raise ValueError("OPENAI_FILE_SEARCH_SCORE_THRESHOLD must be between 0 and 1")
        return parsed

    @field_validator("code_interpreter_memory_limit")
    @classmethod
    def validate_code_interpreter_memory_limit(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed_values = {"1g", "4g", "16g", "64g"}
        if normalized not in allowed_values:
            raise ValueError("OPENAI_CODE_INTERPRETER_MEMORY_LIMIT must be one of 1g, 4g, 16g, or 64g")
        return normalized

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
