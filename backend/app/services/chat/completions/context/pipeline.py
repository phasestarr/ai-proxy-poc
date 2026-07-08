from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.postgres.models.chat_history import ChatContextCheckpoint, ChatHistory, ChatMessage
from app.schemas.chat import ChatMessage as RequestChatMessage
from app.services.chat.completions.context.checkpoints import load_chat_context_checkpoint

CHECKPOINT_SUMMARY_USER_PREFIX = (
    "Earlier conversation summary for continuity:\n"
    "- This summary replaces older chat turns already covered by the checkpoint.\n"
    "- Use it as background context only; the latest user message remains the active request.\n\n"
)


@dataclass(slots=True, frozen=True)
class BuiltChatContext:
    history: ChatHistory | None
    checkpoint: ChatContextCheckpoint | None
    persisted_suffix_messages: list[ChatMessage]
    provider_messages: list[RequestChatMessage]
    latest_user_message: RequestChatMessage

    @property
    def covered_through_sequence(self) -> int | None:
        if self.checkpoint is None:
            return None
        return self.checkpoint.covered_through_sequence


def build_chat_context(
    db: Session,
    *,
    history: ChatHistory | None,
    latest_user_content: str,
) -> BuiltChatContext:
    latest_user_message = RequestChatMessage(role="user", content=latest_user_content.strip())
    if history is None:
        return BuiltChatContext(
            history=None,
            checkpoint=None,
            persisted_suffix_messages=[],
            provider_messages=[latest_user_message],
            latest_user_message=latest_user_message,
        )

    checkpoint = load_chat_context_checkpoint(db, history_id=history.id)
    persisted_suffix_messages = _load_persisted_suffix_messages(
        db,
        history_id=history.id,
        covered_through_sequence=checkpoint.covered_through_sequence if checkpoint else None,
    )

    provider_messages: list[RequestChatMessage] = []
    checkpoint_message = _build_checkpoint_context_message(checkpoint)
    if checkpoint_message is not None:
        provider_messages.append(checkpoint_message)

    provider_messages.extend(_map_rows_to_request_messages(persisted_suffix_messages))
    provider_messages.append(latest_user_message)

    return BuiltChatContext(
        history=history,
        checkpoint=checkpoint,
        persisted_suffix_messages=persisted_suffix_messages,
        provider_messages=provider_messages,
        latest_user_message=latest_user_message,
    )


def build_compaction_source_text(
    db: Session,
    *,
    history_id: str,
) -> tuple[str, int | None]:
    checkpoint = load_chat_context_checkpoint(db, history_id=history_id)
    suffix_rows = _load_persisted_suffix_messages(
        db,
        history_id=history_id,
        covered_through_sequence=checkpoint.covered_through_sequence if checkpoint else None,
    )
    rendered_sections: list[str] = []
    if checkpoint and checkpoint.summary_text and checkpoint.summary_text.strip():
        rendered_sections.append(
            "Existing checkpoint summary:\n"
            f"{checkpoint.summary_text.strip()}"
        )

    transcript_lines: list[str] = []
    for row in suffix_rows:
        content = row.content.strip()
        if not content:
            continue
        speaker = "User" if row.role == "user" else "Assistant"
        transcript_lines.append(f"{speaker}: {content}")

    if transcript_lines:
        rendered_sections.append("Recent raw conversation turns:\n" + "\n".join(transcript_lines))

    return "\n\n".join(rendered_sections).strip(), _resolve_covered_through_sequence(
        checkpoint=checkpoint,
        rows=suffix_rows,
    )


def _load_persisted_suffix_messages(
    db: Session,
    *,
    history_id: str,
    covered_through_sequence: int | None,
) -> list[ChatMessage]:
    conditions = [
        ChatMessage.chat_history_id == history_id,
        ChatMessage.excluded_from_context.is_(False),
        ChatMessage.status == "done",
    ]
    if covered_through_sequence is not None:
        conditions.append(ChatMessage.sequence > covered_through_sequence)

    return db.execute(
        select(ChatMessage)
        .where(*conditions)
        .order_by(ChatMessage.sequence.asc())
    ).scalars().all()


def _map_rows_to_request_messages(rows: list[ChatMessage]) -> list[RequestChatMessage]:
    messages: list[RequestChatMessage] = []
    for row in rows:
        content = row.content.strip()
        if not content:
            continue
        messages.append(RequestChatMessage(role=row.role, content=content))
    return messages


def _build_checkpoint_context_message(
    checkpoint: ChatContextCheckpoint | None,
) -> RequestChatMessage | None:
    if checkpoint is None or not checkpoint.summary_text or not checkpoint.summary_text.strip():
        return None
    return RequestChatMessage(
        role="user",
        content=f"{CHECKPOINT_SUMMARY_USER_PREFIX}{checkpoint.summary_text.strip()}",
    )


def _resolve_covered_through_sequence(
    *,
    checkpoint: ChatContextCheckpoint | None,
    rows: list[ChatMessage],
) -> int | None:
    if rows:
        return max(row.sequence for row in rows)
    if checkpoint is not None:
        return checkpoint.covered_through_sequence
    return None
