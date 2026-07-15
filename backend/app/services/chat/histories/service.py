from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.postgres.models.chat_attachment import ChatHistoryFile
from app.db.postgres.models.chat_history import ChatHistory, ChatMessage
from app.services.chat.errors import ChatHistoryNotFoundError
from app.services.chat.histories.titles import normalize_history_title
from app.services.chat.operations import (
    ChatOperationExpiredError,
    OperationHandle,
    assert_operation_current,
    complete_operation,
)


def list_chat_histories(
    db: Session,
    *,
    user_id: str,
) -> list[tuple[ChatHistory, int, int]]:
    activity_timestamp = func.coalesce(ChatHistory.last_message_at, ChatHistory.created_at)
    message_counts = (
        select(
            ChatMessage.chat_history_id.label("chat_history_id"),
            func.count(ChatMessage.id).label("message_count"),
        )
        .group_by(ChatMessage.chat_history_id)
        .subquery()
    )
    attachment_counts = (
        select(
            ChatHistoryFile.chat_history_id.label("chat_history_id"),
            func.count(ChatHistoryFile.id).label("attachment_count"),
        )
        .group_by(ChatHistoryFile.chat_history_id)
        .subquery()
    )
    rows = db.execute(
        select(
            ChatHistory,
            func.coalesce(message_counts.c.message_count, 0),
            func.coalesce(attachment_counts.c.attachment_count, 0),
        )
        .outerjoin(message_counts, message_counts.c.chat_history_id == ChatHistory.id)
        .outerjoin(attachment_counts, attachment_counts.c.chat_history_id == ChatHistory.id)
        .where(ChatHistory.user_id == user_id)
        .order_by(
            ChatHistory.pin_order.is_(None).asc(),
            ChatHistory.pin_order.asc(),
            activity_timestamp.desc(),
            ChatHistory.created_at.desc(),
        )
    ).all()
    return [
        (history, int(message_count), int(attachment_count))
        for history, message_count, attachment_count in rows
    ]


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
        .options(selectinload(ChatMessage.blocks))
        .where(ChatMessage.chat_history_id == history.id)
        .order_by(ChatMessage.sequence.asc())
    ).scalars().all()
    return history, messages


def update_chat_history_title(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    title: str,
    operation: OperationHandle,
) -> ChatHistory:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

    assert_operation_current(db, operation)
    history.title = normalize_history_title(title) or history.title
    if not complete_operation(db, operation, state="succeeded", result_code="metadata_updated", commit=False):
        db.rollback()
        raise ChatOperationExpiredError("chat history operation expired")
    db.commit()
    db.refresh(history)
    return history


def pin_chat_history(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    operation: OperationHandle,
) -> ChatHistory:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

    assert_operation_current(db, operation)
    if history.pin_order is None:
        current_max_pin_order = db.execute(
            select(func.max(ChatHistory.pin_order)).where(
                ChatHistory.user_id == user_id,
                ChatHistory.pin_order.is_not(None),
            )
        ).scalar_one_or_none()
        history.pin_order = int(current_max_pin_order or 0) + 1

    if not complete_operation(db, operation, state="succeeded", result_code="metadata_updated", commit=False):
        db.rollback()
        raise ChatOperationExpiredError("chat history operation expired")
    db.commit()
    db.refresh(history)

    return history


def unpin_chat_history(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    operation: OperationHandle,
) -> ChatHistory:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

    assert_operation_current(db, operation)
    if history.pin_order is not None:
        history.pin_order = None

    if not complete_operation(db, operation, state="succeeded", result_code="metadata_updated", commit=False):
        db.rollback()
        raise ChatOperationExpiredError("chat history operation expired")
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
