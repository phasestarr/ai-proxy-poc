from __future__ import annotations

from app.providers.vertex.client import VertexProviderConfigurationError, build_vertex_client


class CompressionVertexConfigurationError(RuntimeError):
    """Raised when the internal Vertex compression client cannot be constructed."""


def build_compression_vertex_client(*, location: str):
    try:
        return build_vertex_client(location=location)
    except VertexProviderConfigurationError as exc:
        raise CompressionVertexConfigurationError(str(exc)) from exc
