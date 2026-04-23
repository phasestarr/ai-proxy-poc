"""
Purpose:
- Convert internal application request and response structures
  to and from OpenAI Responses API formats.
"""

from __future__ import annotations

from app.providers.types import ProviderStreamChunk, ProviderUsageMetadata
from app.schemas.chat import ChatMessage


def map_chat_messages_to_openai_input(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, object]]]:
    system_messages: list[str] = []
    input_messages: list[dict[str, object]] = []

    for message in messages:
        if message.role == "system":
            system_messages.append(message.content)
            continue

        input_messages.append(
            {
                "role": message.role,
                "content": message.content,
            }
        )

    if not input_messages:
        raise ValueError("at least one non-system message is required")

    request_system_instruction = "\n\n".join(system_messages) if system_messages else None
    return request_system_instruction, input_messages


def map_openai_stream_event(event) -> ProviderStreamChunk | None:
    event_type = getattr(event, "type", None)

    if event_type == "response.output_text.delta":
        return ProviderStreamChunk(text=getattr(event, "delta", None) or "")

    if event_type == "response.refusal.delta":
        return ProviderStreamChunk(text=getattr(event, "delta", None) or "")

    if event_type == "response.completed":
        response = getattr(event, "response", None)
        return ProviderStreamChunk(
            response_id=getattr(response, "id", None),
            model_version=getattr(response, "model", None),
            finish_reason=getattr(response, "status", None) or "completed",
            usage=_map_openai_usage(getattr(response, "usage", None)),
        )

    if event_type == "response.incomplete":
        response = getattr(event, "response", None)
        incomplete_details = getattr(response, "incomplete_details", None)
        reason = getattr(incomplete_details, "reason", None) if incomplete_details is not None else None
        return ProviderStreamChunk(
            response_id=getattr(response, "id", None),
            model_version=getattr(response, "model", None),
            finish_reason=reason or getattr(response, "status", None) or "incomplete",
            usage=_map_openai_usage(getattr(response, "usage", None)),
        )

    return None


def extract_openai_stream_error(event) -> str | None:
    event_type = getattr(event, "type", None)
    if event_type == "error":
        return getattr(event, "message", None) or "openai streaming request failed"

    if event_type != "response.failed":
        return None

    response = getattr(event, "response", None)
    error = getattr(response, "error", None)
    message = getattr(error, "message", None) if error is not None else None
    code = getattr(error, "code", None) if error is not None else None
    if message and code:
        return f"openai request failed ({code}): {message}"
    if message:
        return f"openai request failed: {message}"
    return "openai request failed"


def _map_openai_usage(usage) -> ProviderUsageMetadata | None:
    if usage is None:
        return None

    return ProviderUsageMetadata(
        prompt_token_count=getattr(usage, "input_tokens", None),
        candidates_token_count=getattr(usage, "output_tokens", None),
        total_token_count=getattr(usage, "total_tokens", None),
    )

