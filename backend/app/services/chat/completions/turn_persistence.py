from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import ChatMessageAttachment
from app.db.postgres.models.chat_history import ChatHistory, ChatMessage
from app.providers.types import ProviderRoute, ProviderUsageMetadata
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.errors import ChatHistoryNotFoundError
from app.services.chat.histories.service import load_user_history
from app.services.chat.histories.titles import build_title_from_prompt
from app.services.chat.operations import (
    OperationHandle,
    assert_operation_current,
    complete_operation,
    record_provider_event_heartbeat,
)
from app.services.usage_ledger import append_chat_usage_ledger_event, serialize_provider_usage


@dataclass(slots=True)
class PersistedChatTurn:
    history_id: str
    user_id: str
    auth_session_id: str
    user_message_id: str
    assistant_message_id: str
    model_id: str | None
    provider: str | None
    tool_ids: list[str]
    operation: OperationHandle


def persist_chat_turn_start(
    db: Session,
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    history_id: str | None,
    operation: OperationHandle,
    route: ProviderRoute | None = None,
    attachment_snapshots: list[dict[str, object]] | None = None,
) -> PersistedChatTurn:
    latest_user_message = payload.messages[-1]
    if latest_user_message.role != "user":
        raise ValueError("last message must have role 'user'")

    operation_row = assert_operation_current(db, operation)
    history: ChatHistory | None = None

    if history_id:
        history = load_user_history(db, user_id=session.user_id, history_id=history_id)
        if history is None:
            raise ChatHistoryNotFoundError("chat history not found")
    else:
        raise ChatHistoryNotFoundError("chat history not found")

    next_sequence = _get_next_message_sequence(db, history_id=history.id)
    now = utc_now()
    if next_sequence == 1 and history.title == "New chat":
        history.title = build_title_from_prompt(latest_user_message.content)

    user_message = ChatMessage(
        id=str(uuid4()),
        chat_history_id=history.id,
        sequence=next_sequence,
        role="user",
        content=latest_user_message.content,
        status="done",
        excluded_from_context=False,
        model_id=route.model.public_id if route else payload.model_id,
        provider=route.model.provider if route else None,
        tool_ids=list(route.tool_ids if route else payload.tool_ids),
        created_at=now,
        updated_at=now,
    )
    assistant_message = ChatMessage(
        id=str(uuid4()),
        chat_history_id=history.id,
        sequence=next_sequence + 1,
        role="assistant",
        content="",
        status="streaming",
        excluded_from_context=False,
        model_id=route.model.public_id if route else payload.model_id,
        provider=route.model.provider if route else None,
        tool_ids=list(route.tool_ids if route else payload.tool_ids),
        deadline_at=operation_row.deadline_at,
        created_at=now,
        updated_at=now,
    )

    history.last_message_at = now
    history.updated_at = now
    db.add(user_message)
    db.add(assistant_message)
    for index, attachment_snapshot in enumerate(attachment_snapshots or [], start=1):
        db.add(
            ChatMessageAttachment(
                id=str(uuid4()),
                chat_message_id=user_message.id,
                attachment_index=index,
                chat_history_file_id=_optional_str(attachment_snapshot.get("chat_history_file_id")),
                stored_file_id=_optional_str(attachment_snapshot.get("stored_file_id")),
                display_name=str(attachment_snapshot.get("display_name") or ""),
                mime_type=str(attachment_snapshot.get("mime_type") or ""),
                byte_size=int(attachment_snapshot.get("byte_size") or 0),
                provider=str(attachment_snapshot.get("provider") or ""),
                provider_file_id=_optional_str(attachment_snapshot.get("provider_file_id")),
                token_count=_optional_int(attachment_snapshot.get("token_count")),
                created_at=now,
                updated_at=now,
            )
        )
    assert_operation_current(db, operation)
    db.commit()

    return PersistedChatTurn(
        history_id=history.id,
        user_id=session.user_id,
        auth_session_id=session.session_id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        model_id=route.model.public_id if route else payload.model_id,
        provider=route.model.provider if route else None,
        tool_ids=list(route.tool_ids if route else payload.tool_ids),
        operation=operation,
    )


def persist_chat_turn_success(
    db: Session,
    *,
    operation: OperationHandle,
    history_id: str,
    user_id: str,
    auth_session_id: str | None,
    assistant_message_id: str,
    content: str,
    finish_reason: str | None,
    usage: ProviderUsageMetadata | None,
    result_code: str,
    result_message: str,
) -> bool:
    now = utc_now()
    assert_operation_current(db, operation)
    assistant_message = db.get(ChatMessage, assistant_message_id)
    if assistant_message is None or assistant_message.status != "streaming":
        return False

    assistant_message.content = content
    assistant_message.status = "done"
    assistant_message.finish_reason = finish_reason
    assistant_message.result_code = result_code
    assistant_message.result_message = result_message
    usage_payload = serialize_provider_usage(usage)
    assistant_message.completed_at = now
    assistant_message.deadline_at = None
    assistant_message.updated_at = now
    _touch_history(db, history_id=history_id, now=now)
    append_chat_usage_ledger_event(
        db,
        user_id=user_id,
        auth_session_id=auth_session_id,
        chat_history_id=history_id,
        chat_message_id=assistant_message_id,
        provider=assistant_message.provider,
        model_id=assistant_message.model_id,
        tool_ids=list(assistant_message.tool_ids or []),
        result_code=result_code,
        usage_payload=usage_payload,
    )
    if not complete_operation(
        db,
        operation,
        state="succeeded",
        result_code=result_code,
        commit=False,
        allow_expired=True,
    ):
        db.rollback()
        return False
    db.commit()
    return True


def persist_chat_turn_provider_event(
    db: Session,
    *,
    operation: OperationHandle,
    assistant_message_id: str,
) -> bool:
    heartbeat = record_provider_event_heartbeat(db, operation)
    if not heartbeat.persisted:
        return True
    now = utc_now()
    assistant_message = db.get(ChatMessage, assistant_message_id)
    if assistant_message is None or assistant_message.status != "streaming":
        db.commit()
        return True
    assistant_message.first_response_at = assistant_message.first_response_at or now
    assistant_message.deadline_at = heartbeat.operation.deadline_at
    if assistant_message.result_code is None:
        assistant_message.result_code = "provider_first_event_received"
        assistant_message.result_message = "Provider response started."
    assistant_message.updated_at = now
    db.commit()
    return True


def persist_chat_turn_failure(
    db: Session,
    *,
    operation: OperationHandle,
    history_id: str,
    user_message_id: str,
    assistant_message_id: str,
    content: str,
    result_code: str,
    result_message: str,
    detail: str,
    exclude_from_context: bool = True,
    allow_expired_operation: bool = False,
    operation_state: str = "failed",
) -> bool:
    now = utc_now()
    try:
        assert_operation_current(db, operation, allow_expired=allow_expired_operation)
    except Exception:
        return False
    assistant_message = db.get(ChatMessage, assistant_message_id)
    if assistant_message is not None and assistant_message.status != "streaming":
        return False

    user_message = db.get(ChatMessage, user_message_id)
    if user_message is not None:
        user_message.excluded_from_context = exclude_from_context
        user_message.updated_at = now

    if assistant_message is not None:
        assistant_message.content = content
        assistant_message.status = "error"
        assistant_message.excluded_from_context = exclude_from_context
        assistant_message.result_code = result_code
        assistant_message.result_message = result_message
        assistant_message.error_detail = detail
        assistant_message.completed_at = now
        assistant_message.deadline_at = None
        assistant_message.updated_at = now

    _touch_history(db, history_id=history_id, now=now)
    if assistant_message is None:
        db.rollback()
        return False
    if not complete_operation(
        db,
        operation,
        state=operation_state,
        result_code=result_code,
        error_detail=detail,
        commit=False,
        allow_expired=allow_expired_operation,
    ):
        db.rollback()
        return False
    db.commit()
    return True


def _get_next_message_sequence(
    db: Session,
    *,
    history_id: str,
) -> int:
    current_max = db.execute(
        select(func.max(ChatMessage.sequence)).where(ChatMessage.chat_history_id == history_id)
    ).scalar_one_or_none()
    return int(current_max or 0) + 1


def _touch_history(
    db: Session,
    *,
    history_id: str,
    now,
) -> None:
    history = db.get(ChatHistory, history_id)
    if history is None:
        return
    history.updated_at = now
    history.last_message_at = now


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None
