from __future__ import annotations

from app.config.providers.vertex import vertex_settings


class CompressionVertexConfigurationError(RuntimeError):
    """Raised when the internal Vertex compression client cannot be constructed."""


def build_compression_vertex_client(*, location: str):
    if not vertex_settings.project:
        raise CompressionVertexConfigurationError("vertex ai project is not configured")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise CompressionVertexConfigurationError("google-genai is not installed") from exc

    return genai.Client(
        vertexai=True,
        project=vertex_settings.project,
        location=location,
        http_options=types.HttpOptions(api_version=vertex_settings.api_version),
    )
