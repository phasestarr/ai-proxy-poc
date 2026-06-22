from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import ChatHistoryFile, StoredFile, StoredFileProviderState
from app.db.postgres.models.chat_history import ChatMessage
from app.services.chat.attachments.provider_state import build_provider_token_states, ensure_provider_token_states
from app.services.chat.attachments.remote_files import best_effort_delete_provider_files, delete_provider_files_for_stored_file
from app.services.chat.completions.request_audit import persist_operator_event

STORED_FILE_ACTIVE = "active"
STORED_FILE_PENDING_DELETE = "pending_delete"
STORED_FILE_DELETE_FAILED = "delete_failed"
DELETE_RETRY_BASE_SECONDS = 60
DELETE_RETRY_MAX_SECONDS = 86_400


async def get_or_create_stored_file(
    db: Session,
    *,
    user_id: str,
    sha256: str,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
    existing_stored_file: StoredFile | None,
) -> StoredFile:
    stored_file = existing_stored_file
    if stored_file is None:
        stored_file_id = str(uuid4())
        provider_states = await build_provider_token_states(
            stored_file_id=stored_file_id,
            display_name=display_name,
            mime_type=mime_type,
            file_bytes=file_bytes,
        )
        now = utc_now()
        candidate = StoredFile(
            id=stored_file_id,
            user_id=user_id,
            sha256=sha256,
            mime_type=mime_type,
            byte_size=len(file_bytes),
            content=file_bytes,
            created_at=now,
            updated_at=now,
        )
        for provider_state in provider_states:
            candidate.provider_states.append(provider_state)
        savepoint = db.begin_nested()
        try:
            db.add(candidate)
            db.flush()
            savepoint.commit()
            stored_file = candidate
        except IntegrityError:
            savepoint.rollback()
            await best_effort_delete_provider_files(stored_file=candidate)
            stored_file = load_stored_file_by_hash(
                db,
                user_id=user_id,
                sha256=sha256,
            )
            if stored_file is None:
                raise

    await ensure_provider_token_states(
        stored_file=stored_file,
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
    )
    mark_stored_file_active(stored_file)
    return stored_file


def load_stored_file_by_hash(
    db: Session,
    *,
    user_id: str,
    sha256: str,
) -> StoredFile | None:
    return db.execute(
        select(StoredFile)
        .options(joinedload(StoredFile.provider_states))
        .where(
            StoredFile.user_id == user_id,
            StoredFile.sha256 == sha256,
        )
    ).unique().scalar_one_or_none()


def get_provider_state(
    *,
    stored_file: StoredFile,
    provider: str,
) -> StoredFileProviderState | None:
    for provider_state in stored_file.provider_states:
        if provider_state.provider == provider:
            return provider_state
    return None


async def cleanup_orphan_stored_file(
    db: Session,
    *,
    stored_file_id: str,
) -> bool:
    stored_file = db.execute(
        select(StoredFile)
        .where(StoredFile.id == stored_file_id)
        .with_for_update()
    ).scalar_one_or_none()
    if stored_file is None:
        return False

    if count_stored_file_references(db, stored_file_id=stored_file_id) > 0:
        mark_stored_file_active(stored_file)
        return False

    _ = list(stored_file.provider_states)
    if stored_file.lifecycle_state == STORED_FILE_ACTIVE:
        stored_file.lifecycle_state = STORED_FILE_PENDING_DELETE
        stored_file.delete_error = None
        stored_file.delete_next_attempt_at = None
        stored_file.updated_at = utc_now()

    previous_state = stored_file.lifecycle_state
    delete_succeeded, delete_errors = await delete_provider_files_for_stored_file(stored_file=stored_file)
    if not delete_succeeded:
        mark_stored_file_delete_failed(
            stored_file,
            detail="; ".join(delete_errors) or "provider remote delete failed",
            now=utc_now(),
        )
        if previous_state != STORED_FILE_DELETE_FAILED:
            persist_operator_event(
                db,
                event_type="attachment_blob_delete_failed",
                severity="error",
                user_id=stored_file.user_id,
                stored_file_id=stored_file.id,
                operation="attachment_blob_delete",
                result_code="attachment_blob_delete_failed",
                message="Attachment blob delete is waiting for remote cleanup retry.",
                detail=stored_file.delete_error,
                metadata={
                    "delete_attempt_count": stored_file.delete_attempt_count,
                    "delete_next_attempt_at": (
                        stored_file.delete_next_attempt_at.isoformat()
                        if stored_file.delete_next_attempt_at
                        else None
                    ),
                },
                commit=False,
            )
        return False
    db.delete(stored_file)
    db.flush()
    return True


async def cleanup_due_orphan_stored_files(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> int:
    current_time = now or utc_now()
    stored_file_ids = db.execute(
        select(StoredFile.id)
        .where(
            StoredFile.lifecycle_state.in_((STORED_FILE_PENDING_DELETE, STORED_FILE_DELETE_FAILED)),
            or_(
                StoredFile.delete_next_attempt_at.is_(None),
                StoredFile.delete_next_attempt_at <= current_time,
            ),
        )
        .order_by(StoredFile.delete_next_attempt_at.asc().nullsfirst(), StoredFile.updated_at.asc(), StoredFile.id.asc())
        .limit(max(1, limit))
    ).scalars().all()

    cleaned_count = 0
    for stored_file_id in stored_file_ids:
        if await cleanup_orphan_stored_file(db, stored_file_id=stored_file_id):
            cleaned_count += 1
    db.commit()
    return cleaned_count


def mark_stored_file_active(stored_file: StoredFile) -> None:
    stored_file.lifecycle_state = STORED_FILE_ACTIVE
    stored_file.delete_error = None
    stored_file.delete_next_attempt_at = None
    stored_file.updated_at = utc_now()


def mark_stored_file_delete_failed(
    stored_file: StoredFile,
    *,
    detail: str,
    now: datetime,
) -> None:
    stored_file.lifecycle_state = STORED_FILE_DELETE_FAILED
    stored_file.delete_error = detail[:4000]
    stored_file.delete_attempt_count = int(stored_file.delete_attempt_count or 0) + 1
    stored_file.delete_last_attempt_at = now
    stored_file.delete_next_attempt_at = now + timedelta(
        seconds=_delete_retry_delay_seconds(stored_file.delete_attempt_count),
    )
    stored_file.updated_at = now


def _delete_retry_delay_seconds(attempt_count: int) -> int:
    exponent = max(0, min(10, attempt_count - 1))
    return min(DELETE_RETRY_MAX_SECONDS, DELETE_RETRY_BASE_SECONDS * (2 ** exponent))


def count_stored_file_references(
    db: Session,
    *,
    stored_file_id: str,
    excluded_history_file_ids: set[str] | None = None,
) -> int:
    query = select(func.count(ChatHistoryFile.id)).where(ChatHistoryFile.stored_file_id == stored_file_id)
    if excluded_history_file_ids:
        query = query.where(ChatHistoryFile.id.notin_(excluded_history_file_ids))
    return int(db.execute(query).scalar_one() or 0)


def history_has_stored_file_reference(
    db: Session,
    *,
    history_id: str,
    stored_file_id: str,
) -> bool:
    row = db.execute(
        select(ChatHistoryFile.id)
        .where(
            ChatHistoryFile.chat_history_id == history_id,
            ChatHistoryFile.stored_file_id == stored_file_id,
        )
        .limit(1)
    ).first()
    return row is not None


def count_history_files(
    db: Session,
    *,
    history_id: str,
) -> int:
    return int(
        db.execute(
            select(func.count(ChatHistoryFile.id)).where(ChatHistoryFile.chat_history_id == history_id)
        ).scalar_one()
        or 0
    )


def count_history_messages(
    db: Session,
    *,
    history_id: str,
) -> int:
    return int(
        db.execute(
            select(func.count(ChatMessage.id)).where(ChatMessage.chat_history_id == history_id)
        ).scalar_one()
        or 0
    )


def count_user_attachment_files(
    db: Session,
    *,
    user_id: str,
) -> int:
    return int(
        db.execute(
            select(func.count(ChatHistoryFile.id)).where(ChatHistoryFile.user_id == user_id)
        ).scalar_one()
        or 0
    )
