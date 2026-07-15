from __future__ import annotations

import asyncio
import logging

from app.config.chat_outcomes import SUCCESS_RESULT_CODE, pick_success_message
from app.db.postgres.session import SessionLocal
from app.providers.anthropic.outcomes import (
    ANTHROPIC_SUCCESS_RESULT_CODE,
    get_anthropic_result_message,
    pick_anthropic_success_message,
)
from app.providers.dispatcher import (
    ProviderExecutionError,
    map_provider_raw_stream_events,
    stream_provider_raw_chat_completion,
)
from app.providers.openai.outcomes import (
    OPENAI_SUCCESS_RESULT_CODE,
    get_openai_result_message,
    pick_openai_success_message,
)
from app.providers.types import (
    PreparedProviderChatRequest,
    ProviderRawStreamChunk,
    ProviderRoute,
    ProviderStreamEvent,
)
from app.providers.vertex.outcomes import (
    VERTEX_SUCCESS_RESULT_CODE,
    get_vertex_result_message,
    pick_vertex_success_message,
)
from app.schemas.chat import (
    ChatStreamDeltaEvent,
    ChatStreamDoneEvent,
    ChatStreamProviderEvent,
    ChatStreamStatusEvent,
    ChatUsageSummary,
)
from app.services.chat.completions.validation import build_safe_error_detail
from app.services.chat.completions.sse import LiveChatStreamSink, build_error_event
from app.services.chat.completions.turn_persistence import (
    PersistedChatTurn,
    persist_chat_turn_provider_event,
    persist_chat_turn_failure,
    persist_chat_turn_success,
)
from app.services.chat.completions.request_audit import persist_operator_event
from app.services.chat.errors import ChatProxyError
from app.services.chat.operations import (
    ChatOperationExpiredError,
    provider_event_idle_timeout_seconds,
    provider_max_runtime_seconds,
)

logger = logging.getLogger("uvicorn.error")


async def run_chat_completion_turn(
    *,
    turn: PersistedChatTurn,
    prepared_request: PreparedProviderChatRequest,
    route: ProviderRoute,
    sink: LiveChatStreamSink,
) -> None:
    last_event: ProviderStreamEvent | None = None
    accumulated_text = ""
    last_status_code: str | None = None
    event_idle_timeout_seconds = provider_event_idle_timeout_seconds()
    max_runtime_seconds = provider_max_runtime_seconds()
    provider_event_seen = False
    final_answer_completed = False
    max_runtime_deadline = asyncio.get_running_loop().time() + max_runtime_seconds
    stream = None

    try:
        stream = stream_provider_raw_chat_completion(prepared_request=prepared_request).__aiter__()
        while True:
            try:
                raw_chunk = await _next_provider_raw_chunk(
                    stream,
                    timeout_seconds=_next_provider_timeout_seconds(
                        event_idle_timeout_seconds=event_idle_timeout_seconds,
                        max_runtime_deadline=max_runtime_deadline,
                    ),
                )
            except StopAsyncIteration:
                break
            except TimeoutError:
                await _close_provider_stream(stream)
                persist_provider_timeout(
                    turn=turn,
                    route=route,
                    sink=sink,
                    accumulated_text=accumulated_text,
                    first_response_received=provider_event_seen,
                    final_answer_completed=final_answer_completed,
                    event_idle_timeout_seconds=event_idle_timeout_seconds,
                    max_runtime_seconds=max_runtime_seconds,
                )
                return
            provider_event_seen = True
            if not mark_turn_provider_event(turn):
                persist_provider_timeout(
                    turn=turn,
                    route=route,
                    sink=sink,
                    accumulated_text=accumulated_text,
                    first_response_received=True,
                    final_answer_completed=final_answer_completed,
                    event_idle_timeout_seconds=event_idle_timeout_seconds,
                    max_runtime_seconds=max_runtime_seconds,
                )
                return
            stream_events = map_provider_raw_stream_events(
                prepared_request=prepared_request,
                raw_chunk=raw_chunk,
            )
            for stream_event in stream_events:
                last_event, accumulated_text, last_status_code = emit_provider_event(
                    stream_event=stream_event,
                    route=route,
                    sink=sink,
                    accumulated_text=accumulated_text,
                    last_status_code=last_status_code,
                )
                final_answer_completed = final_answer_completed or is_strong_final_answer_event(
                    route.model.provider,
                    stream_event,
                )
    except ProviderExecutionError as exc:
        error = map_provider_execution_error(exc)
        persist_turn_failure(
            turn,
            accumulated_text,
            error,
            exclude_from_context=not should_include_error_turn(
                accumulated_text=accumulated_text,
                final_answer_completed=final_answer_completed,
            ),
        )
        persist_turn_failure_event(turn=turn, route=route, error=error)
        sink.emit("error", build_error_event(error))
        return
    except ChatProxyError as exc:
        persist_turn_failure(
            turn,
            accumulated_text,
            exc,
            exclude_from_context=not should_include_error_turn(
                accumulated_text=accumulated_text,
                final_answer_completed=final_answer_completed,
            ),
        )
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
    finally:
        if stream is not None:
            await _close_provider_stream(stream)

    result_code, result_message = build_success_outcome(
        route=route,
        finish_reason=last_event.finish_reason if last_event else None,
    )
    try:
        with SessionLocal() as stream_db:
            persisted = persist_chat_turn_success(
                stream_db,
                operation=turn.operation,
                history_id=turn.history_id,
                user_id=turn.user_id,
                auth_session_id=turn.auth_session_id,
                assistant_message_id=turn.assistant_message_id,
                content=accumulated_text,
                finish_reason=last_event.finish_reason if last_event else None,
                usage=last_event.usage if last_event else None,
                result_code=result_code,
                result_message=result_message,
            )
    except ChatOperationExpiredError:
        persist_provider_timeout(
            turn=turn,
            route=route,
            sink=sink,
            accumulated_text=accumulated_text,
            first_response_received=provider_event_seen,
            final_answer_completed=final_answer_completed,
            event_idle_timeout_seconds=event_idle_timeout_seconds,
            max_runtime_seconds=max_runtime_seconds,
        )
        return
    if not persisted:
        return
    sink.emit(
        "done",
        ChatStreamDoneEvent(
            model=route.model.public_id,
            provider=route.model.provider,
            result_code=result_code,
            result_message=result_message,
            finish_reason=last_event.finish_reason if last_event else None,
            usage=map_usage_summary(last_event),
        ),
    )


def emit_provider_event(
    *,
    stream_event: ProviderStreamEvent,
    route: ProviderRoute,
    sink: LiveChatStreamSink,
    accumulated_text: str,
    last_status_code: str | None,
) -> tuple[ProviderStreamEvent, str, str | None]:
    if (
        stream_event.status_code
        and stream_event.status_message
        and stream_event.status_code != last_status_code
    ):
        last_status_code = stream_event.status_code
        sink.emit(
            "status",
            ChatStreamStatusEvent(
                provider=route.model.provider,
                status_code=stream_event.status_code,
                status_message=stream_event.status_message,
            ),
        )
    if stream_event.text_delta and stream_event.append_to_message_content:
        accumulated_text = f"{accumulated_text}{stream_event.text_delta}"
        sink.emit(
            "delta",
            ChatStreamDeltaEvent(delta_text=stream_event.text_delta),
        )
    elif should_emit_provider_event(stream_event):
        sink.emit(
            "provider_event",
            ChatStreamProviderEvent(
                provider=route.model.provider,
                event_kind=stream_event.kind,
                raw_event_type=stream_event.raw_event_type,
                text_delta=stream_event.text_delta or None,
                tool_type=stream_event.tool_type,
                item_id=stream_event.item_id,
                output_index=stream_event.output_index,
                content_index=stream_event.content_index,
                status_code=stream_event.status_code,
                status_message=stream_event.status_message,
                metadata=stream_event.metadata,
            ),
        )
    return stream_event, accumulated_text, last_status_code


def should_emit_provider_event(stream_event: ProviderStreamEvent) -> bool:
    if not stream_event.stream_to_client:
        return False
    if stream_event.kind in {"heartbeat", "completion", "status", "answer_delta"}:
        return False
    return bool(stream_event.text_delta or stream_event.metadata)


def mark_turn_provider_event(turn: PersistedChatTurn) -> bool:
    try:
        with SessionLocal() as stream_db:
            return persist_chat_turn_provider_event(
                stream_db,
                operation=turn.operation,
                assistant_message_id=turn.assistant_message_id,
            )
    except ChatOperationExpiredError:
        return False


def map_usage_summary(stream_event: ProviderStreamEvent | None) -> ChatUsageSummary | None:
    if stream_event is None or stream_event.usage is None:
        return None
    return ChatUsageSummary(
        input_tokens=stream_event.usage.prompt_token_count,
        output_tokens=stream_event.usage.candidates_token_count,
        total_tokens=stream_event.usage.total_token_count,
    )


def persist_turn_failure(
    turn: PersistedChatTurn,
    content: str,
    error: ChatProxyError,
    *,
    exclude_from_context: bool = True,
) -> None:
    with SessionLocal() as stream_db:
        persisted = persist_chat_turn_failure(
            stream_db,
            operation=turn.operation,
            history_id=turn.history_id,
            user_message_id=turn.user_message_id,
            assistant_message_id=turn.assistant_message_id,
            content=content,
            result_code=error.code,
            result_message=error.result_message,
            detail=error.detail,
            exclude_from_context=exclude_from_context,
            allow_expired_operation=True,
        )


def should_include_error_turn(
    *,
    accumulated_text: str,
    final_answer_completed: bool,
) -> bool:
    return final_answer_completed and bool(accumulated_text.strip())


def is_strong_final_answer_event(provider: str, stream_event: ProviderStreamEvent) -> bool:
    if provider == "openai":
        if (
            stream_event.raw_event_type == "response.output_item.done"
            and (stream_event.metadata or {}).get("item_type") == "message"
        ):
            return (stream_event.metadata or {}).get("status") == "completed"
        return (
            stream_event.raw_event_type == "response.completed"
            and stream_event.finish_reason == "completed"
        )

    if provider == "anthropic":
        return (
            stream_event.raw_event_type == "message_delta"
            and stream_event.finish_reason in {"end_turn", "stop_sequence", "refusal"}
        )

    if provider == "vertex_ai":
        return stream_event.kind == "completion" and stream_event.finish_reason == "STOP"

    return False


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
            user_id=turn.user_id,
            auth_session_id=turn.auth_session_id,
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
        if finish_reason and finish_reason != "completed":
            result_code = "openai_response_incomplete"
            return result_code, get_openai_result_message(result_code)
        return OPENAI_SUCCESS_RESULT_CODE, pick_openai_success_message()
    if route.model.provider == "anthropic":
        result_code = map_anthropic_finish_result_code(finish_reason)
        if result_code in {ANTHROPIC_SUCCESS_RESULT_CODE, "anthropic_stop_stop_sequence"}:
            return result_code, pick_anthropic_success_message()
        return result_code, get_anthropic_result_message(result_code)
    if route.model.provider == "vertex_ai":
        result_code = map_vertex_finish_result_code(finish_reason)
        if result_code == VERTEX_SUCCESS_RESULT_CODE:
            return result_code, pick_vertex_success_message()
        return result_code, get_vertex_result_message(result_code)
    return SUCCESS_RESULT_CODE, pick_success_message()


def map_anthropic_finish_result_code(finish_reason: str | None) -> str:
    if finish_reason in {None, "end_turn"}:
        return ANTHROPIC_SUCCESS_RESULT_CODE
    result_code_by_stop_reason = {
        "stop_sequence": "anthropic_stop_stop_sequence",
        "max_tokens": "anthropic_stop_max_tokens",
        "tool_use": "anthropic_stop_tool_use",
        "pause_turn": "anthropic_stop_pause_turn",
        "refusal": "anthropic_stop_refusal",
        "model_context_window_exceeded": "anthropic_stop_model_context_window_exceeded",
    }
    return result_code_by_stop_reason.get(finish_reason, "anthropic_stream_error")


def map_vertex_finish_result_code(finish_reason: str | None) -> str:
    if finish_reason in {None, "STOP"}:
        return VERTEX_SUCCESS_RESULT_CODE
    result_code_by_finish_reason = {
        "MAX_TOKENS": "vertex_finish_max_tokens",
        "SAFETY": "vertex_finish_safety",
        "RECITATION": "vertex_finish_recitation",
        "OTHER": "vertex_finish_other",
        "BLOCKLIST": "vertex_finish_blocklist",
        "PROHIBITED_CONTENT": "vertex_finish_prohibited_content",
        "SPII": "vertex_finish_spii",
        "MALFORMED_FUNCTION_CALL": "vertex_finish_malformed_function_call",
        "MODEL_ARMOR": "vertex_finish_model_armor",
        "IMAGE_SAFETY": "vertex_finish_image_safety",
        "IMAGE_PROHIBITED_CONTENT": "vertex_finish_image_prohibited_content",
        "IMAGE_RECITATION": "vertex_finish_image_recitation",
        "IMAGE_OTHER": "vertex_finish_image_other",
        "UNEXPECTED_TOOL_CALL": "vertex_finish_unexpected_tool_call",
        "NO_IMAGE": "vertex_finish_no_image",
    }
    return result_code_by_finish_reason.get(finish_reason, "vertex_stream_error")


async def _next_provider_raw_chunk(
    stream,
    *,
    timeout_seconds: float | None = None,
    deadline: float | None = None,
) -> ProviderRawStreamChunk:
    effective_timeout_seconds = timeout_seconds
    if deadline is not None:
        remaining_seconds = deadline - asyncio.get_running_loop().time()
        if remaining_seconds <= 0:
            raise TimeoutError
        effective_timeout_seconds = (
            remaining_seconds
            if effective_timeout_seconds is None
            else min(effective_timeout_seconds, remaining_seconds)
        )
    if effective_timeout_seconds is None:
        effective_timeout_seconds = provider_event_idle_timeout_seconds()
    return await asyncio.wait_for(
        anext(stream),
        timeout=effective_timeout_seconds,
    )


async def _close_provider_stream(stream) -> None:
    close = getattr(stream, "aclose", None)
    if not callable(close):
        return
    try:
        await close()
    except Exception:
        logger.exception("Failed to close provider stream.")


def persist_provider_timeout(
    *,
    turn: PersistedChatTurn,
    route: ProviderRoute,
    sink: LiveChatStreamSink,
    accumulated_text: str,
    first_response_received: bool,
    final_answer_completed: bool,
    event_idle_timeout_seconds: int,
    max_runtime_seconds: int,
) -> None:
    code = "provider_response_timeout" if first_response_received else "provider_first_response_timeout"
    event_type = (
        "chat_provider_response_timeout"
        if first_response_received
        else "chat_provider_first_response_timeout"
    )
    error = ChatProxyError(
        code=code,
        origin="proxy",
        detail=build_safe_error_detail(code),
        http_status=504,
        provider=route.model.provider,
    )
    with SessionLocal() as stream_db:
        persisted = persist_chat_turn_failure(
            stream_db,
            operation=turn.operation,
            history_id=turn.history_id,
            user_message_id=turn.user_message_id,
            assistant_message_id=turn.assistant_message_id,
            content=accumulated_text,
            result_code=error.code,
            result_message=error.result_message,
            detail=error.detail,
            exclude_from_context=not should_include_error_turn(
                accumulated_text=accumulated_text,
                final_answer_completed=final_answer_completed,
            ),
            allow_expired_operation=True,
            operation_state="timed_out",
        )
    with SessionLocal() as event_db:
        persist_operator_event(
            event_db,
            event_type=event_type,
            severity="error",
            user_id=turn.user_id,
            auth_session_id=turn.auth_session_id,
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
                "event_idle_timeout_seconds": event_idle_timeout_seconds,
                "max_runtime_seconds": max_runtime_seconds,
                "timeout_phase": "stream" if first_response_received else "first_response",
                "user_message_id": turn.user_message_id,
                "first_response_received": first_response_received,
            },
        )
    sink.emit("error", build_error_event(error))


def _next_provider_timeout_seconds(
    *,
    event_idle_timeout_seconds: int,
    max_runtime_deadline: float,
) -> float:
    remaining_runtime = max_runtime_deadline - asyncio.get_running_loop().time()
    if remaining_runtime <= 0:
        raise TimeoutError
    return min(float(event_idle_timeout_seconds), remaining_runtime)


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
