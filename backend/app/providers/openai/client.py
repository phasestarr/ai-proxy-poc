"""
Purpose:
- Build and validate OpenAI clients.

Responsibilities:
- Validate required OpenAI runtime settings
- Lazily create SDK clients
- Keep SDK-specific configuration out of service modules
"""

from __future__ import annotations

from app.config.providers.openai import openai_settings


class OpenAIProviderConfigurationError(RuntimeError):
    """Raised when OpenAI provider settings or dependencies are missing."""


def ensure_openai_provider_ready() -> None:
    if not openai_settings.api_key:
        raise OpenAIProviderConfigurationError("openai api key is not configured")

    try:
        from openai import AsyncOpenAI  # noqa: F401
    except ImportError as exc:
        raise OpenAIProviderConfigurationError("openai is not installed") from exc


def build_openai_client():
    ensure_openai_provider_ready()

    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=openai_settings.api_key)

