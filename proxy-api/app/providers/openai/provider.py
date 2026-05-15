"""
OpenAI provider entry points exposed to the shared provider catalog and dispatcher.
"""

from __future__ import annotations

from app.providers.openai.client import OpenAIProviderConfigurationError, ensure_openai_provider_ready
from app.providers.openai.models import OPENAI_PROVIDER_ID, list_openai_models
from app.providers.openai.stream import OpenAIProviderError, stream_openai_chat_completion


__all__ = [
    "OPENAI_PROVIDER_ID",
    "OpenAIProviderConfigurationError",
    "OpenAIProviderError",
    "ensure_openai_provider_ready",
    "list_openai_models",
    "stream_openai_chat_completion",
]
