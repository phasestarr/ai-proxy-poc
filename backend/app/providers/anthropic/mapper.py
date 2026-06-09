"""
Purpose:
- Convert internal application request and response structures
  to and from Anthropic Messages API formats.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.providers.anthropic.outcomes import get_anthropic_status_message
from app.providers.anthropic.usage import map_anthropic_usage
from app.providers.types import ProviderStreamChunk
from app.schemas.chat import ChatMessage


def map_chat_messages_to_anthropic_messages(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, object]]]:
    system_messages: list[str] = []
    anthropic_messages: list[dict[str, object]] = []

    for message in messages:
        if message.role == "system":
            system_messages.append(message.content)
            continue

        anthropic_messages.append(
            {
                "role": message.role,
                "content": message.content,
            }
        )

    if not anthropic_messages:
        raise ValueError("at least one non-system message is required")

    request_system_instruction = "\n\n".join(system_messages) if system_messages else None
    return request_system_instruction, anthropic_messages


def map_anthropic_stream_event(
    event,
    *,
    public_model_id: str,
    selected_tool_ids: Iterable[str] = (),
) -> ProviderStreamChunk | None:
    event_type = getattr(event, "type", None)

    if event_type == "content_block_delta":
        status_code = _map_anthropic_status_code(event)
        delta = getattr(event, "delta", None)
        if getattr(delta, "type", None) == "text_delta":
            return ProviderStreamChunk(
                text=getattr(delta, "text", None) or "",
                status_code="anthropic_text_output",
                status_message=get_anthropic_status_message("anthropic_text_output"),
            )
        if status_code is not None:
            return ProviderStreamChunk(
                status_code=status_code,
                status_message=get_anthropic_status_message(status_code),
            )
        return None

    if event_type == "message_delta":
        status_code = _map_anthropic_status_code(event)
        delta = getattr(event, "delta", None)
        usage = getattr(event, "usage", None)
        return ProviderStreamChunk(
            finish_reason=getattr(delta, "stop_reason", None),
            status_code=status_code,
            status_message=get_anthropic_status_message(status_code) if status_code else None,
            usage=map_anthropic_usage(
                usage,
                public_model_id=public_model_id,
                selected_tool_ids=selected_tool_ids,
            ),
        )

    status_code = _map_anthropic_status_code(event)
    if status_code is not None:
        return ProviderStreamChunk(
            status_code=status_code,
            status_message=get_anthropic_status_message(status_code),
        )

    return None

def _map_anthropic_status_code(event) -> str | None:
    event_type = getattr(event, "type", None)
    if event_type == "message_start":
        return "anthropic_message_start"
    if event_type == "message_stop":
        return "anthropic_message_stop"
    if event_type == "message_delta":
        return "anthropic_message_delta"
    if event_type == "ping":
        return "anthropic_ping"
    if event_type == "content_block_start":
        content_block = getattr(event, "content_block", None)
        content_type = getattr(content_block, "type", None)
        if content_type == "thinking":
            return "anthropic_thinking"
        if content_type in {"tool_use", "server_tool_use"}:
            return "anthropic_tool_use"
        return None
    if event_type != "content_block_delta":
        return None

    delta = getattr(event, "delta", None)
    delta_type = getattr(delta, "type", None)
    if delta_type == "thinking_delta":
        return "anthropic_thinking_delta"
    if delta_type == "signature_delta":
        return "anthropic_thinking_signature"
    if delta_type == "input_json_delta":
        return "anthropic_tool_input"
    return None
