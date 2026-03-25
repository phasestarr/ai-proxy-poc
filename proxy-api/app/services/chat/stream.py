"""
Purpose:
- Implement chat streaming orchestration for the backend service layer.

Responsibilities:
- Apply coordination and rate limit guardrails before streaming starts
- Convert provider output into SSE events for the HTTP layer
- Release coordination state on completion, failure, or disconnect
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.db.redis.chat_coordination import (
    ChatCoordinationUnavailableError,
    ChatRateLimitExceededError,
    ChatRequestInProgressError,
    acquire_chat_execution_lease,
    enforce_chat_rate_limits,
    release_chat_execution_lease,
)
from app.providers.vertex.client import VertexProviderConfigurationError, ensure_vertex_provider_ready
from app.providers.vertex.stream import VertexProviderError, stream_vertex_chat_completion
from app.providers.vertex.types import VertexStreamChunk
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatStreamDeltaEvent,
    ChatStreamDoneEvent,
    ChatStreamErrorEvent,
    ChatStreamStartEvent,
    ChatUsageSummary,
)
from app.services.auth import SessionContext
from app.services.chat.preparation import prepare_chat_completion_request


class ChatProviderUnavailableError(RuntimeError):
    """Raised when a provider is not configured for streaming."""


def create_chat_completion_stream(
    payload: ChatCompletionRequest,
    *,
    session: SessionContext,
) -> AsyncIterator[bytes]:
    prepared = prepare_chat_completion_request(payload, session=session)

    try:
        _ensure_provider_ready(provider=prepared.model.provider)
    except VertexProviderConfigurationError as exc:
        raise ChatProviderUnavailableError(str(exc)) from exc

    lease = acquire_chat_execution_lease(session_id=session.session_id)
    try:
        enforce_chat_rate_limits(user_id=session.user_id)
    except Exception:
        release_chat_execution_lease(lease)
        raise

    return _stream_chat_completion(
        prepared.model.public_id,
        prepared.model.provider,
        prepared.model.provider_model,
        prepared.messages,
        lease,
    )


async def _stream_chat_completion(
    public_model_id: str,
    provider: str,
    provider_model: str,
    messages,
    lease,
) -> AsyncIterator[bytes]:
    last_chunk: VertexStreamChunk | None = None
    yield _encode_sse_event(
        "start",
        ChatStreamStartEvent(model=public_model_id, provider=provider),
    )

    try:
        async for chunk in stream_vertex_chat_completion(
            model_name=provider_model,
            messages=messages,
        ):
            last_chunk = chunk
            if chunk.text:
                yield _encode_sse_event(
                    "delta",
                    ChatStreamDeltaEvent(delta_text=chunk.text),
                )
    except asyncio.CancelledError:
        raise
    except VertexProviderError as exc:
        yield _encode_sse_event(
            "error",
            ChatStreamErrorEvent(detail=str(exc)),
        )
        return
    except Exception:
        yield _encode_sse_event(
            "error",
            ChatStreamErrorEvent(detail="chat streaming failed"),
        )
        return
    finally:
        release_chat_execution_lease(lease)

    yield _encode_sse_event(
        "done",
        ChatStreamDoneEvent(
            model=public_model_id,
            provider=provider,
            finish_reason=last_chunk.finish_reason if last_chunk else None,
            usage=_map_usage_summary(last_chunk),
        ),
    )


def _ensure_provider_ready(*, provider: str) -> None:
    if provider == "vertex_ai":
        ensure_vertex_provider_ready()
        return
    raise ChatProviderUnavailableError(f"provider is not configured: {provider}")


def _map_usage_summary(chunk: VertexStreamChunk | None) -> ChatUsageSummary | None:
    if chunk is None or chunk.usage is None:
        return None
    return ChatUsageSummary(
        input_tokens=chunk.usage.prompt_token_count,
        output_tokens=chunk.usage.candidates_token_count,
        total_tokens=chunk.usage.total_token_count,
    )


def _encode_sse_event(event_name: str, payload: BaseModel) -> bytes:
    return f"event: {event_name}\ndata: {payload.model_dump_json()}\n\n".encode("utf-8")


__all__ = [
    "ChatCoordinationUnavailableError",
    "ChatProviderUnavailableError",
    "ChatRateLimitExceededError",
    "ChatRequestInProgressError",
    "create_chat_completion_stream",
]
