"""
Purpose:
- Build and validate Anthropic clients.

Responsibilities:
- Validate required Anthropic runtime settings
- Lazily create SDK clients
- Keep SDK-specific configuration out of service modules
"""

from __future__ import annotations

from app.config.providers.anthropic import anthropic_settings


class AnthropicProviderConfigurationError(RuntimeError):
    """Raised when Anthropic provider settings or dependencies are missing."""


def ensure_anthropic_provider_ready() -> None:
    if not anthropic_settings.api_key:
        raise AnthropicProviderConfigurationError("anthropic api key is not configured")

    try:
        from anthropic import AsyncAnthropic  # noqa: F401
    except ImportError as exc:
        raise AnthropicProviderConfigurationError("anthropic is not installed") from exc


def build_anthropic_client():
    ensure_anthropic_provider_ready()

    from anthropic import AsyncAnthropic

    return AsyncAnthropic(
        api_key=anthropic_settings.api_key,
        default_headers={
            "anthropic-version": anthropic_settings.api_version,
        },
    )

