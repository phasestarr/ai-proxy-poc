from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.time import utc_now
from app.db.postgres.models.chat_history import ChatContextCheckpoint
from app.providers.types import ProviderUsageMetadata
from app.services.chat.usage_summary import serialize_provider_usage


def load_ready_chat_context_checkpoint(
    db: Session,
    *,
    history_id: str,
) -> ChatContextCheckpoint | None:
    return db.execute(
        select(ChatContextCheckpoint).where(
            ChatContextCheckpoint.chat_history_id == history_id,
            ChatContextCheckpoint.status == "ready",
        )
    ).scalar_one_or_none()


def mark_chat_context_checkpoint_building(
    db: Session,
    *,
    user_id: str,
    history_id: str,
) -> ChatContextCheckpoint:
    checkpoint = _load_checkpoint(db, history_id=history_id)
    now = utc_now()
    if checkpoint is None:
        checkpoint = ChatContextCheckpoint(
            id=str(uuid4()),
            user_id=user_id,
            chat_history_id=history_id,
            created_at=now,
            updated_at=now,
        )
        db.add(checkpoint)

    checkpoint.status = "building"
    checkpoint.error_detail = None
    checkpoint.requested_at = now
    checkpoint.updated_at = now
    db.commit()
    db.refresh(checkpoint)
    return checkpoint


def persist_chat_context_checkpoint_ready(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    summary_text: str,
    covered_through_sequence: int | None,
    model_id: str,
    provider: str,
    usage: ProviderUsageMetadata | None,
) -> ChatContextCheckpoint:
    checkpoint = _load_checkpoint(db, history_id=history_id)
    now = utc_now()
    if checkpoint is None:
        checkpoint = ChatContextCheckpoint(
            id=str(uuid4()),
            user_id=user_id,
            chat_history_id=history_id,
            created_at=now,
        )
        db.add(checkpoint)

    checkpoint.status = "ready"
    checkpoint.summary_text = summary_text
    checkpoint.covered_through_sequence = covered_through_sequence
    checkpoint.model_id = model_id
    checkpoint.provider = provider
    checkpoint.usage = serialize_provider_usage(usage)
    checkpoint.error_detail = None
    checkpoint.completed_at = now
    checkpoint.updated_at = now
    db.commit()
    db.refresh(checkpoint)
    return checkpoint


def persist_chat_context_checkpoint_failure(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    detail: str,
    model_id: str,
    provider: str,
) -> ChatContextCheckpoint:
    checkpoint = _load_checkpoint(db, history_id=history_id)
    now = utc_now()
    if checkpoint is None:
        checkpoint = ChatContextCheckpoint(
            id=str(uuid4()),
            user_id=user_id,
            chat_history_id=history_id,
            created_at=now,
        )
        db.add(checkpoint)

    checkpoint.status = "failed"
    checkpoint.model_id = model_id
    checkpoint.provider = provider
    checkpoint.error_detail = detail
    checkpoint.completed_at = now
    checkpoint.updated_at = now
    db.commit()
    db.refresh(checkpoint)
    return checkpoint


def _load_checkpoint(db: Session, *, history_id: str) -> ChatContextCheckpoint | None:
    return db.execute(
        select(ChatContextCheckpoint).where(ChatContextCheckpoint.chat_history_id == history_id)
    ).scalar_one_or_none()
