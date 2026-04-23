from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.postgres.models.chat_history import ChatMessage
from app.schemas.chat import ChatMessage as RequestChatMessage


def build_provider_context(
    db: Session,
    *,
    history_id: str,
) -> list[RequestChatMessage]:
    rows = db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.chat_history_id == history_id,
            ChatMessage.excluded_from_context.is_(False),
            ChatMessage.status != "error",
        )
        .order_by(ChatMessage.sequence.asc())
    ).scalars().all()

    messages: list[RequestChatMessage] = []
    for row in rows:
        content = row.content.strip()
        if not content:
            continue
        messages.append(RequestChatMessage(role=row.role, content=content))
    return messages

