"""Vertex request mapping and GenerateContent stream classification."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.providers.types import (
    ProviderStreamEvent,
    ThinkingDeltaBlock,
    ToolUsageBlock,
    dump_provider_value,
)
from app.providers.vertex.outcomes import get_vertex_status_message
from app.providers.vertex.usage import map_vertex_usage
from app.schemas.chat import ChatMessage


@dataclass(slots=True)
class VertexStreamState:
    chunk_ordinal: int = 0


def map_chat_messages_to_vertex_contents(
    messages: list[ChatMessage],
) -> tuple[str | None, list[dict[str, object]]]:
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


def map_vertex_stream_chunk(
    chunk,
    *,
    state: VertexStreamState,
    public_model_id: str,
    selected_tool_ids: Iterable[str] = (),
) -> tuple[ProviderStreamEvent, ...]:
    chunk_ordinal = state.chunk_ordinal
    state.chunk_ordinal += 1

    usage = _field_any(chunk, "usage_metadata", "usageMetadata")
    candidates = _field(chunk, "candidates") or []
    response_id = _string_or_none(_field_any(chunk, "response_id", "responseId"))
    model_version = _string_or_none(_field_any(chunk, "model_version", "modelVersion"))
    finish_reason: str | None = None
    status_code: str | None = None
    events: list[ProviderStreamEvent] = []
    tool_discriminators: list[str] = []
    tool_candidate_indexes: list[int] = []

    for candidate_index, candidate in enumerate(candidates):
        candidate_finish_reason = _finish_reason(candidate)
        if candidate_finish_reason is not None:
            finish_reason = candidate_finish_reason
        parts = _field(_field(candidate, "content"), "parts") or []

        for part_index, part in enumerate(parts):
            text = _field(part, "text")
            is_thought = _field(part, "thought") is True
            if isinstance(text, str) and text:
                if is_thought:
                    block_id = (
                        f"vertex_ai:{response_id or 'unknown'}:thought:"
                        f"{chunk_ordinal}:{candidate_index}:{part_index}"
                    )
                    metadata = _vertex_thinking_metadata(
                        response_id=response_id,
                        model_version=model_version,
                        candidate_index=candidate_index,
                        part_index=part_index,
                    )
                    events.extend(
                        (
                            ProviderStreamEvent(
                                block=ThinkingDeltaBlock(
                                    block_id=block_id,
                                    operation="start",
                                    text_delta=text,
                                    metadata=metadata,
                                ),
                                raw_event_type="generateContent.chunk",
                            ),
                            ProviderStreamEvent(
                                block=ThinkingDeltaBlock(
                                    block_id=block_id,
                                    operation="end",
                                    metadata=metadata,
                                ),
                                raw_event_type="generateContent.chunk",
                            ),
                        )
                    )
                    status_code = status_code or "vertex_thinking"
                else:
                    events.append(
                        ProviderStreamEvent(
                            kind="answer_delta",
                            text_delta=text,
                            append_to_message_content=True,
                            raw_event_type="generateContent.chunk",
                        )
                    )

            part_discriminators = _vertex_part_tool_discriminators(part)
            if part_discriminators:
                tool_discriminators.extend(part_discriminators)
                if candidate_index not in tool_candidate_indexes:
                    tool_candidate_indexes.append(candidate_index)

        candidate_discriminators = _vertex_candidate_tool_discriminators(candidate)
        if candidate_discriminators:
            tool_discriminators.extend(candidate_discriminators)
            if candidate_index not in tool_candidate_indexes:
                tool_candidate_indexes.append(candidate_index)

        if candidate_finish_reason == "SAFETY":
            status_code = "vertex_safety_review"

    if tool_discriminators:
        events.append(
            ProviderStreamEvent(
                block=_vertex_tool_block(
                    chunk,
                    response_id=response_id,
                    model_version=model_version,
                    candidate_indexes=tool_candidate_indexes,
                    discriminators=tool_discriminators,
                ),
                raw_event_type="generateContent.chunk",
            )
        )

    if not candidates and _field_any(chunk, "prompt_feedback", "promptFeedback") is not None:
        status_code = "vertex_safety_review"
    elif status_code is None and (candidates or finish_reason is None):
        status_code = "vertex_streaming"

    if status_code is not None:
        events.append(
            ProviderStreamEvent(
                kind="status",
                raw_event_type="generateContent.chunk",
                response_id=response_id,
                model_version=model_version,
                finish_reason=finish_reason,
                status_code=status_code,
                status_message=get_vertex_status_message(status_code),
            )
        )

    mapped_usage = map_vertex_usage(
        usage,
        public_model_id=public_model_id,
        selected_tool_ids=selected_tool_ids,
    )
    if finish_reason is not None or mapped_usage is not None:
        events.append(
            ProviderStreamEvent(
                kind="completion",
                raw_event_type="generateContent.chunk",
                stream_to_client=False,
                response_id=response_id,
                model_version=model_version,
                finish_reason=finish_reason,
                usage=mapped_usage,
            )
        )

    return tuple(events) or (
        ProviderStreamEvent(
            kind="heartbeat",
            stream_to_client=False,
            raw_event_type="generateContent.chunk",
        ),
    )


def _vertex_thinking_metadata(
    *,
    response_id: str | None,
    model_version: str | None,
    candidate_index: int,
    part_index: int,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "provider": "vertex_ai",
        "semantic_type": "reasoning_delta",
        "provider_event": "generateContent.chunk",
        "provider_subtype": "thought=true",
        "value_path": f"$.candidates[{candidate_index}].content.parts[{part_index}].text",
        "candidate_index": candidate_index,
        "part_index": part_index,
    }
    if response_id:
        metadata["response_id"] = response_id
    if model_version:
        metadata["model"] = model_version
    return metadata


def _vertex_tool_block(
    chunk,
    *,
    response_id: str | None,
    model_version: str | None,
    candidate_indexes: list[int],
    discriminators: list[str],
) -> ToolUsageBlock:
    metadata: dict[str, object] = {
        "provider": "vertex_ai",
        "semantic_type": "tool_event",
        "provider_event": "generateContent.chunk",
        "provider_subtype": ",".join(dict.fromkeys(discriminators)),
        "candidate_indexes": candidate_indexes,
    }
    if response_id:
        metadata["response_id"] = response_id
    if model_version:
        metadata["model"] = model_version
    return ToolUsageBlock(metadata=metadata, raw=dump_provider_value(chunk))


def _vertex_candidate_tool_discriminators(candidate) -> list[str]:
    discriminators: list[str] = []
    if _field_any(candidate, "grounding_metadata", "groundingMetadata") is not None:
        discriminators.append("groundingMetadata")
    if _field_any(candidate, "url_context_metadata", "urlContextMetadata") is not None:
        discriminators.append("urlContextMetadata")
    return discriminators


def _vertex_part_tool_discriminators(part) -> list[str]:
    discriminators: list[str] = []
    fields = (
        ("executable_code", "executableCode", "executableCode"),
        ("code_execution_result", "codeExecutionResult", "codeExecutionResult"),
        ("tool_call", "toolCall", "toolCall"),
        ("tool_response", "toolResponse", "toolResponse"),
    )
    for snake_name, alias_name, label in fields:
        if _field_any(part, snake_name, alias_name) is not None:
            discriminators.append(label)
    return discriminators


def _finish_reason(candidate) -> str | None:
    value = _field_any(candidate, "finish_reason", "finishReason")
    if value is None:
        return None
    return _string_or_none(getattr(value, "name", None) or value)


def _field(value, name: str):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _field_any(value, *names: str):
    for name in names:
        field_value = _field(value, name)
        if field_value is not None:
            return field_value
    return None


def _string_or_none(value: object) -> str | None:
    return str(value) if value is not None else None
