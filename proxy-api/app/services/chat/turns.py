from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.config.time import utc_now
from app.db.postgres.models.chat_history import ChatHistory, ChatMessage
from app.providers.types import ProviderRoute, ProviderUsageMetadata
from app.schemas.chat import ChatCompletionRequest, ChatMessage as RequestChatMessage
from app.services.chat.errors import ChatHistoryNotFoundError
from app.services.chat.history_queries import load_user_history
from app.services.chat.provider_context import build_provider_context
from app.services.chat.titles import build_title_from_prompt


@dataclass(slots=True)
class PersistedChatTurn:
    history_id: str
    user_message_id: str
    assistant_message_id: str
    provider_messages: list[RequestChatMessage]


def persist_chat_turn_start(
    db: Session,
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    route: ProviderRoute,
) -> PersistedChatTurn:
    latest_user_message = payload.messages[-1]
    if latest_user_message.role != "user":
        raise ValueError("last message must have role 'user'")

    history = load_user_history(db, user_id=session.user_id, history_id=payload.chat_history_id)
    if history is None:
        if payload.chat_history_id:
            raise ChatHistoryNotFoundError("chat history not found")
        history = _create_history_for_first_prompt(
            db,
            user_id=session.user_id,
            prompt=latest_user_message.content,
        )

    next_sequence = _get_next_message_sequence(db, history_id=history.id)
    now = utc_now()
    user_message = ChatMessage(
        id=str(uuid4()),
        chat_history_id=history.id,
        sequence=next_sequence,
        role="user",
        content=latest_user_message.content,
        status="done",
        excluded_from_context=False,
        model_id=route.model.public_id,
        provider=route.model.provider,
        tool_ids=list(route.tool_ids),
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
        model_id=route.model.public_id,
        provider=route.model.provider,
        tool_ids=list(route.tool_ids),
        created_at=now,
        updated_at=now,
    )

    provider_messages = build_provider_context(db, history_id=history.id)
    provider_messages.append(RequestChatMessage(role="user", content=latest_user_message.content))

    history.last_message_at = now
    history.updated_at = now
    db.add(user_message)
    db.add(assistant_message)
    db.commit()

    return PersistedChatTurn(
        history_id=history.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        provider_messages=provider_messages,
    )


def persist_chat_turn_success(
    db: Session,
    *,
    history_id: str,
    assistant_message_id: str,
    content: str,
    finish_reason: str | None,
    usage: ProviderUsageMetadata | None,
) -> None:
    now = utc_now()
    assistant_message = db.get(ChatMessage, assistant_message_id)
    if assistant_message is None:
        return

    assistant_message.content = content
    assistant_message.status = "done"
    assistant_message.finish_reason = finish_reason
    assistant_message.usage = _serialize_usage(usage)
    assistant_message.updated_at = now
    _touch_history(db, history_id=history_id, now=now)
    db.commit()


def persist_chat_turn_failure(
    db: Session,
    *,
    history_id: str,
    user_message_id: str,
    assistant_message_id: str,
    content: str,
    detail: str,
) -> None:
    now = utc_now()
    user_message = db.get(ChatMessage, user_message_id)
    if user_message is not None:
        user_message.excluded_from_context = True
        user_message.updated_at = now

    assistant_message = db.get(ChatMessage, assistant_message_id)
    if assistant_message is not None:
        assistant_message.content = content or "An error happened while processing your request."
        assistant_message.status = "error"
        assistant_message.excluded_from_context = True
        assistant_message.error_detail = detail
        assistant_message.updated_at = now

    _touch_history(db, history_id=history_id, now=now)
    db.commit()


def _create_history_for_first_prompt(
    db: Session,
    *,
    user_id: str,
    prompt: str,
) -> ChatHistory:
    now = utc_now()
    history = ChatHistory(
        id=str(uuid4()),
        user_id=user_id,
        title=build_title_from_prompt(prompt),
        created_at=now,
        updated_at=now,
    )
    db.add(history)
    db.flush()
    return history


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


def _serialize_usage(usage: ProviderUsageMetadata | None) -> dict | None:
    if usage is None:
        return None
    return {
        "input_tokens": usage.prompt_token_count,
        "output_tokens": usage.candidates_token_count,
        "total_tokens": usage.total_token_count,
    }

