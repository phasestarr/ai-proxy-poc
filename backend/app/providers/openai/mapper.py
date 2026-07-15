"""OpenAI request mapping and stateful Responses stream classification."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.providers.openai.outcomes import get_openai_status_message
from app.providers.openai.usage import map_openai_usage
from app.providers.types import (
    ProviderStreamEvent,
    ThinkingDeltaBlock,
    ToolBlockOperation,
    ToolUsageBlock,
    dump_provider_value,
)
from app.schemas.chat import ChatMessage


@dataclass(slots=True)
class _OpenAIThinkingBlockState:
    started: bool = False


@dataclass(slots=True)
class OpenAIStreamState:
    response_id: str | None = None
    model: str | None = None
    thinking_blocks: dict[tuple[str, int], _OpenAIThinkingBlockState] = field(default_factory=dict)
    tool_item_types: dict[str, str] = field(default_factory=dict)
    message_phases: dict[str, str] = field(default_factory=dict)


def map_chat_messages_to_openai_input(
    messages: list[ChatMessage],
) -> tuple[str | None, list[dict[str, object]]]:
    system_messages: list[str] = []
    input_messages: list[dict[str, object]] = []

    for message in messages:
        if message.role == "system":
            system_messages.append(message.content)
            continue
        input_messages.append({"role": message.role, "content": message.content})

    if not input_messages:
        raise ValueError("at least one non-system message is required")

    request_system_instruction = "\n\n".join(system_messages) if system_messages else None
    return request_system_instruction, input_messages


def map_openai_stream_event(
    event,
    *,
    state: OpenAIStreamState,
    public_model_id: str,
    selected_tool_ids: Iterable[str] = (),
) -> tuple[ProviderStreamEvent, ...]:
    event_type = _string_or_none(_field(event, "type"))

    if event_type == "response.created":
        response = _field(event, "response")
        state.response_id = _string_or_none(_field(response, "id"))
        state.model = _string_or_none(_field(response, "model"))
        return (_status_event(event_type, "openai_response_created"),)

    if event_type in {"response.queued", "response.in_progress"}:
        status_code = (
            "openai_response_queued"
            if event_type == "response.queued"
            else "openai_response_in_progress"
        )
        return (_status_event(event_type, status_code),)

    if event_type in {"response.output_item.added", "response.output_item.done"}:
        return _map_output_item_event(event, event_type=event_type, state=state)

    if event_type == "response.reasoning_summary_part.added":
        key = _thinking_key(event)
        if key is not None:
            state.thinking_blocks.setdefault(key, _OpenAIThinkingBlockState())
        return ()

    if event_type == "response.reasoning_summary_text.delta":
        return _map_reasoning_delta(event, state=state)

    if event_type in {
        "response.reasoning_summary_text.done",
        "response.reasoning_summary_part.done",
    }:
        return _map_reasoning_done(event, event_type=event_type, state=state)

    item_id = _string_or_none(_field(event, "item_id"))
    if item_id and item_id in state.tool_item_types:
        item_type = state.tool_item_types[item_id]
        status_code = _tool_status_code(item_type)
        return (
            ProviderStreamEvent(
                block=_openai_tool_block(
                    event,
                    event_type=event_type or "unknown",
                    state=state,
                    item_id=item_id,
                    item_type=item_type,
                    operation="delta",
                ),
                status_code=status_code,
                status_message=get_openai_status_message(status_code) if status_code else None,
                raw_event_type=event_type,
            ),
        )

    if event_type in {"response.output_text.delta", "response.refusal.delta"}:
        if not item_id or state.message_phases.get(item_id) != "final_answer":
            return ()
        text = _field(event, "delta")
        if not isinstance(text, str) or not text:
            return ()
        return (
            ProviderStreamEvent(
                kind="answer_delta",
                text_delta=text,
                append_to_message_content=True,
                raw_event_type=event_type,
            ),
        )

    if event_type == "response.completed":
        response = _field(event, "response")
        return (
            ProviderStreamEvent(
                kind="completion",
                response_id=_string_or_none(_field(response, "id")) or state.response_id,
                model_version=_string_or_none(_field(response, "model")) or state.model,
                finish_reason=_string_or_none(_field(response, "status")) or "completed",
                raw_event_type=event_type,
                stream_to_client=False,
                usage=map_openai_usage(
                    _field(response, "usage"),
                    public_model_id=public_model_id,
                    selected_tool_ids=selected_tool_ids,
                    response_output=_field(response, "output"),
                ),
            ),
        )

    if event_type == "response.incomplete":
        response = _field(event, "response")
        incomplete_details = _field(response, "incomplete_details")
        reason = _string_or_none(_field(incomplete_details, "reason"))
        return (
            ProviderStreamEvent(
                kind="completion",
                response_id=_string_or_none(_field(response, "id")) or state.response_id,
                model_version=_string_or_none(_field(response, "model")) or state.model,
                finish_reason=reason or _string_or_none(_field(response, "status")) or "incomplete",
                raw_event_type=event_type,
                stream_to_client=False,
                usage=map_openai_usage(
                    _field(response, "usage"),
                    public_model_id=public_model_id,
                    selected_tool_ids=selected_tool_ids,
                    response_output=_field(response, "output"),
                ),
            ),
        )

    # Done snapshots and annotations repeat text or carry answer metadata. They
    # are deliberately not converted into thinking/tool blocks.
    return ()


def _map_output_item_event(
    event,
    *,
    event_type: str,
    state: OpenAIStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    item = _field(event, "item")
    item_type = _string_or_none(_field(item, "type"))
    item_id = _string_or_none(_field(item, "id"))
    if not item_type or not item_id:
        return ()

    if item_type == "message":
        phase = _string_or_none(_field(item, "phase"))
        if phase:
            state.message_phases[item_id] = phase
        if event_type == "response.output_item.done":
            return (
                ProviderStreamEvent(
                    kind="metadata",
                    raw_event_type=event_type,
                    stream_to_client=False,
                    metadata={
                        "item_type": item_type,
                        "status": _field(item, "status"),
                        "phase": phase,
                    },
                ),
            )
        return ()

    if not _is_openai_tool_item_type(item_type):
        return ()

    state.tool_item_types[item_id] = item_type
    status_code = _tool_status_code(item_type)
    return (
        ProviderStreamEvent(
            block=_openai_tool_block(
                event,
                event_type=event_type,
                state=state,
                item_id=item_id,
                item_type=item_type,
                operation="end" if event_type == "response.output_item.done" else "start",
            ),
            status_code=status_code,
            status_message=get_openai_status_message(status_code) if status_code else None,
            raw_event_type=event_type,
        ),
    )


def _map_reasoning_delta(
    event,
    *,
    state: OpenAIStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    key = _thinking_key(event)
    text = _field(event, "delta")
    if key is None or not isinstance(text, str) or not text:
        return ()
    block_state = state.thinking_blocks.setdefault(key, _OpenAIThinkingBlockState())
    operation = "delta" if block_state.started else "start"
    block_state.started = True
    status_code = "openai_reasoning"
    return (
        ProviderStreamEvent(
            block=ThinkingDeltaBlock(
                block_id=_openai_thinking_block_id(state=state, key=key),
                operation=operation,
                text_delta=text,
                metadata=_openai_thinking_metadata(
                    event,
                    event_type="response.reasoning_summary_text.delta",
                    state=state,
                    key=key,
                ),
            ),
            status_code=status_code,
            status_message=get_openai_status_message(status_code),
            raw_event_type="response.reasoning_summary_text.delta",
        ),
    )


def _map_reasoning_done(
    event,
    *,
    event_type: str,
    state: OpenAIStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    key = _thinking_key(event)
    if key is None:
        return ()
    block_state = state.thinking_blocks.pop(key, None)
    if block_state is None or not block_state.started:
        return ()
    return (
        ProviderStreamEvent(
            block=ThinkingDeltaBlock(
                block_id=_openai_thinking_block_id(state=state, key=key),
                operation="end",
                metadata=_openai_thinking_metadata(
                    event,
                    event_type=event_type,
                    state=state,
                    key=key,
                ),
            ),
            raw_event_type=event_type,
        ),
    )


def _openai_thinking_metadata(
    event,
    *,
    event_type: str,
    state: OpenAIStreamState,
    key: tuple[str, int],
) -> dict[str, object]:
    item_id, summary_index = key
    metadata: dict[str, object] = {
        "provider": "openai",
        "semantic_type": "reasoning_delta",
        "provider_event": event_type,
        "value_path": "$.delta",
        "item_id": item_id,
        "summary_index": summary_index,
    }
    if state.response_id:
        metadata["response_id"] = state.response_id
    sequence_number = _optional_int(_field(event, "sequence_number"))
    output_index = _optional_int(_field(event, "output_index"))
    if sequence_number is not None:
        metadata["sequence_number"] = sequence_number
    if output_index is not None:
        metadata["output_index"] = output_index
    return metadata


def _openai_tool_block(
    event,
    *,
    event_type: str,
    state: OpenAIStreamState,
    item_id: str,
    item_type: str,
    operation: ToolBlockOperation,
) -> ToolUsageBlock:
    metadata: dict[str, object] = {
        "provider": "openai",
        "semantic_type": "tool_event",
        "provider_event": event_type,
        "provider_subtype": item_type,
        "item_id": item_id,
    }
    if state.response_id:
        metadata["response_id"] = state.response_id
    sequence_number = _optional_int(_field(event, "sequence_number"))
    output_index = _optional_int(_field(event, "output_index"))
    if sequence_number is not None:
        metadata["sequence_number"] = sequence_number
    if output_index is not None:
        metadata["output_index"] = output_index
    return ToolUsageBlock(
        block_id=_openai_tool_block_id(state=state, item_id=item_id),
        operation=operation,
        metadata=metadata,
        raw=dump_provider_value(event),
    )


def _thinking_key(event) -> tuple[str, int] | None:
    item_id = _string_or_none(_field(event, "item_id"))
    summary_index = _optional_int(_field(event, "summary_index"))
    if item_id is None or summary_index is None:
        return None
    return item_id, summary_index


def _openai_thinking_block_id(
    *,
    state: OpenAIStreamState,
    key: tuple[str, int],
) -> str:
    item_id, summary_index = key
    return f"openai:{state.response_id or 'unknown'}:{item_id}:{summary_index}"


def _openai_tool_block_id(
    *,
    state: OpenAIStreamState,
    item_id: str,
) -> str:
    return f"openai:{state.response_id or 'unknown'}:tool:{item_id}"


def _is_openai_tool_item_type(item_type: str) -> bool:
    # Caller-managed function calls require a separate request/response loop and
    # are intentionally outside this proxy's provider-native tool contract.
    return item_type.endswith("_call") and item_type != "function_call"


def _tool_status_code(item_type: str) -> str | None:
    if item_type == "web_search_call":
        return "openai_web_search"
    if item_type == "file_search_call":
        return "openai_file_search"
    if item_type == "code_interpreter_call":
        return "openai_code_execution"
    if item_type == "image_generation_call":
        return "openai_image_generation"
    if item_type == "mcp_call":
        return "openai_mcp_call"
    return None


def _status_event(event_type: str, status_code: str) -> ProviderStreamEvent:
    return ProviderStreamEvent(
        kind="status",
        status_code=status_code,
        status_message=get_openai_status_message(status_code),
        raw_event_type=event_type,
    )


def _field(value, name: str):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _string_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
