"""
Purpose:
- Load and expose AI provider and model-related settings from environment variables.

Responsibilities:
- Keep vendor and model configuration separate from general application settings
- Provide provider-specific parsing helpers for optional RAG settings
"""

import json
import re

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AiSettings(BaseSettings):
    vertex_ai_project: str = Field(
        default="",
        validation_alias=AliasChoices("VERTEX_AI_PROJECT", "GOOGLE_CLOUD_PROJECT"),
    )
    vertex_ai_location: str = Field(
        default="global",
        validation_alias=AliasChoices("VERTEX_AI_LOCATION", "GOOGLE_CLOUD_LOCATION"),
    )
    vertex_ai_model: str = Field(default="gemini-2.5-flash", validation_alias="VERTEX_AI_MODEL")
    vertex_ai_api_version: str = Field(default="v1", validation_alias="VERTEX_AI_API_VERSION")
    vertex_ai_rag_corpora_value: str = Field(default="", validation_alias="VERTEX_AI_RAG_CORPORA", exclude=True)
    vertex_ai_rag_similarity_top_k: int = Field(default=5, validation_alias="VERTEX_AI_RAG_SIMILARITY_TOP_K")
    vertex_ai_rag_vector_distance_threshold: float | None = Field(
        default=None,
        validation_alias="VERTEX_AI_RAG_VECTOR_DISTANCE_THRESHOLD",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("vertex_ai_rag_corpora_value", mode="before")
    @classmethod
    def normalize_vertex_ai_rag_corpora_value(cls, value: object) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, (list, tuple, set)):
            return ",".join(str(item).strip() for item in value if str(item).strip())

        raise ValueError("VERTEX_AI_RAG_CORPORA must be a comma-separated string or list")

    @field_validator("vertex_ai_rag_vector_distance_threshold", mode="before")
    @classmethod
    def parse_vertex_ai_rag_vector_distance_threshold(cls, value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)

    @property
    def vertex_ai_rag_corpora(self) -> list[str]:
        trimmed = self.vertex_ai_rag_corpora_value.strip()
        if not trimmed:
            return []
        if trimmed.startswith("["):
            parsed = json.loads(trimmed)
            if not isinstance(parsed, list):
                raise ValueError("VERTEX_AI_RAG_CORPORA JSON value must be a list")
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in re.split(r"[\r\n,]+", trimmed) if item.strip()]


ai_settings = AiSettings()
