"""
Purpose:
- Implement chat streaming orchestration for the backend service layer.

Responsibilities:
- Start a DB-token-backed chat operation
- Run validation, context preparation, compaction, and attachment preparation under the validating timeout
- Persist a backend-owned chat turn only after the final request is ready
- Convert live provider output into SSE events when the client is still connected
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import logging

from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.providers.types import PreparedProviderChatRequest, ProviderRoute
from app.schemas.chat import ChatCompletionRequest, ChatStreamStatusEvent
from app.services.chat.attachments import prepare_history_attachments_for_provider
from app.services.chat.completions.context.budget import needs_context_compaction
from app.services.chat.completions.validation import ChatValidationResult, build_safe_error_detail, run_chat_validation
from app.services.chat.completions.provider_execution import run_chat_completion_turn
from app.services.chat.completions.request_audit import persist_chat_proxy_rejection
from app.services.chat.completions.request_builder import build_prepared_request, run_context_compaction
from app.services.chat.completions.sse import (
    LiveChatStreamSink,
    build_error_event,
    build_start_event,
    stream_live_chat_completion,
)
from app.services.chat.completions.turn_persistence import PersistedChatTurn, persist_chat_turn_start
from app.services.chat.errors import ChatHistoryNotFoundError, ChatProxyError
from app.services.chat.histories.titles import build_title_from_prompt
from app.services.chat.operations import (
    OPERATION_PROVIDER_STREAMING,
    ChatOperationConflictError,
    ChatOperationExpiredError,
    OperationHandle,
    begin_history_operation,
    begin_new_history_send_operation,
    complete_operation,
    delete_empty_history_for_operation,
    provider_event_idle_timeout_seconds,
    provider_max_runtime_seconds,
    transition_operation,
    validating_timeout_seconds,
)
from app.db.postgres.session import SessionLocal

logger = logging.getLogger("uvicorn.error")

TEXT_TOKENS_ESTIMATED_STATUS = "context_text_tokens_estimated"
TEXT_TOKENS_EXACT_STATUS = "context_text_tokens_exact"
CONTEXT_COMPACTION_STARTED_STATUS = "context_compaction_started"
CONTEXT_COMPACTION_STARTED_MESSAGE = "Compressing conversation context..."


class ChatHistoryUnavailableError(RuntimeError):
    """Raised when a requested chat history cannot be used."""


def create_chat_completion_stream(
    payload: ChatCompletionRequest,
    *,
    session: SessionContext,
    db: Session,
) -> AsyncIterator[bytes]:
    operation: OperationHandle | None = None
    created_empty_history = False
    history_id: str | None = None
    try:
        history_id, operation, created_empty_history = _begin_send_operation(
            db,
            payload=payload,
            session=session,
        )
        validation = run_chat_validation(
            payload=payload,
            session=session,
            db=db,
        )
    except ChatOperationConflictError as exc:
        raise ChatProxyError(
            code="request_in_progress",
            origin="proxy",
            detail=build_safe_error_detail("request_in_progress"),
            http_status=409,
            retry_after_seconds=exc.retry_after_seconds,
        ) from exc
    except ChatHistoryNotFoundError as exc:
        _close_prestart_operation(
            db,
            operation=operation,
            created_empty_history=created_empty_history,
            error_code="chat_history_not_found",
            error_detail=str(exc),
        )
        raise ChatHistoryUnavailableError(str(exc)) from exc
    except ChatProxyError as exc:
        _close_prestart_operation(
            db,
            operation=operation,
            created_empty_history=created_empty_history,
            error_code=exc.code,
            error_detail=exc.detail,
        )
        raise
    except Exception:
        _close_prestart_operation(
            db,
            operation=operation,
            created_empty_history=created_empty_history,
            error_code="chat_failed",
            error_detail=build_safe_error_detail("chat_failed"),
        )
        raise

    sink = LiveChatStreamSink()
    asyncio.create_task(
        _run_chat_request_pipeline(
            payload=payload,
            session=session,
            validation=validation,
            history_id=history_id,
            operation=operation,
            created_empty_history=created_empty_history,
            sink=sink,
        )
    )
    return stream_live_chat_completion(sink)


async def _run_chat_request_pipeline(
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    validation: ChatValidationResult,
    history_id: str | None,
    operation: OperationHandle,
    created_empty_history: bool,
    sink: LiveChatStreamSink,
) -> None:
    turn: PersistedChatTurn | None = None
    try:
        turn, prepared_request = await asyncio.wait_for(
            _prepare_turn_for_provider(
                payload=payload,
                session=session,
                validation=validation,
                history_id=history_id,
                operation=operation,
                sink=sink,
            ),
            timeout=validating_timeout_seconds(),
        )
        sink.emit("start", build_start_event(turn))
        await run_chat_completion_turn(
            turn=turn,
            prepared_request=prepared_request,
            route=validation.route,
            sink=sink,
        )
    except TimeoutError:
        error = ChatProxyError(
            code="chat_validation_timeout",
            origin="proxy",
            detail=build_safe_error_detail("chat_validation_timeout"),
            http_status=504,
        )
        _best_effort_finish_prestart_failure(
            session=session,
            payload=payload,
            validation=validation,
            operation=operation,
            created_empty_history=created_empty_history,
            error=error,
            timed_out=True,
        )
        sink.emit("error", build_error_event(error))
    except ChatOperationExpiredError:
        error = ChatProxyError(
            code="chat_validation_timeout",
            origin="proxy",
            detail=build_safe_error_detail("chat_validation_timeout"),
            http_status=504,
        )
        if turn is None:
            _best_effort_finish_prestart_failure(
                session=session,
                payload=payload,
                validation=validation,
                operation=operation,
                created_empty_history=created_empty_history,
                error=error,
                timed_out=True,
            )
        sink.emit("error", build_error_event(error))
    except ChatProxyError as exc:
        if turn is None:
            _best_effort_finish_prestart_failure(
                session=session,
                payload=payload,
                validation=validation,
                operation=operation,
                created_empty_history=created_empty_history,
                error=exc,
            )
        sink.emit("error", build_error_event(exc))
    except Exception:
        logger.exception("Chat request pipeline failed.")
        error = ChatProxyError(
            code="chat_failed",
            origin="proxy",
            detail=build_safe_error_detail("chat_failed"),
            http_status=500,
        )
        if turn is None:
            _best_effort_finish_prestart_failure(
                session=session,
                payload=payload,
                validation=validation,
                operation=operation,
                created_empty_history=created_empty_history,
                error=error,
            )
        sink.emit("error", build_error_event(error))


async def _prepare_turn_for_provider(
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    validation: ChatValidationResult,
    history_id: str | None,
    operation: OperationHandle,
    sink: LiveChatStreamSink,
) -> tuple[PersistedChatTurn, PreparedProviderChatRequest]:
    attachment_snapshots: list[dict[str, object]] = []
    built_context, prepared_request = await build_prepared_request(
        payload=payload,
        session=session,
        route=validation.route,
        history_id=history_id,
    )
    emit_text_token_statuses(sink=sink, prepared_request=prepared_request)

    if needs_context_compaction(prepared_request):
        if built_context.history is None:
            raise ChatProxyError(
                code="context_still_too_large",
                origin="proxy",
                detail=build_safe_error_detail("context_still_too_large"),
                http_status=400,
            )

        sink.emit(
            "status",
            ChatStreamStatusEvent(
                provider=None,
                status_code=CONTEXT_COMPACTION_STARTED_STATUS,
                status_message=build_compaction_started_message(prepared_request),
            ),
        )
        await run_context_compaction(
            history=built_context.history,
            user_id=session.user_id,
            auth_session_id=session.session_id,
            operation=operation,
        )
        _, prepared_request = await build_prepared_request(
            payload=payload,
            session=session,
            route=validation.route,
            history_id=history_id,
        )
        emit_text_token_statuses(sink=sink, prepared_request=prepared_request)
        if needs_context_compaction(prepared_request):
            raise ChatProxyError(
                code="context_still_too_large",
                origin="proxy",
                detail=build_safe_error_detail("context_still_too_large"),
                http_status=400,
            )

    prepared_request, attachment_snapshots = await prepare_history_attachments_for_provider(
        user_id=session.user_id,
        history_id=history_id,
        operation=operation,
        route=validation.route,
        prepared_request=prepared_request,
    )

    with SessionLocal() as turn_db:
        transition_operation(
            turn_db,
            operation,
            state=OPERATION_PROVIDER_STREAMING,
            timeout_seconds=provider_event_idle_timeout_seconds(),
            provider_max_seconds=provider_max_runtime_seconds(),
        )
        turn = persist_chat_turn_start(
            turn_db,
            payload=payload,
            session=session,
            history_id=history_id,
            operation=operation,
            route=validation.route,
            attachment_snapshots=attachment_snapshots,
        )
    return turn, prepared_request


__all__ = [
    "ChatHistoryUnavailableError",
    "create_chat_completion_stream",
]


def emit_text_token_statuses(
    *,
    sink: LiveChatStreamSink,
    prepared_request: PreparedProviderChatRequest,
) -> None:
    sink.emit(
        "status",
        ChatStreamStatusEvent(
            provider=None,
            status_code=TEXT_TOKENS_ESTIMATED_STATUS,
            status_message=build_token_status_message(
                prefix="Estimated text tokens",
                token_count=prepared_request.estimated_text_tokens,
            ),
        ),
    )
    if prepared_request.resolved_text_tokens is None:
        return
    sink.emit(
        "status",
        ChatStreamStatusEvent(
            provider=None,
            status_code=TEXT_TOKENS_EXACT_STATUS,
            status_message=build_token_status_message(
                prefix="Exact text tokens",
                token_count=prepared_request.resolved_text_tokens,
            ),
        ),
    )


def build_compaction_started_message(prepared_request: PreparedProviderChatRequest) -> str:
    return (
        f"{CONTEXT_COMPACTION_STARTED_MESSAGE} "
        f"({prepared_request.budget_text_tokens:,} text tokens)"
    )


def build_token_status_message(*, prefix: str, token_count: int) -> str:
    return f"{prefix}: {token_count:,}"


def _begin_send_operation(
    db: Session,
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
) -> tuple[str | None, OperationHandle, bool]:
    if payload.chat_history_id:
        operation = begin_history_operation(
            db,
            session=session,
            history_id=payload.chat_history_id,
            operation_type="send",
            timeout_seconds=validating_timeout_seconds(),
        )
        return payload.chat_history_id, operation, False

    history, operation = begin_new_history_send_operation(
        db,
        session=session,
        title=build_title_from_prompt(payload.prompt),
        timeout_seconds=validating_timeout_seconds(),
    )
    return history.id, operation, True


def _close_prestart_operation(
    db: Session,
    *,
    operation: OperationHandle | None,
    created_empty_history: bool,
    error_code: str,
    error_detail: str,
) -> None:
    if operation is None:
        return
    complete_operation(
        db,
        operation,
        state="failed",
        result_code=error_code,
        error_detail=error_detail,
    )
    if created_empty_history:
        delete_empty_history_for_operation(db, operation)


def _best_effort_finish_prestart_failure(
    *,
    session: SessionContext,
    payload: ChatCompletionRequest,
    validation: ChatValidationResult,
    operation: OperationHandle,
    created_empty_history: bool,
    error: ChatProxyError,
    timed_out: bool = False,
) -> None:
    try:
        with SessionLocal() as failure_db:
            complete_operation(
                failure_db,
                operation,
                state="timed_out" if timed_out else "failed",
                result_code=error.code,
                error_detail=error.detail,
                allow_expired=timed_out,
            )
            if created_empty_history:
                delete_empty_history_for_operation(failure_db, operation)
        with SessionLocal() as rejection_db:
            persist_chat_proxy_rejection(
                rejection_db,
                session=session,
                payload=payload,
                error=error,
                route=validation.route,
            )
    except Exception:
        logger.exception("Failed to close chat operation after pre-provider failure.")
