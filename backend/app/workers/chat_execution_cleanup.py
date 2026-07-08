from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import ChatDraftFile
from app.db.postgres.models.chat_history import ChatDraft, ChatHistory, ChatMessage, ChatOperation
from app.services.chat.attachments.storage import cleanup_orphan_stored_file
from app.services.chat.completions.request_audit import persist_operator_event
from app.services.chat.operations import TERMINAL_OPERATION_STATES

STALE_FIRST_RESPONSE_RESULT_CODE = "provider_first_response_timeout"
STALE_RESPONSE_RESULT_CODE = "provider_response_timeout"
STALE_VALIDATION_RESULT_CODE = "chat_validation_timeout"
STALE_EXECUTION_MESSAGE = "Chat turn was closed by housekeeping after its operation deadline expired."


async def cleanup_stale_chat_executions(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    current_time = now or utc_now()
    cleaned_count = 0

    stale_operations = db.execute(
        select(ChatOperation)
        .where(
            ChatOperation.state.notin_(tuple(TERMINAL_OPERATION_STATES)),
            or_(
                ChatOperation.deadline_at <= current_time,
                ChatOperation.provider_max_deadline_at <= current_time,
            ),
        )
        .order_by(ChatOperation.deadline_at.asc(), ChatOperation.id.asc())
    ).scalars().all()

    for operation in stale_operations:
        if _close_stale_operation(db, operation=operation, now=current_time):
            cleaned_count += 1

    streaming_messages = db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.role == "assistant",
            ChatMessage.status == "streaming",
            ChatMessage.deadline_at.is_not(None),
            ChatMessage.deadline_at <= current_time,
        )
        .order_by(ChatMessage.deadline_at.asc(), ChatMessage.id.asc())
    ).scalars().all()

    for assistant_message in streaming_messages:
        if _close_stale_streaming_message(db, assistant_message=assistant_message, now=current_time):
            cleaned_count += 1

    expired_drafts = db.execute(
        select(ChatDraft)
        .where(
            ChatDraft.lifecycle_state.in_(("active", "expired")),
            ChatDraft.active_operation_id.is_(None),
            ChatDraft.expires_at <= current_time,
        )
        .order_by(ChatDraft.expires_at.asc(), ChatDraft.id.asc())
    ).scalars().all()
    for draft in expired_drafts:
        await _delete_expired_draft(db, draft=draft)
        cleaned_count += 1

    db.commit()
    return cleaned_count


async def _delete_expired_draft(
    db: Session,
    *,
    draft: ChatDraft,
) -> None:
    draft_files = db.execute(
        select(ChatDraftFile)
        .where(ChatDraftFile.draft_id == draft.id)
        .with_for_update()
    ).scalars().all()
    stored_file_ids = {draft_file.stored_file_id for draft_file in draft_files}
    for draft_file in draft_files:
        db.delete(draft_file)
    db.flush()
    for stored_file_id in stored_file_ids:
        await cleanup_orphan_stored_file(db, stored_file_id=stored_file_id)
    db.delete(draft)


def _close_stale_operation(
    db: Session,
    *,
    operation: ChatOperation,
    now: datetime,
) -> bool:
    if operation.state in TERMINAL_OPERATION_STATES:
        return False

    result_code = _operation_timeout_code(operation)
    operation.state = "timed_out"
    operation.result_code = operation.result_code or result_code
    operation.error_detail = operation.error_detail or STALE_EXECUTION_MESSAGE
    operation.completed_at = operation.completed_at or now
    operation.updated_at = now

    if operation.chat_history_id:
        _close_streaming_messages_for_history(
            db,
            history_id=operation.chat_history_id,
            now=now,
            result_code=result_code,
        )

    if operation.scope_type == "history":
        history = db.get(ChatHistory, operation.scope_id)
        if history is not None and history.active_operation_id == operation.id:
            history.active_operation_id = None
            history.active_operation_token = None
            if history.lifecycle_state == "deleting":
                history.lifecycle_state = "active"
            history.updated_at = now
    else:
        draft = db.get(ChatDraft, operation.scope_id)
        if draft is not None and draft.active_operation_id == operation.id:
            draft.active_operation_id = None
            draft.active_operation_token = None
            if draft.expires_at <= now:
                draft.lifecycle_state = "expired"
            draft.updated_at = now

    persist_operator_event(
        db,
        event_type="chat_operation_timed_out",
        severity="error",
        user_id=operation.user_id,
        chat_history_id=operation.chat_history_id,
        model_id=None,
        provider=None,
        operation=operation.operation_type,
        result_code=result_code,
        message="Recovered expired chat operation.",
        detail=STALE_EXECUTION_MESSAGE,
        metadata={
            "operation_id": operation.id,
            "operation_state": operation.state,
            "operation_type": operation.operation_type,
            "deadline_at": operation.deadline_at.isoformat(),
            "provider_max_deadline_at": (
                operation.provider_max_deadline_at.isoformat()
                if operation.provider_max_deadline_at
                else None
            ),
        },
        commit=False,
    )
    return True


def _close_streaming_messages_for_history(
    db: Session,
    *,
    history_id: str,
    now: datetime,
    result_code: str,
) -> None:
    messages = db.execute(
        select(ChatMessage).where(
            ChatMessage.chat_history_id == history_id,
            ChatMessage.role == "assistant",
            ChatMessage.status == "streaming",
        )
    ).scalars().all()
    for assistant_message in messages:
        _close_stale_streaming_message(
            db,
            assistant_message=assistant_message,
            now=now,
            forced_result_code=result_code,
        )


def _close_stale_streaming_message(
    db: Session,
    *,
    assistant_message: ChatMessage,
    now: datetime,
    forced_result_code: str | None = None,
) -> bool:
    if assistant_message.status != "streaming":
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

    result_code = forced_result_code or (
        STALE_RESPONSE_RESULT_CODE
        if assistant_message.first_response_at is not None
        else STALE_FIRST_RESPONSE_RESULT_CODE
    )
    result_message = (
        "The selected provider did not start responding in time."
        if result_code == STALE_FIRST_RESPONSE_RESULT_CODE
        else "The selected provider stopped responding in time."
    )
    if result_code == STALE_VALIDATION_RESULT_CODE:
        result_message = "Chat validation took too long."

    assistant_message.status = "error"
    assistant_message.excluded_from_context = True
    assistant_message.result_code = result_code
    assistant_message.result_message = result_message
    assistant_message.error_detail = STALE_EXECUTION_MESSAGE
    assistant_message.completed_at = now
    assistant_message.deadline_at = None
    assistant_message.updated_at = now

    history = db.get(ChatHistory, assistant_message.chat_history_id)
    if history is not None:
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
        result_code=result_code,
        message=assistant_message.result_message,
        detail=STALE_EXECUTION_MESSAGE,
        metadata={
            "user_message_id": user_message.id if user_message is not None else None,
            "assistant_message_first_response_at": (
                assistant_message.first_response_at.isoformat()
                if assistant_message.first_response_at
                else None
            ),
        },
        commit=False,
    )
    return True


def _operation_timeout_code(operation: ChatOperation) -> str:
    if operation.state == "validating":
        return STALE_VALIDATION_RESULT_CODE
    if operation.first_provider_event_at is None:
        return STALE_FIRST_RESPONSE_RESULT_CODE
    return STALE_RESPONSE_RESULT_CODE
