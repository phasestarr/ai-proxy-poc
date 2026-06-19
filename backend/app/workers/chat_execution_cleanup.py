from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.chat_history import ChatHistory, ChatMessage
from app.services.chat.completions.request_audit import persist_operator_event
from app.services.chat.histories.state import (
    BUSY_REASON_SEND,
    INTERACTION_STATE_READY,
    apply_history_interaction_state,
)

STALE_EXECUTION_RESULT_CODE = "provider_first_response_timeout"
STALE_EXECUTION_MESSAGE = "Chat turn was closed by housekeeping after the provider did not start responding in time."


def cleanup_stale_chat_executions(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    current_time = now or utc_now()
    cutoff = current_time - timedelta(seconds=max(1, settings.chat_provider_idle_timeout_seconds))
    cleaned_count = 0

    streaming_messages = db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.role == "assistant",
            ChatMessage.status == "streaming",
            ChatMessage.result_code.is_(None),
            ChatMessage.updated_at < cutoff,
        )
        .order_by(ChatMessage.updated_at.asc(), ChatMessage.id.asc())
    ).scalars().all()

    for assistant_message in streaming_messages:
        if _close_stale_streaming_message(db, assistant_message=assistant_message, now=current_time):
            cleaned_count += 1

    stale_histories = db.execute(
        select(ChatHistory)
        .where(
            ChatHistory.interaction_state != INTERACTION_STATE_READY,
            ChatHistory.busy_reason == BUSY_REASON_SEND,
            ChatHistory.state_updated_at < cutoff,
        )
        .order_by(ChatHistory.state_updated_at.asc(), ChatHistory.id.asc())
    ).scalars().all()

    for history in stale_histories:
        stale_state_updated_at = history.state_updated_at
        has_open_stream = db.execute(
            select(ChatMessage.id)
            .where(
                ChatMessage.chat_history_id == history.id,
                ChatMessage.role == "assistant",
                ChatMessage.status == "streaming",
            )
            .limit(1)
        ).scalar_one_or_none()
        if has_open_stream is not None:
            continue
        apply_history_interaction_state(
            history,
            interaction_state=INTERACTION_STATE_READY,
            busy_reason=None,
        )
        history.updated_at = current_time
        persist_operator_event(
            db,
            event_type="chat_execution_state_recovered",
            severity="warning",
            user_id=history.user_id,
            chat_history_id=history.id,
            operation="chat_completion",
            result_code=STALE_EXECUTION_RESULT_CODE,
            message="Recovered stale chat send state.",
            detail=STALE_EXECUTION_MESSAGE,
            metadata={
                "state_updated_at": stale_state_updated_at.isoformat(),
                "timeout_seconds": max(1, settings.chat_provider_idle_timeout_seconds),
            },
            commit=False,
        )
        cleaned_count += 1

    db.commit()
    return cleaned_count


def _close_stale_streaming_message(
    db: Session,
    *,
    assistant_message: ChatMessage,
    now: datetime,
) -> bool:
    if assistant_message.status != "streaming" or assistant_message.result_code is not None:
        return False

    user_message = db.execute(
        select(ChatMessage).where(
            ChatMessage.chat_history_id == assistant_message.chat_history_id,
            ChatMessage.sequence == assistant_message.sequence - 1,
            ChatMessage.role == "user",
        )
    ).scalar_one_or_none()
    if user_message is not None:
        user_message.excluded_from_context = True
        user_message.updated_at = now

    stale_assistant_updated_at = assistant_message.updated_at
    assistant_message.status = "error"
    assistant_message.excluded_from_context = True
    assistant_message.result_code = STALE_EXECUTION_RESULT_CODE
    assistant_message.result_message = "The selected provider did not start responding in time."
    assistant_message.error_detail = STALE_EXECUTION_MESSAGE
    assistant_message.completed_at = now
    assistant_message.updated_at = now

    history = db.get(ChatHistory, assistant_message.chat_history_id)
    if history is not None:
        apply_history_interaction_state(
            history,
            interaction_state=INTERACTION_STATE_READY,
            busy_reason=None,
        )
        history.updated_at = now
        history.last_message_at = now

    persist_operator_event(
        db,
        event_type="chat_execution_stale_closed",
        severity="error",
        user_id=history.user_id if history is not None else None,
        chat_history_id=assistant_message.chat_history_id,
        chat_message_id=assistant_message.id,
        model_id=assistant_message.model_id,
        provider=assistant_message.provider,
        operation="chat_completion",
        result_code=STALE_EXECUTION_RESULT_CODE,
        message=assistant_message.result_message,
        detail=STALE_EXECUTION_MESSAGE,
        metadata={
            "assistant_message_updated_at": stale_assistant_updated_at.isoformat(),
            "user_message_id": user_message.id if user_message is not None else None,
            "timeout_seconds": max(1, settings.chat_provider_idle_timeout_seconds),
        },
        commit=False,
    )
    return True
