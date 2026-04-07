"""
Vertex provider entry points exposed to the shared provider catalog and dispatcher.
"""

from __future__ import annotations

from app.config.providers.vertex import vertex_settings
from app.providers.types import ProviderModelDefinition, ProviderToolDefinition
from app.providers.vertex.client import VertexProviderConfigurationError, ensure_vertex_provider_ready
from app.providers.vertex.stream import VertexProviderError, stream_vertex_chat_completion

VERTEX_PROVIDER_ID = "vertex_ai"


def list_vertex_models() -> list[ProviderModelDefinition]:
    return [
        ProviderModelDefinition(
            public_id="gemini",
            provider=VERTEX_PROVIDER_ID,
            provider_model=vertex_settings.model,
            display_name="Gemini",
            available=True,
            default=True,
            supported_tools=(
                ProviderToolDefinition(
                    public_id="rag",
                    display_name="RAG",
                    available=True,
                ),
            ),
        )
    ]


__all__ = [
    "VERTEX_PROVIDER_ID",
    "VertexProviderConfigurationError",
    "VertexProviderError",
    "ensure_vertex_provider_ready",
    "list_vertex_models",
    "stream_vertex_chat_completion",
]
