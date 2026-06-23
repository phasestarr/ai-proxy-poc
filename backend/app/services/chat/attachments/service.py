from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import ChatHistoryFile, StoredFile
from app.db.postgres.models.chat_history import ChatHistory
from app.db.redis.chat_drafts import delete_chat_draft, load_chat_draft
from app.services.chat.attachments.errors import ChatHistoryDuplicateFileError, ChatHistoryFileNotFoundError
from app.services.chat.attachments.storage import (
    cleanup_orphan_stored_file,
    count_history_files,
    count_history_messages,
    get_or_create_stored_file,
    history_has_stored_file_reference,
    load_stored_file_by_hash,
)
from app.services.chat.attachments.validation import (
    build_attachment_display_name,
    build_history_title_from_filename,
    enforce_history_attachment_limits,
    normalize_attachment_mime_type,
    validate_attachment_upload,
)
from app.services.chat.errors import ChatHistoryNotFoundError
from app.services.chat.histories.service import load_user_history
from app.services.chat.histories.state import (
    BUSY_REASON_ATTACH_FILE,
    INTERACTION_STATE_READY,
    INTERACTION_STATE_VALIDATING,
    apply_history_interaction_state,
)

UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


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
    draft_chat_id: str | None,
    upload: UploadFile,
) -> tuple[ChatHistory, list[ChatHistoryFile]]:
    mime_type = normalize_attachment_mime_type(upload.content_type)
    display_name = build_attachment_display_name(upload.filename, mime_type=mime_type)
    file_bytes = await _read_upload_bytes(upload)
    validate_attachment_upload(
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
    )

    history = None
    should_delete_draft = False
    if history_id:
        history = load_user_history(db, user_id=user_id, history_id=history_id)
        if history is None:
            raise ChatHistoryNotFoundError("chat history not found")
    elif draft_chat_id:
        history = load_user_history(db, user_id=user_id, history_id=draft_chat_id)
        if history is None:
            draft = load_chat_draft(draft_chat_id=draft_chat_id)
            if draft is None or draft.user_id != user_id:
                raise ChatHistoryNotFoundError("chat history not found")
            should_delete_draft = True
    else:
        raise ValueError("exactly one of chat_history_id or draft_chat_id is required")

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
    enforce_history_attachment_limits(
        db,
        user_id=user_id,
        history_id=history.id if history is not None else None,
        next_byte_size=len(file_bytes),
    )

    stored_file = await get_or_create_stored_file(
        db,
        user_id=user_id,
        sha256=file_sha256,
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
        existing_stored_file=existing_stored_file,
    )
    if history is None:
        history = ChatHistory(
            id=draft_chat_id or str(uuid4()),
            user_id=user_id,
            title=build_history_title_from_filename(display_name),
            interaction_state=INTERACTION_STATE_VALIDATING,
            busy_reason=BUSY_REASON_ATTACH_FILE,
            created_at=utc_now(),
            updated_at=utc_now(),
            state_updated_at=utc_now(),
        )
        db.add(history)
        db.flush()
    else:
        history.updated_at = utc_now()

    history_file = ChatHistoryFile(
        id=str(uuid4()),
        user_id=user_id,
        chat_history_id=history.id,
        stored_file_id=stored_file.id,
        display_name=display_name,
        mime_type=mime_type,
        byte_size=len(file_bytes),
        is_active=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(history_file)
    apply_history_interaction_state(
        history,
        interaction_state=INTERACTION_STATE_READY,
        busy_reason=None,
    )
    db.commit()
    if should_delete_draft and draft_chat_id:
        delete_chat_draft(draft_chat_id=draft_chat_id)
    db.refresh(history)
    return history, list_history_files(db, user_id=user_id, history_id=history.id)


async def delete_file_from_history(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    file_id: str,
) -> tuple[ChatHistory | None, list[ChatHistoryFile], str | None]:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

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
        db.delete(history)
        db.commit()
        return None, [], deleted_history_id

    history.updated_at = utc_now()
    apply_history_interaction_state(
        history,
        interaction_state=INTERACTION_STATE_READY,
        busy_reason=None,
    )
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
) -> tuple[ChatHistory, list[ChatHistoryFile]]:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

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
    apply_history_interaction_state(
        history,
        interaction_state=INTERACTION_STATE_READY,
        busy_reason=None,
    )
    db.commit()
    db.refresh(history)
    return history, list_history_files(db, user_id=user_id, history_id=history.id)


async def delete_history_with_files(
    db: Session,
    *,
    user_id: str,
    history_id: str,
) -> None:
    history = load_user_history(db, user_id=user_id, history_id=history_id)
    if history is None:
        raise ChatHistoryNotFoundError("chat history not found")

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
    db.delete(history)
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
