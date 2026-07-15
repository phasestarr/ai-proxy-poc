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

from collections.abc import Iterable

from app.providers.vertex.outcomes import get_vertex_status_message
from app.providers.types import ProviderStreamEvent
from app.providers.vertex.usage import map_vertex_usage
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


def map_vertex_stream_chunk(
    chunk,
    *,
    public_model_id: str,
    selected_tool_ids: Iterable[str] = (),
) -> tuple[ProviderStreamEvent, ...]:
    usage = getattr(chunk, "usage_metadata", None)
    candidates = getattr(chunk, "candidates", None) or []
    finish_reason = None
    status_code = None
    events: list[ProviderStreamEvent] = []

    for candidate_index, candidate in enumerate(candidates):
        finish_reason_value = getattr(candidate, "finish_reason", None)
        if finish_reason_value is not None:
            finish_reason = getattr(finish_reason_value, "name", None) or str(finish_reason_value)
        candidate_status_code = _map_vertex_status_code(candidate, finish_reason)
        status_code = status_code or candidate_status_code
        events.extend(_map_vertex_candidate_parts(candidate, candidate_index=candidate_index))
        grounding_event = _map_vertex_grounding_metadata(candidate, candidate_index=candidate_index)
        if grounding_event is not None:
            events.append(grounding_event)
        url_context_event = _map_vertex_url_context_metadata(candidate, candidate_index=candidate_index)
        if url_context_event is not None:
            events.append(url_context_event)

    if not candidates and getattr(chunk, "prompt_feedback", None) is not None:
        status_code = "vertex_safety_review"

    if status_code is not None:
        events.append(
            ProviderStreamEvent(
                kind="status",
                raw_event_type=type(chunk).__name__,
                response_id=getattr(chunk, "response_id", None),
                model_version=getattr(chunk, "model_version", None),
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
                raw_event_type=type(chunk).__name__,
                stream_to_client=False,
                response_id=getattr(chunk, "response_id", None),
                model_version=getattr(chunk, "model_version", None),
                finish_reason=finish_reason,
                usage=mapped_usage,
            )
        )

    return tuple(events) or (
        ProviderStreamEvent(
            kind="heartbeat",
            stream_to_client=False,
            raw_event_type=type(chunk).__name__,
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


def _map_vertex_candidate_parts(candidate, *, candidate_index: int) -> list[ProviderStreamEvent]:
    content = getattr(candidate, "content", None)
    parts = getattr(content, "parts", None) or []
    events: list[ProviderStreamEvent] = []
    for part_index, part in enumerate(parts):
        text = _field(part, "text")
        is_thought = bool(_field(part, "thought"))
        item_id = f"candidate:{candidate_index}:part:{part_index}"
        if isinstance(text, str) and text:
            events.append(
                ProviderStreamEvent(
                    kind="reasoning_delta" if is_thought else "answer_delta",
                    text_delta=text,
                    append_to_message_content=not is_thought,
                    raw_event_type=type(candidate).__name__,
                    item_id=item_id,
                    output_index=candidate_index,
                    content_index=part_index,
                    metadata={"thought": is_thought} if is_thought else None,
                )
            )

        executable_code = _field(part, "executable_code") or _field(part, "executableCode")
        if executable_code is not None:
            events.append(
                ProviderStreamEvent(
                    kind="tool_input_delta",
                    text_delta=str(_field(executable_code, "code") or ""),
                    raw_event_type=type(candidate).__name__,
                    tool_type="code_execution",
                    item_id=item_id,
                    output_index=candidate_index,
                    content_index=part_index,
                    metadata={"executable_code": _dump_provider_obj(executable_code)},
                )
            )

        code_result = _field(part, "code_execution_result") or _field(part, "codeExecutionResult")
        if code_result is not None:
            events.append(
                ProviderStreamEvent(
                    kind="tool_result",
                    text_delta=str(_field(code_result, "output") or ""),
                    raw_event_type=type(candidate).__name__,
                    tool_type="code_execution",
                    item_id=item_id,
                    output_index=candidate_index,
                    content_index=part_index,
                    metadata={"code_execution_result": _dump_provider_obj(code_result)},
                )
            )

        function_call = _field(part, "function_call") or _field(part, "functionCall")
        if function_call is not None:
            events.append(
                ProviderStreamEvent(
                    kind="tool_input_delta",
                    raw_event_type=type(candidate).__name__,
                    tool_type="function_call",
                    item_id=item_id,
                    output_index=candidate_index,
                    content_index=part_index,
                    metadata={"function_call": _dump_provider_obj(function_call)},
                )
            )

        function_response = _field(part, "function_response") or _field(part, "functionResponse")
        if function_response is not None:
            events.append(
                ProviderStreamEvent(
                    kind="tool_result",
                    raw_event_type=type(candidate).__name__,
                    tool_type="function_call",
                    item_id=item_id,
                    output_index=candidate_index,
                    content_index=part_index,
                    metadata={"function_response": _dump_provider_obj(function_response)},
                )
            )
    return events


def _map_vertex_grounding_metadata(candidate, *, candidate_index: int) -> ProviderStreamEvent | None:
    grounding_metadata = _field(candidate, "grounding_metadata") or _field(candidate, "groundingMetadata")
    if grounding_metadata is None:
        return None
    dumped = _dump_provider_obj(grounding_metadata)
    if not dumped:
        return None
    return ProviderStreamEvent(
        kind="citation",
        raw_event_type=type(candidate).__name__,
        tool_type="web_search",
        item_id=f"candidate:{candidate_index}:grounding",
        output_index=candidate_index,
        metadata={"grounding_metadata": dumped},
    )


def _map_vertex_url_context_metadata(candidate, *, candidate_index: int) -> ProviderStreamEvent | None:
    url_context_metadata = _field(candidate, "url_context_metadata") or _field(candidate, "urlContextMetadata")
    if url_context_metadata is None:
        return None
    dumped = _dump_provider_obj(url_context_metadata)
    if not dumped:
        return None
    return ProviderStreamEvent(
        kind="tool_result",
        raw_event_type=type(candidate).__name__,
        tool_type="url_context",
        item_id=f"candidate:{candidate_index}:url_context",
        output_index=candidate_index,
        text_delta=_format_vertex_url_context(url_context_metadata),
        metadata={"url_context_metadata": dumped},
    )


def _format_vertex_url_context(url_context_metadata) -> str:
    url_metadata = _field(url_context_metadata, "url_metadata") or _field(url_context_metadata, "urlMetadata") or []
    lines: list[str] = []
    for item in url_metadata:
        url = _field(item, "retrieved_url") or _field(item, "retrievedUrl")
        status = _field(item, "url_retrieval_status") or _field(item, "urlRetrievalStatus")
        if url and status:
            lines.append(f"{url}: {status}")
        elif url:
            lines.append(str(url))
    return "\n".join(lines)


def _field(value, name: str):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _dump_provider_obj(value) -> object:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_dump_provider_obj(item) for item in value]
    if isinstance(value, tuple):
        return [_dump_provider_obj(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _dump_provider_obj(item) for key, item in value.items()}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _dump_provider_obj(model_dump(mode="json"))
    return str(value)
