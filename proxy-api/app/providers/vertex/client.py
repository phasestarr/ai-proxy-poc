"""
Purpose:
- Build and validate Google Gen AI clients for Vertex AI.

Responsibilities:
- Validate the required Vertex runtime settings
- Lazily create Google Gen AI clients
- Keep SDK-specific configuration out of service modules

Notes:
- Import the provider SDK lazily so missing dependencies surface as controlled
  runtime errors instead of startup crashes.
"""

from __future__ import annotations

from app.config.ai import ai_settings
from app.providers.vertex.rag import VertexRagConfigurationError, ensure_vertex_rag_configuration_ready


class VertexProviderConfigurationError(RuntimeError):
    """Raised when Vertex provider settings or dependencies are missing."""


def ensure_vertex_provider_ready() -> None:
    if not ai_settings.vertex_ai_project:
        raise VertexProviderConfigurationError("vertex ai project is not configured")
    if not ai_settings.vertex_ai_location:
        raise VertexProviderConfigurationError("vertex ai location is not configured")
    if not ai_settings.vertex_ai_model:
        raise VertexProviderConfigurationError("vertex ai model is not configured")
    try:
        ensure_vertex_rag_configuration_ready()
    except VertexRagConfigurationError as exc:
        raise VertexProviderConfigurationError(str(exc)) from exc

    try:
        from google import genai  # noqa: F401
        from google.genai import types  # noqa: F401
    except ImportError as exc:
        raise VertexProviderConfigurationError("google-genai is not installed") from exc


def build_vertex_ai_client():
    ensure_vertex_provider_ready()

    from google import genai
    from google.genai import types

    return genai.Client(
        vertexai=True,
        project=ai_settings.vertex_ai_project,
        location=ai_settings.vertex_ai_location,
        http_options=types.HttpOptions(api_version=ai_settings.vertex_ai_api_version),
    )
