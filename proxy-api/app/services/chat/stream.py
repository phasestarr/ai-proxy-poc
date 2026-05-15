"""
Purpose:
- Implement chat streaming orchestration for the backend service layer.

Responsibilities:
- Run provider-neutral request preflight before background execution starts
- Build the real provider context from DB-backed chat state
- Trigger context compaction before the main provider call when needed
- Persist a backend-owned chat turn only after the final request is ready
- Convert live provider output into SSE events when the client is still connected
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import logging

from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.db.postgres.session import SessionLocal
from app.db.redis.chat_drafts import set_chat_draft_state
from app.db.redis.chat_coordination import (
    ChatCoordinationUnavailableError,
    ChatRequestInProgressError,
    acquire_chat_execution_lease,
    release_chat_execution_lease,
)
from app.providers.types import PreparedProviderChatRequest
from app.schemas.chat import ChatCompletionRequest, ChatStreamStatusEvent
from app.services.chat.attachments import prepare_history_attachments_for_provider
from app.services.chat.context_budget import needs_context_compaction
from app.services.chat.errors import ChatHistoryNotFoundError, ChatProxyError
from app.services.chat.history_queries import load_user_history
from app.services.chat.interaction_state import (
    BUSY_REASON_SEND,
    INTERACTION_STATE_READY,
    INTERACTION_STATE_VALIDATING,
    apply_history_interaction_state,
)
from app.services.chat.rejections import persist_chat_proxy_rejection
from app.services.chat.request_preflight import ChatPreflightResult, build_safe_error_detail, run_chat_preflight
from app.services.chat.request_preparation import build_prepared_request, run_context_compaction
from app.services.chat.stream_events import (
    LiveChatStreamSink,
    build_error_event,
    build_start_event,
    stream_live_chat_completion,
)
from app.services.chat.turn_execution import run_chat_completion_turn
from app.services.chat.turns import persist_chat_turn_start

logger = logging.getLogger("uvicorn.error")

INPUT_TOKENS_ESTIMATED_STATUS = "context_input_tokens_estimated"
INPUT_TOKENS_EXACT_STATUS = "context_input_tokens_exact"
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
    try:
        lease = acquire_chat_execution_lease(chat_history_id=payload.conversation_id)
    except ChatRequestInProgressError as exc:
        raise ChatProxyError(
            code="request_in_progress",
            origin="proxy",
            detail=build_safe_error_detail("request_in_progress"),
            http_status=409,
            retry_after_seconds=exc.retry_after_seconds,
        ) from exc
    except ChatCoordinationUnavailableError as exc:
        raise ChatProxyError(
            code="coordination_unavailable",
            origin="proxy",
            detail=build_safe_error_detail("coordination_unavailable"),
            http_status=503,
        ) from exc

    try:
        preflight = run_chat_preflight(
            payload=payload,
            session=session,
            db=db,
        )
        _mark_preflight_target_validating(
            db=db,
            session=session,
            preflight=preflight,
        )
    except ChatHistoryNotFoundError as exc:
        release_chat_execution_lease(lease)
        raise ChatHistoryUnavailableError(str(exc)) from exc
    except Exception:
        release_chat_execution_lease(lease)
        raise

    sink = LiveChatStreamSink()
    asyncio.create_task(
        _run_chat_request_pipeline(
            payload=payload,
            session=session,
            preflight=preflight,
            lease=lease,
            sink=sink,
        )
    )
    return stream_live_chat_completion(sink)


async def _run_chat_request_pipeline(
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    preflight: ChatPreflightResult,
    lease,
    sink: LiveChatStreamSink,
) -> None:
    turn_started = False
    try:
        attachment_snapshots: list[dict[str, object]] = []
        built_context, prepared_request = await build_prepared_request(
            payload=payload,
            session=session,
            route=preflight.route,
            history_id=preflight.history_id,
            draft_chat_id=preflight.draft_chat_id,
        )
        emit_input_token_statuses(sink=sink, prepared_request=prepared_request)

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
            )
            _, prepared_request = await build_prepared_request(
                payload=payload,
                session=session,
                route=preflight.route,
                history_id=preflight.history_id,
                draft_chat_id=preflight.draft_chat_id,
            )
            emit_input_token_statuses(sink=sink, prepared_request=prepared_request)
            if needs_context_compaction(prepared_request):
                raise ChatProxyError(
                    code="context_still_too_large",
                    origin="proxy",
                    detail=build_safe_error_detail("context_still_too_large"),
                    http_status=400,
                )

        prepared_request, attachment_snapshots = await prepare_history_attachments_for_provider(
            user_id=session.user_id,
            history_id=preflight.history_id,
            route=preflight.route,
            prepared_request=prepared_request,
        )

        with SessionLocal() as turn_db:
            turn = persist_chat_turn_start(
                turn_db,
                payload=payload,
                session=session,
                history_id=preflight.history_id,
                draft_chat_id=preflight.draft_chat_id,
                route=preflight.route,
                attachment_snapshots=attachment_snapshots,
            )
            turn_started = True

        sink.emit("start", build_start_event(turn))
        await run_chat_completion_turn(
            turn=turn,
            prepared_request=prepared_request,
            route=preflight.route,
            sink=sink,
        )
    except ChatProxyError as exc:
        if not turn_started:
            _best_effort_reset_preflight_target_ready(
                session=session,
                preflight=preflight,
            )
            with SessionLocal() as rejection_db:
                persist_chat_proxy_rejection(
                    rejection_db,
                    session=session,
                    payload=payload,
                    error=exc,
                    route=preflight.route,
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
        if not turn_started:
            _best_effort_reset_preflight_target_ready(
                session=session,
                preflight=preflight,
            )
            with SessionLocal() as rejection_db:
                persist_chat_proxy_rejection(
                    rejection_db,
                    session=session,
                    payload=payload,
                    error=error,
                    route=preflight.route,
                )
        sink.emit("error", build_error_event(error))
    finally:
        release_chat_execution_lease(lease)


__all__ = [
    "ChatHistoryUnavailableError",
    "create_chat_completion_stream",
]


def emit_input_token_statuses(
    *,
    sink: LiveChatStreamSink,
    prepared_request: PreparedProviderChatRequest,
) -> None:
    sink.emit(
        "status",
        ChatStreamStatusEvent(
            provider=None,
            status_code=INPUT_TOKENS_ESTIMATED_STATUS,
            status_message=build_input_token_status_message(
                prefix="Estimated input tokens",
                token_count=prepared_request.estimated_input_tokens,
            ),
        ),
    )
    if prepared_request.resolved_input_tokens is None:
        return
    sink.emit(
        "status",
        ChatStreamStatusEvent(
            provider=None,
            status_code=INPUT_TOKENS_EXACT_STATUS,
            status_message=build_input_token_status_message(
                prefix="Exact input tokens",
                token_count=prepared_request.resolved_input_tokens,
            ),
        ),
    )


def build_compaction_started_message(prepared_request: PreparedProviderChatRequest) -> str:
    return (
        f"{CONTEXT_COMPACTION_STARTED_MESSAGE} "
        f"({prepared_request.budget_input_tokens:,} input tokens)"
    )


def build_input_token_status_message(*, prefix: str, token_count: int) -> str:
    return f"{prefix}: {token_count:,}"


def _mark_preflight_target_validating(
    *,
    db: Session,
    session: SessionContext,
    preflight: ChatPreflightResult,
) -> None:
    if preflight.draft_chat_id:
        set_chat_draft_state(
            draft_chat_id=preflight.draft_chat_id,
            interaction_state=INTERACTION_STATE_VALIDATING,
            busy_reason=BUSY_REASON_SEND,
        )
        return

    history = load_user_history(
        db,
        user_id=session.user_id,
        history_id=preflight.history_id,
    )
    if history is None:
        raise ChatHistoryUnavailableError("chat history not found")
    apply_history_interaction_state(
        history,
        interaction_state=INTERACTION_STATE_VALIDATING,
        busy_reason=BUSY_REASON_SEND,
    )
    db.commit()


def _reset_preflight_target_ready(
    *,
    db: Session,
    session: SessionContext,
    preflight: ChatPreflightResult,
) -> None:
    if preflight.draft_chat_id:
        set_chat_draft_state(
            draft_chat_id=preflight.draft_chat_id,
            interaction_state=INTERACTION_STATE_READY,
            busy_reason=None,
        )
        return

    history = load_user_history(
        db,
        user_id=session.user_id,
        history_id=preflight.history_id,
    )
    if history is None:
        return
    apply_history_interaction_state(
        history,
        interaction_state=INTERACTION_STATE_READY,
        busy_reason=None,
    )
    db.commit()


def _best_effort_reset_preflight_target_ready(
    *,
    session: SessionContext,
    preflight: ChatPreflightResult,
) -> None:
    try:
        with SessionLocal() as state_db:
            _reset_preflight_target_ready(
                db=state_db,
                session=session,
                preflight=preflight,
            )
    except Exception:
        logger.exception("Failed to restore conversation state after chat pipeline failure.")
