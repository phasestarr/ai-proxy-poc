from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import ChatHistoryFile, StoredFile, StoredFileProviderState
from app.db.postgres.models.chat_history import ChatMessage
from app.services.chat.attachments.provider_state import build_provider_token_states, ensure_provider_token_states
from app.services.chat.attachments.remote_files import best_effort_delete_provider_files, delete_provider_files_for_stored_file


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
        return False

    _ = list(stored_file.provider_states)
    if not await delete_provider_files_for_stored_file(stored_file=stored_file):
        return False
    db.delete(stored_file)
    db.flush()
    return True


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
