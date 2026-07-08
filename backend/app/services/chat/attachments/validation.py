from __future__ import annotations

from os.path import basename

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.postgres.models.chat_attachment import ChatDraftFile, ChatHistoryFile
from app.services.chat.attachments.storage import count_draft_files, count_history_files, count_user_attachment_files
from app.services.chat.histories.titles import normalize_history_title

SUPPORTED_ATTACHMENT_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg"}
SUPPORTED_ATTACHMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
PDF_MAGIC_PREFIX = b"%PDF-"
PNG_MAGIC_PREFIX = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC_PREFIX = b"\xff\xd8"


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
    history_id: str | None,
    next_byte_size: int,
) -> None:
    current_user_file_count = count_user_attachment_files(db, user_id=user_id)
    if current_user_file_count >= settings.chat_attachment_max_files_per_user:
        raise ValueError("user attachment limit reached")

    current_file_count = count_history_files(db, history_id=history_id) if history_id is not None else 0
    if current_file_count >= settings.chat_attachment_max_files_per_history:
        raise ValueError("chat history attachment limit reached")

    current_total_bytes = 0
    if history_id is not None:
        current_total_bytes = db.execute(
            select(func.coalesce(func.sum(ChatHistoryFile.byte_size), 0))
            .where(ChatHistoryFile.chat_history_id == history_id)
        ).scalar_one()
    if int(current_total_bytes or 0) + next_byte_size > settings.chat_attachment_max_total_bytes_per_history:
        raise ValueError("chat history attachment bytes exceed the total size limit")


def enforce_draft_attachment_limits(
    db: Session,
    *,
    user_id: str,
    draft_id: str,
    next_byte_size: int,
) -> None:
    current_user_file_count = count_user_attachment_files(db, user_id=user_id)
    if current_user_file_count >= settings.chat_attachment_max_files_per_user:
        raise ValueError("user attachment limit reached")

    current_file_count = count_draft_files(db, draft_id=draft_id)
    if current_file_count >= settings.chat_attachment_max_files_per_history:
        raise ValueError("chat draft attachment limit reached")

    current_total_bytes = db.execute(
        select(func.coalesce(func.sum(ChatDraftFile.byte_size), 0))
        .where(ChatDraftFile.draft_id == draft_id)
    ).scalar_one()
    if int(current_total_bytes or 0) + next_byte_size > settings.chat_attachment_max_total_bytes_per_history:
        raise ValueError("chat draft attachment bytes exceed the total size limit")


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


def default_attachment_filename(mime_type: str) -> str:
    if mime_type == "image/png":
        return "attachment.png"
    if mime_type == "image/jpeg":
        return "attachment.jpg"
    return "attachment.pdf"
