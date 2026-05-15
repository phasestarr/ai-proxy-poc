from __future__ import annotations

import asyncio
import hashlib
import logging
from os.path import basename
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import ChatHistoryFile, StoredFile, StoredFileProviderState
from app.db.postgres.models.chat_history import ChatHistory, ChatMessage
from app.db.postgres.session import SessionLocal
from app.db.redis.chat_drafts import delete_chat_draft, load_chat_draft
from app.providers.anthropic.attachments import (
    count_anthropic_file_tokens,
    delete_anthropic_file,
    inject_anthropic_history_files,
    upload_anthropic_file,
)
from app.providers.openai.attachments import (
    count_openai_file_tokens,
    delete_openai_file,
    inject_openai_history_files,
    upload_openai_file,
)
from app.providers.types import PreparedProviderChatRequest, ProviderRoute
from app.services.chat.errors import ChatHistoryNotFoundError, ChatProxyError
from app.services.chat.history_queries import load_user_history
from app.services.chat.interaction_state import (
    BUSY_REASON_ATTACH_FILE,
    INTERACTION_STATE_READY,
    INTERACTION_STATE_VALIDATING,
    apply_history_interaction_state,
)
from app.services.chat.titles import normalize_history_title

logger = logging.getLogger("uvicorn.error")

SUPPORTED_ATTACHMENT_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg"}
SUPPORTED_ATTACHMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
PDF_MAGIC_PREFIX = b"%PDF-"
PNG_MAGIC_PREFIX = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC_PREFIX = b"\xff\xd8"


class ChatHistoryFileNotFoundError(RuntimeError):
    """Raised when a chat attachment does not belong to the current user/history."""


class ChatHistoryDuplicateFileError(RuntimeError):
    """Raised when the same stored file is already attached to a chat history."""


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
    file_bytes = await upload.read()
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
            history_id=history.id,
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


async def prepare_history_attachments_for_provider(
    *,
    user_id: str,
    history_id: str,
    route: ProviderRoute,
    prepared_request: PreparedProviderChatRequest,
) -> tuple[PreparedProviderChatRequest, list[dict[str, object]]]:
    if route.model.provider == "vertex_ai":
        with SessionLocal() as db:
            if count_history_files(db, history_id=history_id) > 0:
                raise ChatProxyError(
                    code="attachments_unsupported",
                    origin="client",
                    detail="selected provider does not support file attachments",
                    http_status=400,
                    provider=route.model.provider,
                )
        return prepared_request, []

    with SessionLocal() as db:
        history_files = list_history_files(db, user_id=user_id, history_id=history_id)
        active_history_files = [history_file for history_file in history_files if history_file.is_active]
        if not active_history_files:
            return prepared_request, []

        provider_token_total = 0
        upload_targets: dict[str, tuple[str, StoredFile, StoredFileProviderState]] = {}
        attachments: list[dict[str, object]] = []

        for history_file in active_history_files:
            stored_file = history_file.stored_file
            provider_state = get_provider_state(stored_file=stored_file, provider=route.model.provider)
            if provider_state is None or provider_state.token_count_status != "ready" or provider_state.token_count is None:
                raise ChatProxyError(
                    code="attachments_token_count_failed",
                    origin="proxy",
                    detail="attachment token metadata is unavailable",
                    http_status=503,
                    provider=route.model.provider,
                )

            provider_token_total += int(provider_state.token_count)
            attachments.append(
                {
                    "history_file_id": history_file.id,
                    "stored_file_id": stored_file.id,
                    "display_name": history_file.display_name,
                    "mime_type": history_file.mime_type,
                    "byte_size": history_file.byte_size,
                    "provider": route.model.provider,
                    "provider_file_id": provider_state.provider_file_id,
                    "token_count": int(provider_state.token_count),
                }
            )
            if provider_state.provider_file_id and provider_state.remote_file_status == "ready":
                continue
            upload_targets[stored_file.id] = (history_file.display_name, stored_file, provider_state)

        if provider_token_total > settings.chat_attachment_max_total_tokens_per_provider:
            raise ChatProxyError(
                code="attachments_too_large",
                origin="client",
                detail="attachment token total exceeds the provider attachment limit",
                http_status=400,
                provider=route.model.provider,
            )

        uploaded_provider_ids = await upload_provider_files(
            provider=route.model.provider,
            upload_targets=upload_targets,
        )
        now = utc_now()
        for stored_file_id, provider_file_id in uploaded_provider_ids.items():
            _, _, provider_state = upload_targets[stored_file_id]
            provider_state.provider_file_id = provider_file_id
            provider_state.remote_file_status = "ready"
            provider_state.remote_file_error = None
            provider_state.uploaded_at = now
            provider_state.last_used_at = now

        for history_file in active_history_files:
            provider_state = get_provider_state(stored_file=history_file.stored_file, provider=route.model.provider)
            if provider_state is not None:
                provider_state.last_used_at = now

        db.commit()

        attachment_by_history_file_id = {
            attachment["history_file_id"]: attachment
            for attachment in attachments
        }
        for history_file in active_history_files:
            provider_state = get_provider_state(stored_file=history_file.stored_file, provider=route.model.provider)
            if provider_state is None or not provider_state.provider_file_id:
                raise ChatProxyError(
                    code="attachments_upload_failed",
                    origin="proxy",
                    detail="provider file upload did not return a reusable file id",
                    http_status=502,
                    provider=route.model.provider,
                )
            attachment = attachment_by_history_file_id[history_file.id]
            attachment["provider_file_id"] = provider_state.provider_file_id

        snapshots = [
            {
                "chat_history_file_id": attachment["history_file_id"],
                "stored_file_id": attachment["stored_file_id"],
                "display_name": attachment["display_name"],
                "mime_type": attachment["mime_type"],
                "byte_size": attachment["byte_size"],
                "provider": attachment["provider"],
                "provider_file_id": attachment["provider_file_id"],
                "token_count": attachment["token_count"],
            }
            for attachment in attachments
        ]

    next_payload = build_provider_attachment_payload(
        provider=route.model.provider,
        payload=prepared_request.payload,
        history_id=history_id,
        attachments=attachments,
    )
    return PreparedProviderChatRequest(
        provider=prepared_request.provider,
        public_model_id=prepared_request.public_model_id,
        payload=next_payload,
        estimated_input_tokens=prepared_request.estimated_input_tokens,
        input_token_count_payload=prepared_request.input_token_count_payload,
        resolved_input_tokens=prepared_request.resolved_input_tokens,
    ), snapshots


def validate_attachment_upload(
    *,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> None:
    if not display_name:
        raise ValueError("file name is required")
    if mime_type not in SUPPORTED_ATTACHMENT_MIME_TYPES:
        raise ValueError("this file type is not supported")
    if not any(display_name.lower().endswith(extension) for extension in SUPPORTED_ATTACHMENT_EXTENSIONS):
        raise ValueError("file extension must be .pdf, .png, .jpg, or .jpeg")
    if not file_bytes:
        raise ValueError("file must not be empty")
    if len(file_bytes) > settings.chat_attachment_max_file_bytes:
        raise ValueError("file exceeds the per-file size limit")
    # Cheap signature check to catch obvious MIME/extension spoofing before provider upload.
    if mime_type == "application/pdf" and not file_bytes.startswith(PDF_MAGIC_PREFIX):
        raise ValueError("file content does not match application/pdf")
    if mime_type == "image/png" and not file_bytes.startswith(PNG_MAGIC_PREFIX):
        raise ValueError("file content does not match image/png")
    if mime_type == "image/jpeg" and not file_bytes.startswith(JPEG_MAGIC_PREFIX):
        raise ValueError("file content does not match image/jpeg")


def enforce_history_attachment_limits(
    db: Session,
    *,
    user_id: str,
    history_id: str,
    next_byte_size: int,
) -> None:
    current_user_file_count = count_user_attachment_files(db, user_id=user_id)
    if current_user_file_count >= settings.chat_attachment_max_files_per_user:
        raise ValueError("user attachment limit reached")

    current_file_count = count_history_files(db, history_id=history_id)
    if current_file_count >= settings.chat_attachment_max_files_per_history:
        raise ValueError("chat history attachment limit reached")

    current_total_bytes = db.execute(
        select(func.coalesce(func.sum(ChatHistoryFile.byte_size), 0))
        .where(ChatHistoryFile.chat_history_id == history_id)
    ).scalar_one()
    if int(current_total_bytes or 0) + next_byte_size > settings.chat_attachment_max_total_bytes_per_history:
        raise ValueError("chat history attachment bytes exceed the total size limit")


def build_attachment_display_name(filename: str | None, *, mime_type: str) -> str:
    candidate = basename((filename or "").strip())
    candidate = " ".join(candidate.split())
    if not candidate:
        return default_attachment_filename(mime_type)
    return candidate[:255]


def normalize_attachment_mime_type(content_type: str | None) -> str:
    normalized = str(content_type or "").strip().lower() or "application/octet-stream"
    if normalized == "image/jpg":
        return "image/jpeg"
    return normalized


def build_history_title_from_filename(display_name: str) -> str:
    title = normalize_history_title(display_name)
    if not title:
        return "New chat"
    return title[:80]


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
        provider_states = await build_provider_token_states(
            display_name=display_name,
            mime_type=mime_type,
            file_bytes=file_bytes,
        )
        now = utc_now()
        candidate = StoredFile(
            id=str(uuid4()),
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
            stored_file = load_stored_file_by_hash(
                db,
                user_id=user_id,
                sha256=sha256,
            )
            if stored_file is None:
                raise

    await ensure_provider_token_states(
        db,
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


async def ensure_provider_token_states(
    db: Session,
    *,
    stored_file: StoredFile,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> None:
    existing_states = {state.provider: state for state in stored_file.provider_states}
    provider_counts = await resolve_provider_token_counts(
        existing_states=existing_states,
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
    )
    for provider, payload in provider_counts.items():
        state = existing_states.get(provider)
        if state is None:
            state = StoredFileProviderState(
                id=str(uuid4()),
                provider=provider,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            stored_file.provider_states.append(state)

        state.token_count = payload.get("token_count")
        state.token_count_status = str(payload["token_count_status"])
        state.token_count_error = payload.get("token_count_error")
        state.count_model_id = payload.get("count_model_id")
        if provider == "vertex_ai":
            state.remote_file_status = "unsupported"
        elif not state.remote_file_status:
            state.remote_file_status = "not_uploaded"


async def build_provider_token_states(
    *,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> list[StoredFileProviderState]:
    provider_counts = await resolve_provider_token_counts(
        existing_states={},
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
    )
    provider_states: list[StoredFileProviderState] = []
    for provider, payload in provider_counts.items():
        provider_states.append(
            StoredFileProviderState(
                id=str(uuid4()),
                provider=provider,
                token_count=payload.get("token_count"),
                token_count_status=str(payload["token_count_status"]),
                token_count_error=payload.get("token_count_error"),
                remote_file_status="unsupported" if provider == "vertex_ai" else "not_uploaded",
                count_model_id=payload.get("count_model_id"),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
    return provider_states


async def resolve_provider_token_counts(
    *,
    existing_states: dict[str, StoredFileProviderState],
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {
        "vertex_ai": {
            "token_count": None,
            "token_count_status": "unsupported",
            "token_count_error": None,
            "count_model_id": None,
        }
    }
    tasks: list[tuple[str, asyncio.Task]] = []

    openai_state = existing_states.get("openai")
    if openai_state is None or openai_state.token_count_status != "ready" or openai_state.token_count is None:
        tasks.append(
            (
                "openai",
                asyncio.ensure_future(
                    count_openai_file_tokens(
                        display_name=display_name,
                        mime_type=mime_type,
                        file_bytes=file_bytes,
                    )
                ),
            )
        )
    else:
        results["openai"] = {
            "token_count": openai_state.token_count,
            "token_count_status": openai_state.token_count_status,
            "token_count_error": openai_state.token_count_error,
            "count_model_id": openai_state.count_model_id,
        }

    anthropic_state = existing_states.get("anthropic")
    if anthropic_state is None or anthropic_state.token_count_status != "ready" or anthropic_state.token_count is None:
        tasks.append(
            (
                "anthropic",
                asyncio.ensure_future(
                    count_anthropic_file_tokens(
                        display_name=display_name,
                        mime_type=mime_type,
                        file_bytes=file_bytes,
                    )
                ),
            )
        )
    else:
        results["anthropic"] = {
            "token_count": anthropic_state.token_count,
            "token_count_status": anthropic_state.token_count_status,
            "token_count_error": anthropic_state.token_count_error,
            "count_model_id": anthropic_state.count_model_id,
        }

    if tasks:
        gathered = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        for (provider, _), outcome in zip(tasks, gathered, strict=False):
            if isinstance(outcome, Exception):
                raise RuntimeError(f"{provider} attachment token counting failed: {outcome}") from outcome
            token_count, count_model_id = outcome
            results[provider] = {
                "token_count": int(token_count),
                "token_count_status": "ready",
                "token_count_error": None,
                "count_model_id": count_model_id,
            }

    return results


async def upload_provider_files(
    *,
    provider: str,
    upload_targets: dict[str, tuple[str, StoredFile, StoredFileProviderState]],
) -> dict[str, str]:
    uploaded_ids: dict[str, str] = {}
    for stored_file_id, (display_name, stored_file, provider_state) in upload_targets.items():
        try:
            if provider == "openai":
                provider_file_id = await upload_openai_file(
                    display_name=display_name,
                    mime_type=stored_file.mime_type,
                    file_bytes=stored_file.content,
                )
            elif provider == "anthropic":
                provider_file_id = await upload_anthropic_file(
                    display_name=display_name,
                    mime_type=stored_file.mime_type,
                    file_bytes=stored_file.content,
                )
            else:
                raise RuntimeError(f"unsupported attachment provider: {provider}")
        except Exception as exc:
            provider_state.remote_file_status = "failed"
            provider_state.remote_file_error = str(exc)
            raise ChatProxyError(
                code="attachments_upload_failed",
                origin="proxy",
                detail=f"{provider} file upload failed",
                http_status=502,
                provider=provider,
            ) from exc
        uploaded_ids[stored_file_id] = provider_file_id
    return uploaded_ids


def build_provider_attachment_payload(
    *,
    provider: str,
    payload: object,
    history_id: str,
    attachments: list[dict[str, object]],
) -> object:
    if not isinstance(payload, dict):
        return payload
    if provider == "openai":
        return inject_openai_history_files(
            payload=payload,
            history_id=history_id,
            attachments=attachments,
        )
    if provider == "anthropic":
        return inject_anthropic_history_files(
            payload=payload,
            attachments=attachments,
        )
    return payload


def get_provider_state(
    *,
    stored_file: StoredFile,
    provider: str,
) -> StoredFileProviderState | None:
    for provider_state in stored_file.provider_states:
        if provider_state.provider == provider:
            return provider_state
    return None


async def best_effort_delete_provider_files(*, stored_file: StoredFile) -> None:
    for provider_state in stored_file.provider_states:
        if not provider_state.provider_file_id or provider_state.remote_file_status != "ready":
            continue
        try:
            if provider_state.provider == "openai":
                await delete_openai_file(provider_file_id=provider_state.provider_file_id)
            elif provider_state.provider == "anthropic":
                await delete_anthropic_file(provider_file_id=provider_state.provider_file_id)
        except Exception:
            logger.exception(
                "Attachment provider file cleanup failed.",
                extra={
                    "provider": provider_state.provider,
                    "provider_file_id": provider_state.provider_file_id,
                    "stored_file_id": stored_file.id,
                },
            )


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

    # Load provider refs after the row lock has been acquired so PostgreSQL
    # does not reject FOR UPDATE on an eager-loaded outer join.
    _ = list(stored_file.provider_states)
    await best_effort_delete_provider_files(stored_file=stored_file)
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


def default_attachment_filename(mime_type: str) -> str:
    if mime_type == "image/png":
        return "attachment.png"
    if mime_type == "image/jpeg":
        return "attachment.jpg"
    return "attachment.pdf"
