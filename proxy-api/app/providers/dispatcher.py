"""
Purpose:
- Dispatch chat traffic to the correct provider implementation.

Responsibilities:
- Hide provider-specific readiness checks behind a common entry point
- Route normalized provider requests to the matching provider adapter
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.providers.anthropic.provider import (
    ANTHROPIC_PROVIDER_ID,
    AnthropicProviderConfigurationError,
    AnthropicProviderError,
    ensure_anthropic_provider_ready,
    stream_anthropic_chat_completion,
)
from app.providers.anthropic.stream import prepare_anthropic_chat_completion_request
from app.providers.openai.provider import (
    OPENAI_PROVIDER_ID,
    OpenAIProviderConfigurationError,
    OpenAIProviderError,
    ensure_openai_provider_ready,
    stream_openai_chat_completion,
)
from app.providers.openai.stream import prepare_openai_chat_completion_request
from app.providers.types import ProviderRoute, ProviderStreamChunk
from app.providers.vertex.provider import (
    VERTEX_PROVIDER_ID,
    VertexProviderConfigurationError,
    VertexProviderError,
    ensure_vertex_provider_ready,
    stream_vertex_chat_completion,
)
from app.providers.vertex.stream import prepare_vertex_chat_completion_request
from app.schemas.chat import ChatMessage


class ProviderConfigurationError(RuntimeError):
    """Raised when the selected provider is not configured or unavailable."""


class ProviderExecutionError(RuntimeError):
    """Raised when a provider request fails during execution."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        error_code: str | None = None,
        result_code: str | None = None,
        result_message: str | None = None,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.error_code = error_code
        self.result_code = result_code
        self.result_message = result_message
        super().__init__(message)


def ensure_provider_ready(*, provider: str) -> None:
    try:
        if provider == VERTEX_PROVIDER_ID:
            ensure_vertex_provider_ready()
            return
        if provider == OPENAI_PROVIDER_ID:
            ensure_openai_provider_ready()
            return
        if provider == ANTHROPIC_PROVIDER_ID:
            ensure_anthropic_provider_ready()
            return
    except VertexProviderConfigurationError as exc:
        raise ProviderConfigurationError(str(exc)) from exc
    except OpenAIProviderConfigurationError as exc:
        raise ProviderConfigurationError(str(exc)) from exc
    except AnthropicProviderConfigurationError as exc:
        raise ProviderConfigurationError(str(exc)) from exc

    raise ProviderConfigurationError(f"provider is not configured: {provider}")


def validate_provider_request(
    *,
    route: ProviderRoute,
    messages: list[ChatMessage],
) -> None:
    if route.model.provider == VERTEX_PROVIDER_ID:
        prepare_vertex_chat_completion_request(
            public_model_id=route.model.public_id,
            messages=messages,
            selected_tool_ids=route.tool_ids,
            function_declarations=route.function_declarations,
        )
        return
    if route.model.provider == OPENAI_PROVIDER_ID:
        prepare_openai_chat_completion_request(
            public_model_id=route.model.public_id,
            messages=messages,
            selected_tool_ids=route.tool_ids,
            function_declarations=route.function_declarations,
        )
        return
    if route.model.provider == ANTHROPIC_PROVIDER_ID:
        prepare_anthropic_chat_completion_request(
            public_model_id=route.model.public_id,
            messages=messages,
            selected_tool_ids=route.tool_ids,
            function_declarations=route.function_declarations,
        )
        return

    raise ProviderConfigurationError(f"provider is not configured: {route.model.provider}")


async def stream_provider_chat_completion(
    *,
    route: ProviderRoute,
    messages: list[ChatMessage],
) -> AsyncIterator[ProviderStreamChunk]:
    try:
        if route.model.provider == VERTEX_PROVIDER_ID:
            async for chunk in stream_vertex_chat_completion(
                public_model_id=route.model.public_id,
                messages=messages,
                selected_tool_ids=route.tool_ids,
                function_declarations=route.function_declarations,
            ):
                yield chunk
            return
        if route.model.provider == OPENAI_PROVIDER_ID:
            async for chunk in stream_openai_chat_completion(
                public_model_id=route.model.public_id,
                messages=messages,
                selected_tool_ids=route.tool_ids,
                function_declarations=route.function_declarations,
            ):
                yield chunk
            return
        if route.model.provider == ANTHROPIC_PROVIDER_ID:
            async for chunk in stream_anthropic_chat_completion(
                public_model_id=route.model.public_id,
                messages=messages,
                selected_tool_ids=route.tool_ids,
                function_declarations=route.function_declarations,
            ):
                yield chunk
            return
    except VertexProviderError as exc:
        raise ProviderExecutionError(
            str(exc),
            provider=VERTEX_PROVIDER_ID,
            status_code=exc.status_code,
            error_code=exc.error_code,
            result_code=exc.result_code,
            result_message=exc.result_message,
        ) from exc
    except OpenAIProviderError as exc:
        raise ProviderExecutionError(
            str(exc),
            provider=OPENAI_PROVIDER_ID,
            status_code=exc.status_code,
            error_code=exc.error_code,
            result_code=exc.result_code,
            result_message=exc.result_message,
        ) from exc
    except AnthropicProviderError as exc:
        raise ProviderExecutionError(
            str(exc),
            provider=ANTHROPIC_PROVIDER_ID,
            status_code=exc.status_code,
            error_code=exc.error_code,
            result_code=exc.result_code,
            result_message=exc.result_message,
        ) from exc

    raise ProviderExecutionError(
        f"provider is not configured: {route.model.provider}",
        provider=route.model.provider,
    )
