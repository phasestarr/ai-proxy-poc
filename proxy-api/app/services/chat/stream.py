"""
Purpose:
- Implement chat streaming orchestration for the backend service layer.

Responsibilities:
- Persist a backend-owned chat turn at send time
- Run provider execution independently from the browser SSE connection
- Convert live provider output into SSE events when the client is still connected
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import logging

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.chat_outcomes import SUCCESS_RESULT_CODE, get_error_message, pick_success_message
from app.db.postgres.session import SessionLocal
from app.db.redis.chat_coordination import (
    ChatCoordinationUnavailableError,
    ChatRateLimitExceededError,
    ChatRequestInProgressError,
    acquire_chat_execution_lease,
    enforce_chat_rate_limits,
    release_chat_execution_lease,
)
from app.providers.anthropic.outcomes import ANTHROPIC_SUCCESS_RESULT_CODE, pick_anthropic_success_message
from app.providers.openai.outcomes import OPENAI_SUCCESS_RESULT_CODE, pick_openai_success_message
from app.providers.vertex.outcomes import VERTEX_SUCCESS_RESULT_CODE, pick_vertex_success_message
from app.providers.dispatcher import (
    ProviderConfigurationError,
    ProviderExecutionError,
    ensure_provider_ready,
    stream_provider_chat_completion,
    validate_provider_request,
)
from app.providers.types import ProviderRoute, ProviderStreamChunk
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatStreamDeltaEvent,
    ChatStreamDoneEvent,
    ChatStreamErrorEvent,
    ChatStreamStartEvent,
    ChatStreamStatusEvent,
    ChatUsageSummary,
)
from app.auth.types import SessionContext
from app.services.chat.errors import ChatHistoryNotFoundError, ChatProxyError, build_preparation_error
from app.services.chat.turns import (
    PersistedChatTurn,
    persist_chat_turn_failure,
    persist_chat_turn_start,
    persist_chat_turn_success,
)
from app.services.chat.history_queries import load_user_history
from app.services.chat.preparation import prepare_chat_completion_request

logger = logging.getLogger("uvicorn.error")


class ChatHistoryUnavailableError(RuntimeError):
    """Raised when a requested chat history cannot be used."""


@dataclass(slots=True, frozen=True)
class _LiveStreamEvent:
    event_name: str
    payload: BaseModel


class _LiveChatStreamSink:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[_LiveStreamEvent] = asyncio.Queue()
        self._active = True

    def emit(self, event_name: str, payload: BaseModel) -> None:
        if self._active:
            self._queue.put_nowait(_LiveStreamEvent(event_name=event_name, payload=payload))

    async def get(self) -> _LiveStreamEvent:
        return await self._queue.get()

    def close(self) -> None:
        self._active = False


def create_chat_completion_stream(
    payload: ChatCompletionRequest,
    *,
    session: SessionContext,
    db: Session,
) -> AsyncIterator[bytes]:
    lease = None
    try:
        lease = acquire_chat_execution_lease(session_id=session.session_id)
    except ChatRequestInProgressError as exc:
        raise ChatProxyError(
            code="request_in_progress",
            origin="proxy",
            detail=_build_safe_error_detail("request_in_progress"),
            http_status=409,
            retry_after_seconds=exc.retry_after_seconds,
        ) from exc
    except ChatCoordinationUnavailableError as exc:
        raise ChatProxyError(
            code="coordination_unavailable",
            origin="proxy",
            detail=_build_safe_error_detail("coordination_unavailable"),
            http_status=503,
        ) from exc

    try:
        route = _run_chat_preflight(
            payload=payload,
            session=session,
            db=db,
        )
        turn = persist_chat_turn_start(
            db,
            payload=payload,
            session=session,
            route=route,
        )
    except ChatHistoryNotFoundError as exc:
        release_chat_execution_lease(lease)
        raise ChatHistoryUnavailableError(str(exc)) from exc
    except ChatProxyError:
        release_chat_execution_lease(lease)
        raise
    except Exception:
        release_chat_execution_lease(lease)
        raise

    sink = _LiveChatStreamSink()
    asyncio.create_task(
        _run_chat_completion_turn(
            turn=turn,
            route=route,
            lease=lease,
            sink=sink,
        )
    )
    return _stream_live_chat_completion(turn, sink)


async def _stream_live_chat_completion(
    turn: PersistedChatTurn,
    sink: _LiveChatStreamSink,
) -> AsyncIterator[bytes]:
    yield _encode_sse_event(
        "start",
        _build_start_event(turn),
    )

    try:
        while True:
            event = await sink.get()
            yield _encode_sse_event(event.event_name, event.payload)
            if event.event_name in {"done", "error"}:
                return
    finally:
        sink.close()


async def _run_chat_completion_turn(
    *,
    turn: PersistedChatTurn,
    route: ProviderRoute,
    lease,
    sink: _LiveChatStreamSink,
) -> None:
    last_chunk: ProviderStreamChunk | None = None
    accumulated_text = ""
    last_status_code: str | None = None

    try:
        async for chunk in stream_provider_chat_completion(
            route=route,
            messages=turn.provider_messages,
        ):
            last_chunk = chunk
            if chunk.status_code and chunk.status_message and chunk.status_code != last_status_code:
                last_status_code = chunk.status_code
                sink.emit(
                    "status",
                    ChatStreamStatusEvent(
                        provider=route.model.provider,
                        status_code=chunk.status_code,
                        status_message=chunk.status_message,
                    ),
                )
            if chunk.text:
                accumulated_text = f"{accumulated_text}{chunk.text}"
                sink.emit(
                    "delta",
                    ChatStreamDeltaEvent(delta_text=chunk.text),
                )
    except ProviderExecutionError as exc:
        error = _map_provider_execution_error(exc)
        _persist_turn_failure(turn, accumulated_text, error)
        sink.emit("error", _build_error_event(error))
        return
    except ChatProxyError as exc:
        _persist_turn_failure(turn, accumulated_text, exc)
        sink.emit("error", _build_error_event(exc))
        return
    except Exception as exc:
        logger.exception("Chat background execution failed.")
        error = ChatProxyError(
            code="chat_failed",
            origin="proxy",
            detail=_build_safe_error_detail("chat_failed"),
            http_status=500,
        )
        _persist_turn_failure(turn, accumulated_text, error)
        sink.emit("error", _build_error_event(error))
        return
    finally:
        release_chat_execution_lease(lease)

    result_code, result_message = _build_success_outcome(
        route=route,
        finish_reason=last_chunk.finish_reason if last_chunk else None,
    )
    with SessionLocal() as stream_db:
        persist_chat_turn_success(
            stream_db,
            history_id=turn.history_id,
            assistant_message_id=turn.assistant_message_id,
            content=accumulated_text,
            finish_reason=last_chunk.finish_reason if last_chunk else None,
            usage=last_chunk.usage if last_chunk else None,
            result_code=result_code,
            result_message=result_message,
        )
    sink.emit(
        "done",
        ChatStreamDoneEvent(
            model=route.model.public_id,
            provider=route.model.provider,
            result_code=result_code,
            result_message=result_message,
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


def _persist_turn_failure(
    turn: PersistedChatTurn,
    content: str,
    error: ChatProxyError,
) -> None:
    with SessionLocal() as stream_db:
        persist_chat_turn_failure(
            stream_db,
            history_id=turn.history_id,
            user_message_id=turn.user_message_id,
            assistant_message_id=turn.assistant_message_id,
            content=content,
            result_code=error.code,
            result_message=error.result_message,
            detail=error.detail,
        )


def _build_start_event(turn: PersistedChatTurn) -> ChatStreamStartEvent:
    return ChatStreamStartEvent(
        model=turn.model_id,
        provider=turn.provider,
        chat_history_id=turn.history_id,
        user_message_id=turn.user_message_id,
        assistant_message_id=turn.assistant_message_id,
    )


def _build_error_event(error: ChatProxyError) -> ChatStreamErrorEvent:
    return ChatStreamErrorEvent(
        result_code=error.code,
        result_message=error.result_message,
        retry_after_seconds=error.retry_after_seconds,
        detail=error.detail,
    )


def _map_rate_limit_error(exc: ChatRateLimitExceededError) -> ChatProxyError:
    return ChatProxyError(
        code="rate_limit_hour" if exc.window == "hour" else "rate_limit_minute",
        origin="proxy",
        detail=_build_safe_error_detail("rate_limit_hour" if exc.window == "hour" else "rate_limit_minute"),
        http_status=429,
        retry_after_seconds=exc.retry_after_seconds,
    )


def _map_provider_execution_error(exc: ProviderExecutionError) -> ChatProxyError:
    if exc.result_code and exc.result_message:
        return ChatProxyError(
            code=exc.result_code,
            origin="provider",
            detail=str(exc),
            http_status=exc.status_code,
            provider=exc.provider,
            provider_error_code=exc.error_code,
            result_message_override=exc.result_message,
        )

    raw_detail = str(exc)
    status_code = exc.status_code

    if _looks_like_proxy_provider_config_error(raw_detail):
        return ChatProxyError(
            code="provider_not_configured",
            origin="proxy",
            detail=_build_safe_error_detail("provider_not_configured"),
            http_status=503,
            provider=exc.provider,
            provider_error_code=exc.error_code,
        )

    if status_code == 429:
        code = "provider_rate_limited"
    elif status_code in {401, 403}:
        code = "provider_auth_failed"
    elif status_code is not None and 400 <= status_code < 500:
        code = "provider_bad_request"
    elif status_code is not None and status_code >= 500:
        code = "provider_unavailable"
    else:
        code = "provider_failed"

    return ChatProxyError(
        code=code,
        origin="provider",
        detail=_build_safe_error_detail(code),
        http_status=status_code,
        provider=exc.provider,
        provider_error_code=exc.error_code,
    )


def _run_chat_preflight(
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    db: Session,
) -> ProviderRoute:
    try:
        prepared = prepare_chat_completion_request(payload, session=session)
    except ValueError as exc:
        raise build_preparation_error(exc) from exc

    route = prepared.route
    try:
        ensure_provider_ready(provider=route.model.provider)
        validate_provider_request(
            route=route,
            messages=prepared.messages,
        )
    except ProviderConfigurationError as exc:
        raise ChatProxyError(
            code="provider_not_configured",
            origin="proxy",
            detail=_build_safe_error_detail("provider_not_configured"),
            http_status=503,
            provider=route.model.provider,
        ) from exc
    except ValueError as exc:
        raise _map_provider_request_validation_error(route=route, exc=exc) from exc
    except Exception as exc:
        raise _map_provider_request_validation_error(route=route, exc=exc) from exc

    if payload.chat_history_id and load_user_history(
        db,
        user_id=session.user_id,
        history_id=payload.chat_history_id,
    ) is None:
        raise ChatHistoryNotFoundError("chat history not found")

    try:
        enforce_chat_rate_limits(user_id=session.user_id)
    except ChatRateLimitExceededError as exc:
        raise _map_rate_limit_error(exc) from exc
    except ChatCoordinationUnavailableError as exc:
        raise ChatProxyError(
            code="coordination_unavailable",
            origin="proxy",
            detail=_build_safe_error_detail("coordination_unavailable"),
            http_status=503,
        ) from exc

    return route


def _map_provider_request_validation_error(
    *,
    route: ProviderRoute,
    exc: Exception,
) -> ChatProxyError:
    detail = str(exc)
    if _looks_like_proxy_provider_config_error(detail):
        return ChatProxyError(
            code="provider_not_configured",
            origin="proxy",
            detail=_build_safe_error_detail("provider_not_configured"),
            http_status=503,
            provider=route.model.provider,
        )
    return ChatProxyError(
        code="chat_failed",
        origin="proxy",
        detail=_build_safe_error_detail("chat_failed"),
        http_status=500,
        provider=route.model.provider,
    )


def _build_safe_error_detail(code: str) -> str:
    return get_error_message(code)


def _build_success_outcome(*, route: ProviderRoute, finish_reason: str | None) -> tuple[str, str]:
    if route.model.provider == "openai":
        return OPENAI_SUCCESS_RESULT_CODE, pick_openai_success_message()
    if route.model.provider == "anthropic":
        if finish_reason == "stop_sequence":
            return "anthropic_stop_stop_sequence", pick_anthropic_success_message()
        return ANTHROPIC_SUCCESS_RESULT_CODE, pick_anthropic_success_message()
    if route.model.provider == "vertex":
        return VERTEX_SUCCESS_RESULT_CODE, pick_vertex_success_message()
    return SUCCESS_RESULT_CODE, pick_success_message()


def _looks_like_proxy_provider_config_error(detail: str) -> bool:
    return any(
        marker in detail
        for marker in (
            "tool is selected but no",
            "cannot use allowed and blocked",
            "must not be blank",
            "must be at least",
            "could not be constructed",
        )
    )


def _encode_sse_event(event_name: str, payload: BaseModel) -> bytes:
    return f"event: {event_name}\ndata: {payload.model_dump_json()}\n\n".encode("utf-8")


__all__ = [
    "ChatHistoryUnavailableError",
    "create_chat_completion_stream",
]
