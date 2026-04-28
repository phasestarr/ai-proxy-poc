from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.time import utc_now
from app.db.postgres.models.chat_history import ChatHistory, ChatMessage
from app.services.chat.errors import ChatHistoryNotFoundError
from app.services.chat.titles import normalize_history_title


def create_chat_history(
    db: Session,
    *,
    user_id: str,
    title: str | None = None,
) -> ChatHistory:
    now = utc_now()
    history = ChatHistory(
        id=str(uuid4()),
        user_id=user_id,
        title=normalize_history_title(title) or "New chat",
        created_at=now,
        updated_at=now,
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return history


def list_chat_histories(
    db: Session,
    *,
    user_id: str,
) -> list[tuple[ChatHistory, int]]:
    activity_timestamp = func.coalesce(ChatHistory.last_message_at, ChatHistory.created_at)
    rows = db.execute(
        select(ChatHistory, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.chat_history_id == ChatHistory.id)
        .where(ChatHistory.user_id == user_id)
        .group_by(ChatHistory.id)
        .order_by(
            ChatHistory.pin_order.is_(None).asc(),
            ChatHistory.pin_order.asc(),
            activity_timestamp.desc(),
            ChatHistory.created_at.desc(),
        )
    ).all()
    return [(history, int(message_count)) for history, message_count in rows]


def get_chat_history(
    db: Session,
    *,
    user_id: str,
    history_id: str,
) -> tuple[ChatHistory, list[ChatMessage]]:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

    messages = db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_history_id == history.id)
        .order_by(ChatMessage.sequence.asc())
    ).scalars().all()
    return history, messages


def delete_chat_history(
    db: Session,
    *,
    user_id: str,
    history_id: str,
) -> None:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

    db.delete(history)
    db.commit()


def update_chat_history_title(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    title: str,
) -> ChatHistory:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

    history.title = normalize_history_title(title) or history.title
    db.commit()
    db.refresh(history)
    return history


def pin_chat_history(
    db: Session,
    *,
    user_id: str,
    history_id: str,
) -> ChatHistory:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

    if history.pin_order is None:
        current_max_pin_order = db.execute(
            select(func.max(ChatHistory.pin_order)).where(
                ChatHistory.user_id == user_id,
                ChatHistory.pin_order.is_not(None),
            )
        ).scalar_one_or_none()
        history.pin_order = int(current_max_pin_order or 0) + 1
        db.commit()
        db.refresh(history)

    return history


def unpin_chat_history(
    db: Session,
    *,
    user_id: str,
    history_id: str,
) -> ChatHistory:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

    if history.pin_order is not None:
        history.pin_order = None
        db.commit()
        db.refresh(history)

    return history


def load_user_history(
    db: Session,
    *,
    user_id: str,
    history_id: str | None,
) -> ChatHistory | None:
    if not history_id:
        return None

    return db.execute(
        select(ChatHistory).where(
            ChatHistory.id == history_id,
            ChatHistory.user_id == user_id,
        )
    ).scalar_one_or_none()
