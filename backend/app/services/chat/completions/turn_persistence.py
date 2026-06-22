from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import ChatMessageAttachment
from app.db.postgres.models.chat_history import ChatHistory, ChatMessage
from app.db.redis.chat_drafts import delete_chat_draft
from app.providers.types import ProviderRoute, ProviderUsageMetadata
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.histories.service import load_user_history
from app.services.chat.histories.state import (
    BUSY_REASON_SEND,
    INTERACTION_STATE_READY,
    INTERACTION_STATE_WAITING,
    apply_history_interaction_state,
)
from app.services.chat.histories.titles import build_title_from_prompt
from app.services.chat.histories.usage_summary import serialize_provider_usage, update_history_usage_summary
from app.services.chat.errors import ChatHistoryNotFoundError
from app.services.usage_ledger import append_chat_usage_ledger_event


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


def persist_chat_turn_start(
    db: Session,
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    history_id: str,
    draft_chat_id: str | None = None,
    route: ProviderRoute | None = None,
    attachment_snapshots: list[dict[str, object]] | None = None,
    first_response_deadline_at: datetime | None = None,
) -> PersistedChatTurn:
    latest_user_message = payload.messages[-1]
    if latest_user_message.role != "user":
        raise ValueError("last message must have role 'user'")

    history = load_user_history(db, user_id=session.user_id, history_id=history_id)
    created_from_draft = False
    if history is None and draft_chat_id and draft_chat_id == history_id:
        created_from_draft = True
        history = ChatHistory(
            id=history_id,
            user_id=session.user_id,
            title=build_title_from_prompt(latest_user_message.content),
            interaction_state=INTERACTION_STATE_WAITING,
            busy_reason=BUSY_REASON_SEND,
            created_at=utc_now(),
            updated_at=utc_now(),
            state_updated_at=utc_now(),
        )
        db.add(history)
        db.flush()
    elif history is None:
        raise ChatHistoryNotFoundError("chat history not found")

    next_sequence = _get_next_message_sequence(db, history_id=history.id)
    now = utc_now()
    initial_deadline_at = first_response_deadline_at or now + timedelta(
        seconds=max(1, settings.chat_provider_first_response_timeout_seconds)
    )
    if next_sequence == 1 and history.title == "New chat":
        history.title = build_title_from_prompt(latest_user_message.content)
    apply_history_interaction_state(
        history,
        interaction_state=INTERACTION_STATE_WAITING,
        busy_reason=BUSY_REASON_SEND,
    )
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
        deadline_at=initial_deadline_at,
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
    db.commit()
    if created_from_draft and draft_chat_id:
        delete_chat_draft(draft_chat_id=draft_chat_id)

    return PersistedChatTurn(
        history_id=history.id,
        user_id=session.user_id,
        auth_session_id=session.session_id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        model_id=route.model.public_id if route else payload.model_id,
        provider=route.model.provider if route else None,
        tool_ids=list(route.tool_ids if route else payload.tool_ids),
    )


def persist_chat_turn_success(
    db: Session,
    *,
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
    assistant_message = db.get(ChatMessage, assistant_message_id)
    if assistant_message is None:
        return False
    if assistant_message.status != "streaming":
        return False

    assistant_message.content = content
    assistant_message.status = "done"
    assistant_message.finish_reason = finish_reason
    assistant_message.result_code = result_code
    assistant_message.result_message = result_message
    usage_payload = serialize_provider_usage(usage)
    assistant_message.usage = usage_payload
    assistant_message.completed_at = now
    assistant_message.deadline_at = None
    assistant_message.updated_at = now
    _touch_history(db, history_id=history_id, now=now)
    _set_history_ready(db, history_id=history_id)
    update_history_usage_summary(
        db,
        history_id=history_id,
        message_usage=assistant_message.usage,
        aggregated_at=now,
    )
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
    db.commit()
    return True


def persist_chat_turn_first_response(
    db: Session,
    *,
    assistant_message_id: str,
    stream_timeout_seconds: int,
) -> None:
    now = utc_now()
    assistant_message = db.get(ChatMessage, assistant_message_id)
    if assistant_message is None or assistant_message.status != "streaming":
        return
    assistant_message.first_response_at = now
    assistant_message.deadline_at = now + timedelta(seconds=max(1, stream_timeout_seconds))
    if assistant_message.result_code is None:
        assistant_message.result_code = "provider_first_response_received"
        assistant_message.result_message = "Provider response started."
    assistant_message.updated_at = now
    db.commit()


def persist_chat_turn_failure(
    db: Session,
    *,
    history_id: str,
    user_message_id: str,
    assistant_message_id: str,
    content: str,
    result_code: str,
    result_message: str,
    detail: str,
) -> bool:
    now = utc_now()
    assistant_message = db.get(ChatMessage, assistant_message_id)
    if assistant_message is not None and assistant_message.status != "streaming":
        return False

    user_message = db.get(ChatMessage, user_message_id)
    if user_message is not None:
        user_message.excluded_from_context = True
        user_message.updated_at = now

    if assistant_message is not None:
        assistant_message.content = content
        assistant_message.status = "error"
        assistant_message.excluded_from_context = True
        assistant_message.result_code = result_code
        assistant_message.result_message = result_message
        assistant_message.error_detail = detail
        assistant_message.completed_at = now
        assistant_message.deadline_at = None
        assistant_message.updated_at = now

    _touch_history(db, history_id=history_id, now=now)
    _set_history_ready(db, history_id=history_id)
    db.commit()
    return assistant_message is not None


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


def _set_history_ready(
    db: Session,
    *,
    history_id: str,
) -> None:
    history = db.get(ChatHistory, history_id)
    if history is None:
        return
    apply_history_interaction_state(
        history,
        interaction_state=INTERACTION_STATE_READY,
        busy_reason=None,
    )


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
