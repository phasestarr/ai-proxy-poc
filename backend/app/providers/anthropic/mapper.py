"""Anthropic request mapping and stateful stream classification."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.providers.anthropic.outcomes import get_anthropic_status_message
from app.providers.anthropic.usage import map_anthropic_usage
from app.providers.types import (
    ProviderStreamEvent,
    ThinkingDeltaBlock,
    ToolUsageBlock,
    dump_provider_value,
)
from app.schemas.chat import ChatMessage


@dataclass(slots=True)
class _AnthropicContentBlockState:
    content_type: str
    block_id: str
    tool_name: str | None = None
    tool_use_id: str | None = None
    thinking_started: bool = False


@dataclass(slots=True)
class AnthropicStreamState:
    message_id: str | None = None
    model: str | None = None
    blocks: dict[int, _AnthropicContentBlockState] = field(default_factory=dict)


def map_chat_messages_to_anthropic_messages(
    messages: list[ChatMessage],
) -> tuple[str | None, list[dict[str, object]]]:
    system_messages: list[str] = []
    anthropic_messages: list[dict[str, object]] = []

    for message in messages:
        if message.role == "system":
            system_messages.append(message.content)
            continue
        anthropic_messages.append({"role": message.role, "content": message.content})

    if not anthropic_messages:
        raise ValueError("at least one non-system message is required")

    request_system_instruction = "\n\n".join(system_messages) if system_messages else None
    return request_system_instruction, anthropic_messages


def map_anthropic_stream_event(
    event,
    *,
    state: AnthropicStreamState,
    public_model_id: str,
    selected_tool_ids: Iterable[str] = (),
) -> tuple[ProviderStreamEvent, ...]:
    event_type = _field(event, "type")

    if event_type == "message_start":
        message = _field(event, "message")
        state.message_id = _string_or_none(_field(message, "id"))
        state.model = _string_or_none(_field(message, "model"))
        return (_status_event(event_type, "anthropic_message_start"),)

    if event_type == "content_block_start":
        return _map_content_block_start(event, state=state)

    if event_type == "content_block_delta":
        return _map_content_block_delta(event, state=state)

    if event_type == "content_block_stop":
        return _map_content_block_stop(event, state=state)

    if event_type == "message_delta":
        delta = _field(event, "delta")
        usage = _field(event, "usage")
        stop_reason = _string_or_none(_field(delta, "stop_reason"))
        status_code = "anthropic_message_delta"
        return (
            ProviderStreamEvent(
                kind="completion" if stop_reason or usage is not None else "status",
                finish_reason=stop_reason,
                status_code=status_code,
                status_message=get_anthropic_status_message(status_code),
                raw_event_type=event_type,
                stream_to_client=False,
                usage=map_anthropic_usage(
                    usage,
                    public_model_id=public_model_id,
                    selected_tool_ids=selected_tool_ids,
                ),
            ),
        )

    status_code_by_event = {
        "message_stop": "anthropic_message_stop",
        "ping": "anthropic_ping",
    }
    status_code = status_code_by_event.get(str(event_type))
    if status_code:
        return (_status_event(event_type, status_code),)
    return ()


def _map_content_block_start(
    event,
    *,
    state: AnthropicStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    index = _optional_int(_field(event, "index"))
    content_block = _field(event, "content_block")
    content_type = _string_or_none(_field(content_block, "type")) or "unknown"
    block_index = index if index is not None else -1
    block_state = _AnthropicContentBlockState(
        content_type=content_type,
        block_id=f"anthropic:{state.message_id or 'unknown'}:{block_index}",
        tool_name=_string_or_none(_field(content_block, "name")),
        tool_use_id=_string_or_none(
            _field(content_block, "id") or _field(content_block, "tool_use_id")
        ),
    )
    if index is not None:
        state.blocks[index] = block_state

    if _is_anthropic_tool_block(content_type):
        status_code = "anthropic_tool_use"
        return (
            ProviderStreamEvent(
                block=_anthropic_tool_block(
                    event,
                    event_type="content_block_start",
                    state=state,
                    block_index=block_index,
                    block_state=block_state,
                    provider_subtype=content_type,
                ),
                status_code=status_code,
                status_message=get_anthropic_status_message(status_code),
                raw_event_type="content_block_start",
            ),
        )

    if content_type == "thinking":
        return (_status_event("content_block_start", "anthropic_thinking"),)

    if content_type == "text":
        text = _field(content_block, "text")
        if isinstance(text, str) and text:
            return (
                ProviderStreamEvent(
                    kind="answer_delta",
                    text_delta=text,
                    append_to_message_content=True,
                    status_code="anthropic_text_output",
                    status_message=get_anthropic_status_message("anthropic_text_output"),
                    raw_event_type="content_block_start",
                ),
            )
    return ()


def _map_content_block_delta(
    event,
    *,
    state: AnthropicStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    index = _optional_int(_field(event, "index"))
    block_state = state.blocks.get(index) if index is not None else None
    if block_state is None:
        return ()

    delta = _field(event, "delta")
    delta_type = _string_or_none(_field(delta, "type"))

    if _is_anthropic_tool_block(block_state.content_type):
        status_code = "anthropic_tool_input" if delta_type == "input_json_delta" else None
        return (
            ProviderStreamEvent(
                block=_anthropic_tool_block(
                    event,
                    event_type="content_block_delta",
                    state=state,
                    block_index=index if index is not None else -1,
                    block_state=block_state,
                    provider_subtype=delta_type,
                ),
                status_code=status_code,
                status_message=get_anthropic_status_message(status_code) if status_code else None,
                raw_event_type="content_block_delta",
            ),
        )

    if block_state.content_type == "thinking" and delta_type == "thinking_delta":
        text = _field(delta, "thinking")
        if not isinstance(text, str) or not text:
            return ()
        operation = "delta" if block_state.thinking_started else "start"
        block_state.thinking_started = True
        status_code = "anthropic_thinking_delta"
        return (
            ProviderStreamEvent(
                block=ThinkingDeltaBlock(
                    block_id=block_state.block_id,
                    operation=operation,
                    text_delta=text,
                    metadata=_anthropic_thinking_metadata(
                        state=state,
                        provider_event="content_block_delta",
                        provider_subtype="thinking_delta",
                        block_index=index if index is not None else -1,
                    ),
                ),
                status_code=status_code,
                status_message=get_anthropic_status_message(status_code),
                raw_event_type="content_block_delta",
            ),
        )

    if block_state.content_type == "text" and delta_type == "text_delta":
        text = _field(delta, "text")
        if isinstance(text, str) and text:
            return (
                ProviderStreamEvent(
                    kind="answer_delta",
                    text_delta=text,
                    append_to_message_content=True,
                    status_code="anthropic_text_output",
                    status_message=get_anthropic_status_message("anthropic_text_output"),
                    raw_event_type="content_block_delta",
                ),
            )
    return ()


def _map_content_block_stop(
    event,
    *,
    state: AnthropicStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    index = _optional_int(_field(event, "index"))
    block_state = state.blocks.get(index) if index is not None else None
    if block_state is None:
        return ()

    if _is_anthropic_tool_block(block_state.content_type):
        mapped = (
            ProviderStreamEvent(
                block=_anthropic_tool_block(
                    event,
                    event_type="content_block_stop",
                    state=state,
                    block_index=index if index is not None else -1,
                    block_state=block_state,
                    provider_subtype=block_state.content_type,
                ),
                raw_event_type="content_block_stop",
            ),
        )
    elif block_state.content_type == "thinking" and block_state.thinking_started:
        mapped = (
            ProviderStreamEvent(
                block=ThinkingDeltaBlock(
                    block_id=block_state.block_id,
                    operation="end",
                    metadata=_anthropic_thinking_metadata(
                        state=state,
                        provider_event="content_block_stop",
                        provider_subtype="thinking",
                        block_index=index if index is not None else -1,
                    ),
                ),
                raw_event_type="content_block_stop",
            ),
        )
    else:
        mapped = ()

    if index is not None:
        del state.blocks[index]
    return mapped


def _anthropic_thinking_metadata(
    *,
    state: AnthropicStreamState,
    provider_event: str,
    provider_subtype: str,
    block_index: int,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "provider": "anthropic",
        "semantic_type": "reasoning_delta",
        "provider_event": provider_event,
        "provider_subtype": provider_subtype,
        "value_path": "$.delta.thinking",
        "block_index": block_index,
    }
    if state.message_id:
        metadata["message_id"] = state.message_id
    if state.model:
        metadata["model"] = state.model
    return metadata


def _anthropic_tool_block(
    event,
    *,
    event_type: str,
    state: AnthropicStreamState,
    block_index: int,
    block_state: _AnthropicContentBlockState,
    provider_subtype: str | None,
) -> ToolUsageBlock:
    metadata: dict[str, object] = {
        "provider": "anthropic",
        "semantic_type": "tool_event",
        "provider_event": event_type,
        "block_index": block_index,
    }
    if provider_subtype:
        metadata["provider_subtype"] = provider_subtype
    if state.message_id:
        metadata["message_id"] = state.message_id
    if block_state.tool_name:
        metadata["tool_name"] = block_state.tool_name
    if block_state.tool_use_id:
        metadata["tool_use_id"] = block_state.tool_use_id
    return ToolUsageBlock(metadata=metadata, raw=dump_provider_value(event))


def _is_anthropic_tool_block(content_type: str) -> bool:
    return content_type == "server_tool_use" or content_type.endswith("_tool_result")


def _status_event(event_type: object, status_code: str) -> ProviderStreamEvent:
    return ProviderStreamEvent(
        kind="status",
        status_code=status_code,
        status_message=get_anthropic_status_message(status_code),
        raw_event_type=str(event_type) if event_type is not None else None,
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
