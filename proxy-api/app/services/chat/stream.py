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
from app.providers.dispatcher import (
    ProviderConfigurationError,
    ProviderExecutionError,
    ensure_provider_ready,
    stream_provider_chat_completion,
)
from app.providers.types import ProviderRoute, ProviderStreamChunk
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
        ensure_provider_ready(provider=prepared.route.model.provider)
    except ProviderConfigurationError as exc:
        raise ChatProviderUnavailableError(str(exc)) from exc

    lease = acquire_chat_execution_lease(session_id=session.session_id)
    try:
        enforce_chat_rate_limits(user_id=session.user_id)
    except Exception:
        release_chat_execution_lease(lease)
        raise

    return _stream_chat_completion(
        prepared.route,
        prepared.messages,
        lease,
    )


async def _stream_chat_completion(
    route: ProviderRoute,
    messages,
    lease,
) -> AsyncIterator[bytes]:
    last_chunk: ProviderStreamChunk | None = None
    yield _encode_sse_event(
        "start",
        ChatStreamStartEvent(model=route.model.public_id, provider=route.model.provider),
    )

    try:
        async for chunk in stream_provider_chat_completion(
            route=route,
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
    except ProviderExecutionError as exc:
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
            model=route.model.public_id,
            provider=route.model.provider,
            finish_reason=last_chunk.finish_reason if last_chunk else None,
            usage=_map_usage_summary(last_chunk),
        ),
    )


def _map_usage_summary(chunk: ProviderStreamChunk | None) -> ChatUsageSummary | None:
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
