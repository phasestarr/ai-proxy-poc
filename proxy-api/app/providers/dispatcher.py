"""
Purpose:
- Dispatch chat traffic to the correct provider implementation.

Responsibilities:
- Hide provider-specific readiness checks behind a common entry point
- Route normalized provider requests to the matching provider adapter
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.providers.types import ProviderRoute, ProviderStreamChunk
from app.providers.vertex.provider import (
    VERTEX_PROVIDER_ID,
    VertexProviderConfigurationError,
    VertexProviderError,
    ensure_vertex_provider_ready,
    stream_vertex_chat_completion,
)
from app.schemas.chat import ChatMessage


class ProviderConfigurationError(RuntimeError):
    """Raised when the selected provider is not configured or unavailable."""


class ProviderExecutionError(RuntimeError):
    """Raised when a provider request fails during execution."""


def ensure_provider_ready(*, provider: str) -> None:
    try:
        if provider == VERTEX_PROVIDER_ID:
            ensure_vertex_provider_ready()
            return
    except VertexProviderConfigurationError as exc:
        raise ProviderConfigurationError(str(exc)) from exc

    raise ProviderConfigurationError(f"provider is not configured: {provider}")


async def stream_provider_chat_completion(
    *,
    route: ProviderRoute,
    messages: list[ChatMessage],
) -> AsyncIterator[ProviderStreamChunk]:
    try:
        if route.model.provider == VERTEX_PROVIDER_ID:
            async for chunk in stream_vertex_chat_completion(
                model_name=route.model.provider_model,
                messages=messages,
                selected_tool_ids=route.tool_ids,
            ):
                yield chunk
            return
    except VertexProviderError as exc:
        raise ProviderExecutionError(str(exc)) from exc

    raise ProviderExecutionError(f"provider is not configured: {route.model.provider}")
