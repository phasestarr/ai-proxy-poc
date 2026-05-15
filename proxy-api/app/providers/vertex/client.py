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

from app.config.providers.vertex import vertex_settings


class VertexProviderConfigurationError(RuntimeError):
    """Raised when Vertex provider settings or dependencies are missing."""


def ensure_vertex_provider_ready() -> None:
    if not vertex_settings.project:
        raise VertexProviderConfigurationError("vertex ai project is not configured")

    try:
        from google import genai  # noqa: F401
        from google.genai import types  # noqa: F401
    except ImportError as exc:
        raise VertexProviderConfigurationError("google-genai is not installed") from exc


def build_vertex_client(*, location: str):
    ensure_vertex_provider_ready()

    from google import genai
    from google.genai import types

    return genai.Client(
        vertexai=True,
        project=vertex_settings.project,
        location=location,
        http_options=types.HttpOptions(api_version=vertex_settings.api_version),
    )


def build_vertex_ai_client(*, location: str):
    return build_vertex_client(location=location)
