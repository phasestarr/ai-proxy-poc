"""
Vertex provider entry points exposed to the shared provider catalog and dispatcher.
"""

from __future__ import annotations

from app.providers.vertex.client import VertexProviderConfigurationError, ensure_vertex_provider_ready
from app.providers.vertex.models import VERTEX_PROVIDER_ID, list_vertex_models
from app.providers.vertex.stream import VertexProviderError, stream_vertex_chat_completion


__all__ = [
    "VERTEX_PROVIDER_ID",
    "VertexProviderConfigurationError",
    "VertexProviderError",
    "ensure_vertex_provider_ready",
    "list_vertex_models",
    "stream_vertex_chat_completion",
]
