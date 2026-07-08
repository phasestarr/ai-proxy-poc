from __future__ import annotations

from app.config.settings import settings
from app.schemas.chat import (
    ChatAttachmentLimitsView,
    ChatHistoryFileTokenSummary,
    ChatHistoryFileView,
    ChatHistoryMessageView,
    ChatHistorySummary,
    ChatHistoryUsageSummary,
)
from app.services.chat.histories.usage_summary import extract_token_summary


def build_chat_history_summary(history, message_count: int, attachment_count: int) -> ChatHistorySummary:
    operation = _active_operation(history)
    return ChatHistorySummary(
        id=history.id,
        title=history.title,
        pin_order=history.pin_order,
        lifecycle_state=getattr(history, "lifecycle_state", "active"),
        operation_state=_operation_state(operation),
        operation_type=getattr(operation, "operation_type", None),
        created_at=history.created_at,
        updated_at=history.updated_at,
        last_message_at=history.last_message_at,
        message_count=message_count,
        attachment_count=attachment_count,
    )


def build_attachment_limits_view() -> ChatAttachmentLimitsView:
    return ChatAttachmentLimitsView(
        max_files_per_history=settings.chat_attachment_max_files_per_history,
        max_files_per_user=settings.chat_attachment_max_files_per_user,
    )


def build_chat_history_message_view(message) -> ChatHistoryMessageView:
    usage = None
    if isinstance(message.usage, dict):
        token_summary = extract_token_summary(message.usage)
        usage = ChatHistoryUsageSummary(
            input_tokens=token_summary.get("input_tokens"),
            output_tokens=token_summary.get("output_tokens"),
            total_tokens=token_summary.get("total_tokens"),
        )

    return ChatHistoryMessageView(
        id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        sequence=message.sequence,
        excluded_from_context=message.excluded_from_context,
        model_id=message.model_id,
        provider=message.provider,
        tool_ids=list(message.tool_ids or []),
        finish_reason=message.finish_reason,
        result_code=message.result_code,
        result_message=message.result_message,
        error_detail=message.error_detail,
        usage=usage,
        completed_at=message.completed_at,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def build_chat_history_file_view(history_file) -> ChatHistoryFileView:
    token_counts = {
        "openai": None,
        "anthropic": None,
        "vertex_ai": None,
    }
    stored_file = getattr(history_file, "stored_file", None)
    provider_states = getattr(stored_file, "provider_states", []) if stored_file is not None else []
    for provider_state in provider_states:
        provider = str(getattr(provider_state, "provider", "") or "").strip()
        if provider in token_counts:
            token_counts[provider] = getattr(provider_state, "token_count", None)

    return ChatHistoryFileView(
        id=history_file.id,
        display_name=history_file.display_name,
        mime_type=history_file.mime_type,
        byte_size=history_file.byte_size,
        is_active=bool(getattr(history_file, "is_active", True)),
        token_counts=ChatHistoryFileTokenSummary(**token_counts),
        created_at=history_file.created_at,
        updated_at=history_file.updated_at,
    )


def _active_operation(owner):
    active_operation_id = getattr(owner, "active_operation_id", None)
    if not active_operation_id:
        return None
    for operation in getattr(owner, "operations", []) or []:
        if operation.id == active_operation_id:
            return operation
    return None


def _operation_state(operation) -> str:
    if operation is None:
        return "ready"
    state = getattr(operation, "state", "validating")
    if state in {"validating", "provider_streaming", "finalizing"}:
        return state
    return "ready"
