from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config.attachments import UPLOAD_READ_CHUNK_BYTES
from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import ChatDraftFile, ChatHistoryFile, StoredFile
from app.db.postgres.models.chat_history import ChatDraft, ChatHistory
from app.services.chat.attachments.errors import ChatHistoryDuplicateFileError, ChatHistoryFileNotFoundError
from app.services.chat.attachments.remote_files import best_effort_delete_remote_provider_file
from app.services.chat.attachments.storage import (
    cleanup_orphan_stored_file,
    count_history_files,
    count_history_messages,
    draft_has_stored_file_reference,
    get_or_create_stored_file,
    history_has_stored_file_reference,
    load_stored_file_by_hash,
)
from app.services.chat.attachments.validation import (
    build_attachment_display_name,
    enforce_draft_attachment_limits,
    enforce_history_attachment_limits,
    normalize_attachment_mime_type,
    validate_attachment_upload,
)
from app.services.chat.errors import ChatHistoryNotFoundError
from app.services.chat.histories.service import load_user_history
from app.services.chat.operations import OperationHandle, assert_operation_current, draft_ttl_seconds

def get_history_file(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    file_id: str,
) -> ChatHistoryFile | None:
    return db.execute(
        select(ChatHistoryFile)
        .options(
            joinedload(ChatHistoryFile.stored_file).joinedload(StoredFile.provider_states),
        )
        .where(
            ChatHistoryFile.id == file_id,
            ChatHistoryFile.chat_history_id == history_id,
            ChatHistoryFile.user_id == user_id,
        )
    ).unique().scalar_one_or_none()


async def attach_file_to_history(
    db: Session,
    *,
    user_id: str,
    history_id: str | None,
    staging_draft_id: str | None,
    upload: UploadFile,
    operation: OperationHandle,
) -> tuple[ChatHistory | None, ChatDraft | None, list[ChatHistoryFile | ChatDraftFile]]:
    mime_type = normalize_attachment_mime_type(upload.content_type)
    display_name = build_attachment_display_name(upload.filename, mime_type=mime_type)
    file_bytes = await _read_upload_bytes(upload)
    validate_attachment_upload(
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
    )

    history = None
    draft = None
    if history_id:
        history = load_user_history(db, user_id=user_id, history_id=history_id)
        if history is None:
            raise ChatHistoryNotFoundError("chat history not found")
    elif staging_draft_id:
        draft = db.get(ChatDraft, staging_draft_id)
        if draft is None or draft.user_id != user_id or draft.lifecycle_state != "active":
            raise ChatHistoryNotFoundError("chat draft not found")
    else:
        raise ValueError("chat history or draft is required before attaching a file")

    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    existing_stored_file = load_stored_file_by_hash(
        db,
        user_id=user_id,
        sha256=file_sha256,
    )
    if history is not None:
        if existing_stored_file is not None and history_has_stored_file_reference(
            db,
            history_id=history.id,
            stored_file_id=existing_stored_file.id,
        ):
            raise ChatHistoryDuplicateFileError("file is already attached to this chat history")
    if draft is not None:
        if existing_stored_file is not None and draft_has_stored_file_reference(
            db,
            draft_id=draft.id,
            stored_file_id=existing_stored_file.id,
        ):
            raise ChatHistoryDuplicateFileError("file is already attached to this chat draft")
    if history is not None:
        enforce_history_attachment_limits(
            db,
            user_id=user_id,
            history_id=history.id,
            next_byte_size=len(file_bytes),
        )
    else:
        enforce_draft_attachment_limits(
            db,
            user_id=user_id,
            draft_id=draft.id,
            next_byte_size=len(file_bytes),
        )

    stored_file_mutation = await get_or_create_stored_file(
        db,
        user_id=user_id,
        sha256=file_sha256,
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
        existing_stored_file=existing_stored_file,
    )
    stored_file = stored_file_mutation.stored_file
    try:
        if history is not None:
            history.updated_at = utc_now()

        assert_operation_current(db, operation)
        now = utc_now()
        if history is not None:
            history_file = ChatHistoryFile(
                id=str(uuid4()),
                user_id=user_id,
                chat_history_id=history.id,
                stored_file_id=stored_file.id,
                display_name=display_name,
                mime_type=mime_type,
                byte_size=len(file_bytes),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            db.add(history_file)
        else:
            history_file = ChatDraftFile(
                id=str(uuid4()),
                user_id=user_id,
                draft_id=draft.id,
                stored_file_id=stored_file.id,
                display_name=display_name,
                mime_type=mime_type,
                byte_size=len(file_bytes),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            draft.expires_at = now + timedelta(seconds=draft_ttl_seconds())
            draft.updated_at = now
            db.add(history_file)
        db.commit()
    except Exception:
        db.rollback()
        await _cleanup_rollback_provider_files(
            stored_file_mutation.remote_provider_files_to_cleanup_on_rollback
        )
        raise
    if history is not None:
        db.refresh(history)
        return history, None, list_history_files(db, user_id=user_id, history_id=history.id)
    db.refresh(draft)
    return None, draft, list_draft_files(db, user_id=user_id, draft_id=draft.id)


async def delete_file_from_history(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    file_id: str,
    operation: OperationHandle,
) -> tuple[ChatHistory | None, list[ChatHistoryFile], str | None]:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")
    assert_operation_current(db, operation)

    history_file = db.execute(
        select(ChatHistoryFile)
        .where(
            ChatHistoryFile.id == file_id,
            ChatHistoryFile.chat_history_id == history_id,
            ChatHistoryFile.user_id == user_id,
        )
        .with_for_update()
    ).unique().scalar_one_or_none()
    if history_file is None:
        raise ChatHistoryFileNotFoundError("chat file not found")

    stored_file_id = history_file.stored_file_id
    db.delete(history_file)
    db.flush()
    await cleanup_orphan_stored_file(
        db,
        stored_file_id=stored_file_id,
    )

    remaining_message_count = count_history_messages(db, history_id=history.id)
    remaining_file_count = count_history_files(db, history_id=history.id)
    deleted_history_id = None
    if remaining_message_count == 0 and remaining_file_count == 0:
        deleted_history_id = history.id
        assert_operation_current(db, operation)
        db.delete(history)
        db.commit()
        return None, [], deleted_history_id

    history.updated_at = utc_now()
    assert_operation_current(db, operation)
    db.commit()
    db.refresh(history)
    return history, list_history_files(db, user_id=user_id, history_id=history.id), deleted_history_id


def update_history_file_activation(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    file_id: str,
    is_active: bool,
    operation: OperationHandle,
) -> tuple[ChatHistory, list[ChatHistoryFile]]:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")
    assert_operation_current(db, operation)

    history_file = get_history_file(
        db,
        user_id=user_id,
        history_id=history_id,
        file_id=file_id,
    )
    if history_file is None:
        raise ChatHistoryFileNotFoundError("chat file not found")

    history_file.is_active = is_active
    history.updated_at = utc_now()
    assert_operation_current(db, operation)
    db.commit()
    db.refresh(history)
    return history, list_history_files(db, user_id=user_id, history_id=history.id)


async def delete_history_with_files(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    operation: OperationHandle,
) -> None:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")
    assert_operation_current(db, operation)

    history_files = db.execute(
        select(ChatHistoryFile)
        .where(
            ChatHistoryFile.chat_history_id == history.id,
            ChatHistoryFile.user_id == user_id,
        )
        .with_for_update()
    ).scalars().all()
    stored_file_ids = {history_file.stored_file_id for history_file in history_files}
    for history_file in history_files:
        db.delete(history_file)

    db.flush()
    for stored_file_id in stored_file_ids:
        await cleanup_orphan_stored_file(
            db,
            stored_file_id=stored_file_id,
        )
    assert_operation_current(db, operation)
    db.delete(history)
    db.commit()


async def discard_draft_with_files(
    db: Session,
    *,
    user_id: str,
    draft_id: str,
) -> None:
    draft = db.get(ChatDraft, draft_id)
    if draft is None or draft.user_id != user_id:
        return

    draft_files = db.execute(
        select(ChatDraftFile)
        .where(
            ChatDraftFile.draft_id == draft.id,
            ChatDraftFile.user_id == user_id,
        )
        .with_for_update()
    ).scalars().all()
    stored_file_ids = {draft_file.stored_file_id for draft_file in draft_files}
    for draft_file in draft_files:
        db.delete(draft_file)

    db.flush()
    for stored_file_id in stored_file_ids:
        await cleanup_orphan_stored_file(
            db,
            stored_file_id=stored_file_id,
        )
    db.delete(draft)
    db.commit()


def list_history_files(
    db: Session,
    *,
    user_id: str,
    history_id: str,
) -> list[ChatHistoryFile]:
    rows = db.execute(
        select(ChatHistoryFile)
        .options(
            joinedload(ChatHistoryFile.stored_file).joinedload(StoredFile.provider_states),
        )
        .where(
            ChatHistoryFile.chat_history_id == history_id,
            ChatHistoryFile.user_id == user_id,
        )
        .order_by(ChatHistoryFile.created_at.asc(), ChatHistoryFile.id.asc())
    ).unique().scalars().all()
    return list(rows)


def list_draft_files(
    db: Session,
    *,
    user_id: str,
    draft_id: str,
) -> list[ChatDraftFile]:
    rows = db.execute(
        select(ChatDraftFile)
        .options(
            joinedload(ChatDraftFile.stored_file).joinedload(StoredFile.provider_states),
        )
        .where(
            ChatDraftFile.draft_id == draft_id,
            ChatDraftFile.user_id == user_id,
        )
        .order_by(ChatDraftFile.created_at.asc(), ChatDraftFile.id.asc())
    ).unique().scalars().all()
    return list(rows)


async def _cleanup_rollback_provider_files(remote_provider_files: list[tuple[str, str]]) -> None:
    for provider, provider_file_id in remote_provider_files:
        await best_effort_delete_remote_provider_file(
            provider=provider,
            provider_file_id=provider_file_id,
        )


async def _read_upload_bytes(upload: UploadFile) -> bytes:
    max_file_bytes = max(0, settings.chat_attachment_max_file_bytes)
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        read_size = min(UPLOAD_READ_CHUNK_BYTES, max_file_bytes + 1 - total_bytes)
        chunk = await upload.read(read_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_file_bytes:
            raise ValueError("file exceeds the per-file size limit")
        chunks.append(chunk)
    return b"".join(chunks)
