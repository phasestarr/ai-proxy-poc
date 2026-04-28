"""
Purpose:
- Convert internal application request and response structures
  to and from Vertex-specific formats.

Responsibilities:
- Map internal chat messages into Vertex content payloads
- Normalize provider chunks into backend-safe internal types

Notes:
- Keep provider translation logic isolated here to reduce coupling.
"""

from __future__ import annotations

from app.providers.vertex.outcomes import get_vertex_status_message
from app.providers.types import ProviderStreamChunk, ProviderUsageMetadata
from app.schemas.chat import ChatMessage


def map_chat_messages_to_vertex_contents(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, object]]]:
    system_messages: list[str] = []
    contents: list[dict[str, object]] = []

    for message in messages:
        if message.role == "system":
            system_messages.append(message.content)
            continue

        contents.append(
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
        )

    if not contents:
        raise ValueError("at least one non-system message is required")

    system_instruction = "\n\n".join(system_messages) if system_messages else None
    return system_instruction, contents


def map_vertex_stream_chunk(chunk) -> ProviderStreamChunk:
    usage = getattr(chunk, "usage_metadata", None)
    candidates = getattr(chunk, "candidates", None) or []
    finish_reason = None
    status_code = None

    if candidates:
        finish_reason_value = getattr(candidates[0], "finish_reason", None)
        if finish_reason_value is not None:
            finish_reason = getattr(finish_reason_value, "name", None) or str(finish_reason_value)
        status_code = _map_vertex_status_code(candidates[0], finish_reason)
    elif getattr(chunk, "prompt_feedback", None) is not None:
        status_code = "vertex_safety_review"

    return ProviderStreamChunk(
        text=getattr(chunk, "text", None) or "",
        response_id=getattr(chunk, "response_id", None),
        model_version=getattr(chunk, "model_version", None),
        finish_reason=finish_reason,
        status_code=status_code,
        status_message=get_vertex_status_message(status_code) if status_code else None,
        usage=(
            ProviderUsageMetadata(
                prompt_token_count=getattr(usage, "prompt_token_count", None),
                candidates_token_count=getattr(usage, "candidates_token_count", None),
                total_token_count=getattr(usage, "total_token_count", None),
            )
            if usage is not None
            else None
        ),
    )


def _map_vertex_status_code(candidate, finish_reason: str | None) -> str | None:
    content = getattr(candidate, "content", None)
    parts = getattr(content, "parts", None) or []

    for part in parts:
        if getattr(part, "function_call", None) is not None:
            return "vertex_function_call"
        if bool(getattr(part, "thought", False)):
            return "vertex_thinking"
        if getattr(part, "thought_signature", None) is not None:
            return "vertex_thinking"
        if getattr(part, "thoughtSignature", None) is not None:
            return "vertex_thinking"

    if finish_reason == "SAFETY":
        return "vertex_safety_review"

    if parts or finish_reason is None:
        return "vertex_streaming"

    return None
