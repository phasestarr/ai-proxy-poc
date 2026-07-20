from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.config.runtime import STALE_EMPTY_HISTORY_MIN_AGE_MINUTES
from app.config.settings import settings
from app.db.postgres.models.chat_attachment import ChatHistoryFile
from app.db.postgres.models.chat_history import ChatHistory, ChatMessage


def delete_stale_empty_histories(
    db: Session,
    *,
    now: datetime,
) -> int:
    deleted_count = 0
    stale_empty_history_cutoff = now - timedelta(
        minutes=max(STALE_EMPTY_HISTORY_MIN_AGE_MINUTES, settings.housekeeping_interval_minutes)
    )
    stale_empty_histories = db.execute(
        select(ChatHistory).where(
            ChatHistory.last_message_at.is_(None),
            ChatHistory.active_operation_id.is_(None),
            ChatHistory.created_at <= stale_empty_history_cutoff,
            ~exists(
                select(ChatMessage.id).where(ChatMessage.chat_history_id == ChatHistory.id)
            ),
            ~exists(
                select(ChatHistoryFile.id).where(ChatHistoryFile.chat_history_id == ChatHistory.id)
            ),
        )
    ).scalars().all()
    for history in stale_empty_histories:
        db.delete(history)
        deleted_count += 1
    db.commit()
    return deleted_count
