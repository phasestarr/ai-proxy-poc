"""
Purpose:
- Load and expose Vertex provider settings from environment variables.

Responsibilities:
- Keep Vertex-specific runtime configuration out of generic app settings
- Hold future Vertex tool configuration in the same provider namespace
"""

from __future__ import annotations

import json
import re

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class VertexProviderSettings(BaseSettings):
    project: str = Field(
        default="",
        validation_alias=AliasChoices("VERTEX_AI_PROJECT", "GOOGLE_CLOUD_PROJECT"),
    )
    location: str = Field(
        default="global",
        validation_alias=AliasChoices("VERTEX_AI_LOCATION", "GOOGLE_CLOUD_LOCATION"),
    )
    model: str = Field(default="gemini-2.5-flash", validation_alias="VERTEX_AI_MODEL")
    api_version: str = Field(default="v1", validation_alias="VERTEX_AI_API_VERSION")
    rag_corpora_value: str = Field(default="", validation_alias="VERTEX_AI_RAG_CORPORA", exclude=True)
    rag_similarity_top_k: int = Field(default=5, validation_alias="VERTEX_AI_RAG_SIMILARITY_TOP_K")
    rag_vector_distance_threshold: float | None = Field(
        default=None,
        validation_alias="VERTEX_AI_RAG_VECTOR_DISTANCE_THRESHOLD",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("rag_corpora_value", mode="before")
    @classmethod
    def normalize_rag_corpora_value(cls, value: object) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, (list, tuple, set)):
            return ",".join(str(item).strip() for item in value if str(item).strip())

        raise ValueError("VERTEX_AI_RAG_CORPORA must be a comma-separated string or list")

    @field_validator("rag_vector_distance_threshold", mode="before")
    @classmethod
    def parse_rag_vector_distance_threshold(cls, value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)

    @property
    def rag_corpora(self) -> list[str]:
        trimmed = self.rag_corpora_value.strip()
        if not trimmed:
            return []
        if trimmed.startswith("["):
            parsed = json.loads(trimmed)
            if not isinstance(parsed, list):
                raise ValueError("VERTEX_AI_RAG_CORPORA JSON value must be a list")
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in re.split(r"[\r\n,]+", trimmed) if item.strip()]


vertex_settings = VertexProviderSettings()
