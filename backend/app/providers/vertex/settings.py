"""
Purpose:
- Load and expose Vertex provider settings from environment variables.

Responsibilities:
- Keep Vertex-specific runtime configuration out of generic app settings
- Bind credentials and external Vertex resource identifiers
"""

from __future__ import annotations

import json
import re

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class VertexProviderSettings(BaseSettings):
    project: str = Field(validation_alias="GOOGLE_CLOUD_PROJECT")
    attachment_gcs_bucket: str = Field(validation_alias="VERTEX_AI_ATTACHMENT_GCS_BUCKET")
    attachment_gcs_prefix: str = Field(validation_alias="VERTEX_AI_ATTACHMENT_GCS_PREFIX")
    rag_corpora_value: str = Field(validation_alias="VERTEX_AI_RAG_CORPORA", exclude=True)

    model_config = SettingsConfigDict(
        extra="ignore",
    )

    @field_validator("project", "attachment_gcs_bucket", "attachment_gcs_prefix")
    @classmethod
    def normalize_optional_strings(cls, value: str) -> str:
        return value.strip()

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
