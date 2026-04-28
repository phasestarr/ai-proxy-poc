"""
Purpose:
- Convert internal application request and response structures
  to and from OpenAI Responses API formats.
"""

from __future__ import annotations

from app.providers.types import ProviderStreamChunk, ProviderUsageMetadata
from app.providers.openai.outcomes import get_openai_status_message
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

    status_code = _map_openai_status_code(event_type)
    if status_code is not None:
        return ProviderStreamChunk(
            status_code=status_code,
            status_message=get_openai_status_message(status_code),
        )

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


def _map_openai_status_code(event_type: str | None) -> str | None:
    if event_type == "response.created":
        return "openai_response_created"
    if event_type == "response.queued":
        return "openai_response_queued"
    if event_type == "response.in_progress":
        return "openai_response_in_progress"
    if isinstance(event_type, str) and event_type.startswith("response.reasoning"):
        return "openai_reasoning"
    if isinstance(event_type, str) and event_type.startswith("response.function_call_arguments"):
        return "openai_function_calling"
    if isinstance(event_type, str) and event_type.startswith("response.web_search_call"):
        return "openai_web_search"
    if isinstance(event_type, str) and event_type.startswith("response.file_search_call"):
        return "openai_file_search"
    if isinstance(event_type, str) and event_type.startswith("response.code_interpreter_call"):
        return "openai_code_execution"
    if isinstance(event_type, str) and event_type.startswith("response.image_generation_call"):
        return "openai_image_generation"
    if isinstance(event_type, str) and event_type.startswith("response.mcp_call"):
        return "openai_mcp_call"
    return None
