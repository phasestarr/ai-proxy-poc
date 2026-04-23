from __future__ import annotations

from app.schemas.chat import ChatHistoryMessageView, ChatHistorySummary, ChatHistoryUsageSummary


def build_chat_history_summary(history, message_count: int) -> ChatHistorySummary:
    return ChatHistorySummary(
        id=history.id,
        title=history.title,
        created_at=history.created_at,
        updated_at=history.updated_at,
        last_message_at=history.last_message_at,
        message_count=message_count,
    )


def build_chat_history_message_view(message) -> ChatHistoryMessageView:
    usage = None
    if isinstance(message.usage, dict):
        usage = ChatHistoryUsageSummary(
            input_tokens=message.usage.get("input_tokens"),
            output_tokens=message.usage.get("output_tokens"),
            total_tokens=message.usage.get("total_tokens"),
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
        error_origin=message.error_origin,
        error_http_status=message.error_http_status,
        provider_error_code=message.provider_error_code,
        retry_after_seconds=message.retry_after_seconds,
        error_detail=message.error_detail,
        usage=usage,
        completed_at=message.completed_at,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )
