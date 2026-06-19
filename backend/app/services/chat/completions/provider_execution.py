from __future__ import annotations

import asyncio
import logging

from app.config.settings import settings
from app.config.chat_outcomes import SUCCESS_RESULT_CODE, pick_success_message
from app.db.postgres.session import SessionLocal
from app.providers.anthropic.outcomes import ANTHROPIC_SUCCESS_RESULT_CODE, pick_anthropic_success_message
from app.providers.dispatcher import ProviderExecutionError, stream_provider_chat_completion
from app.providers.openai.outcomes import OPENAI_SUCCESS_RESULT_CODE, pick_openai_success_message
from app.providers.types import PreparedProviderChatRequest, ProviderRoute, ProviderStreamChunk
from app.providers.vertex.outcomes import VERTEX_SUCCESS_RESULT_CODE, pick_vertex_success_message
from app.schemas.chat import ChatStreamDeltaEvent, ChatStreamDoneEvent, ChatStreamStatusEvent, ChatUsageSummary
from app.services.chat.completions.preflight import build_safe_error_detail
from app.services.chat.completions.sse import LiveChatStreamSink, build_error_event
from app.services.chat.completions.turn_persistence import (
    PersistedChatTurn,
    persist_chat_turn_first_response,
    persist_chat_turn_failure,
    persist_chat_turn_success,
)
from app.services.chat.completions.request_audit import persist_operator_event
from app.services.chat.errors import ChatProxyError
from app.services.chat.histories.usage_summary import extract_token_summary

logger = logging.getLogger("uvicorn.error")


async def run_chat_completion_turn(
    *,
    turn: PersistedChatTurn,
    prepared_request: PreparedProviderChatRequest,
    route: ProviderRoute,
    sink: LiveChatStreamSink,
) -> None:
    last_chunk: ProviderStreamChunk | None = None
    accumulated_text = ""
    last_status_code: str | None = None

    try:
        stream = stream_provider_chat_completion(prepared_request=prepared_request).__aiter__()
        try:
            first_chunk = await asyncio.wait_for(
                anext(stream),
                timeout=max(1, settings.chat_provider_idle_timeout_seconds),
            )
        except StopAsyncIteration:
            first_chunk = None
        except TimeoutError:
            error = ChatProxyError(
                code="provider_first_response_timeout",
                origin="proxy",
                detail=build_safe_error_detail("provider_first_response_timeout"),
                http_status=504,
                provider=route.model.provider,
            )
            persist_turn_failure(turn, accumulated_text, error)
            with SessionLocal() as event_db:
                persist_operator_event(
                    event_db,
                    event_type="chat_provider_first_response_timeout",
                    severity="error",
                    user_id=None,
                    chat_history_id=turn.history_id,
                    chat_message_id=turn.assistant_message_id,
                    model_id=route.model.public_id,
                    provider=route.model.provider,
                    operation="chat_completion",
                    result_code=error.code,
                    http_status=error.http_status,
                    message=error.result_message,
                    detail=error.detail,
                    metadata={
                        "timeout_seconds": max(1, settings.chat_provider_idle_timeout_seconds),
                        "user_message_id": turn.user_message_id,
                    },
                )
            sink.emit("error", build_error_event(error))
            return

        if first_chunk is not None:
            mark_turn_first_response(turn)
            last_chunk, accumulated_text, last_status_code = emit_provider_chunk(
                chunk=first_chunk,
                route=route,
                sink=sink,
                accumulated_text=accumulated_text,
                last_status_code=last_status_code,
            )

        async for chunk in stream:
            last_chunk, accumulated_text, last_status_code = emit_provider_chunk(
                chunk=chunk,
                route=route,
                sink=sink,
                accumulated_text=accumulated_text,
                last_status_code=last_status_code,
            )
    except ProviderExecutionError as exc:
        error = map_provider_execution_error(exc)
        persist_turn_failure(turn, accumulated_text, error)
        persist_turn_failure_event(turn=turn, route=route, error=error)
        sink.emit("error", build_error_event(error))
        return
    except ChatProxyError as exc:
        persist_turn_failure(turn, accumulated_text, exc)
        persist_turn_failure_event(turn=turn, route=route, error=exc)
        sink.emit("error", build_error_event(exc))
        return
    except Exception:
        logger.exception("Chat background execution failed.")
        error = ChatProxyError(
            code="chat_failed",
            origin="proxy",
            detail=build_safe_error_detail("chat_failed"),
            http_status=500,
        )
        persist_turn_failure(turn, accumulated_text, error)
        persist_turn_failure_event(turn=turn, route=route, error=error)
        sink.emit("error", build_error_event(error))
        return

    result_code, result_message = build_success_outcome(
        route=route,
        finish_reason=last_chunk.finish_reason if last_chunk else None,
    )
    with SessionLocal() as stream_db:
        persisted = persist_chat_turn_success(
            stream_db,
            history_id=turn.history_id,
            assistant_message_id=turn.assistant_message_id,
            content=accumulated_text,
            finish_reason=last_chunk.finish_reason if last_chunk else None,
            usage=last_chunk.usage if last_chunk else None,
            result_code=result_code,
            result_message=result_message,
        )
    if not persisted:
        return
    sink.emit(
        "done",
        ChatStreamDoneEvent(
            model=route.model.public_id,
            provider=route.model.provider,
            result_code=result_code,
            result_message=result_message,
            finish_reason=last_chunk.finish_reason if last_chunk else None,
            usage=map_usage_summary(last_chunk),
        ),
    )


def emit_provider_chunk(
    *,
    chunk: ProviderStreamChunk,
    route: ProviderRoute,
    sink: LiveChatStreamSink,
    accumulated_text: str,
    last_status_code: str | None,
) -> tuple[ProviderStreamChunk, str, str | None]:
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
    return chunk, accumulated_text, last_status_code


def mark_turn_first_response(turn: PersistedChatTurn) -> None:
    with SessionLocal() as stream_db:
        persist_chat_turn_first_response(
            stream_db,
            assistant_message_id=turn.assistant_message_id,
        )


def map_usage_summary(chunk: ProviderStreamChunk | None) -> ChatUsageSummary | None:
    if chunk is None or chunk.usage is None:
        return None
    serialized_usage = {
        "normalized": {
            "input_tokens_reported": chunk.usage.prompt_token_count,
            "output_tokens_reported": chunk.usage.candidates_token_count,
            "total_tokens_reported": chunk.usage.total_token_count,
        }
    }
    token_summary = extract_token_summary(serialized_usage)
    return ChatUsageSummary(
        input_tokens=token_summary.get("input_tokens"),
        output_tokens=token_summary.get("output_tokens"),
        total_tokens=token_summary.get("total_tokens"),
    )


def persist_turn_failure(
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


def persist_turn_failure_event(
    *,
    turn: PersistedChatTurn,
    route: ProviderRoute,
    error: ChatProxyError,
) -> None:
    with SessionLocal() as event_db:
        persist_operator_event(
            event_db,
            event_type="chat_turn_failed",
            severity="error" if (error.http_status or 500) >= 500 else "warning",
            chat_history_id=turn.history_id,
            chat_message_id=turn.assistant_message_id,
            model_id=route.model.public_id,
            provider=route.model.provider,
            operation="chat_completion",
            result_code=error.code,
            http_status=error.http_status,
            retry_after_seconds=error.retry_after_seconds,
            message=error.result_message,
            detail=error.detail,
            metadata={"user_message_id": turn.user_message_id, "origin": error.origin},
        )


def build_success_outcome(*, route: ProviderRoute, finish_reason: str | None) -> tuple[str, str]:
    if route.model.provider == "openai":
        return OPENAI_SUCCESS_RESULT_CODE, pick_openai_success_message()
    if route.model.provider == "anthropic":
        if finish_reason == "stop_sequence":
            return "anthropic_stop_stop_sequence", pick_anthropic_success_message()
        return ANTHROPIC_SUCCESS_RESULT_CODE, pick_anthropic_success_message()
    if route.model.provider == "vertex_ai":
        return VERTEX_SUCCESS_RESULT_CODE, pick_vertex_success_message()
    return SUCCESS_RESULT_CODE, pick_success_message()


def map_provider_execution_error(exc: ProviderExecutionError) -> ChatProxyError:
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

    if looks_like_proxy_provider_config_error(raw_detail):
        return ChatProxyError(
            code="provider_not_configured",
            origin="proxy",
            detail=build_safe_error_detail("provider_not_configured"),
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
        detail=build_safe_error_detail(code),
        http_status=status_code,
        provider=exc.provider,
        provider_error_code=exc.error_code,
    )


def looks_like_proxy_provider_config_error(detail: str) -> bool:
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
