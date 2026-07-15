"""
Purpose:
- Convert internal application request and response structures
  to and from Anthropic Messages API formats.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.providers.anthropic.outcomes import get_anthropic_status_message
from app.providers.anthropic.usage import map_anthropic_usage
from app.providers.types import ProviderStreamEvent
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
) -> tuple[ProviderStreamEvent, ...]:
    event_type = getattr(event, "type", None)

    if event_type == "content_block_start":
        tool_result = _map_anthropic_content_block_start(event)
        if tool_result is not None:
            return (tool_result,)

    if event_type == "content_block_delta":
        status_code = _map_anthropic_status_code(event)
        delta = getattr(event, "delta", None)
        delta_type = getattr(delta, "type", None)
        if delta_type == "text_delta":
            return (
                ProviderStreamEvent(
                    kind="answer_delta",
                    text_delta=getattr(delta, "text", None) or "",
                    append_to_message_content=True,
                    status_code="anthropic_text_output",
                    status_message=get_anthropic_status_message("anthropic_text_output"),
                    raw_event_type=event_type,
                    item_id=_index_item_id(event),
                    output_index=_optional_int(getattr(event, "index", None)),
                ),
            )
        if delta_type == "thinking_delta":
            return (
                ProviderStreamEvent(
                    kind="reasoning_delta",
                    text_delta=getattr(delta, "thinking", None) or "",
                    status_code=status_code,
                    status_message=get_anthropic_status_message(status_code) if status_code else None,
                    raw_event_type=event_type,
                    item_id=_index_item_id(event),
                    output_index=_optional_int(getattr(event, "index", None)),
                ),
            )
        if delta_type == "input_json_delta":
            return (
                ProviderStreamEvent(
                    kind="tool_input_delta",
                    text_delta=getattr(delta, "partial_json", None) or "",
                    status_code=status_code,
                    status_message=get_anthropic_status_message(status_code) if status_code else None,
                    raw_event_type=event_type,
                    item_id=_index_item_id(event),
                    output_index=_optional_int(getattr(event, "index", None)),
                ),
            )
        if delta_type == "citations_delta":
            return (
                ProviderStreamEvent(
                    kind="citation",
                    raw_event_type=event_type,
                    item_id=_index_item_id(event),
                    output_index=_optional_int(getattr(event, "index", None)),
                    metadata={"citation": _dump_provider_obj(getattr(delta, "citation", None))},
                ),
            )
        if delta_type == "signature_delta":
            return (
                ProviderStreamEvent(
                    kind="metadata",
                    stream_to_client=False,
                    raw_event_type=event_type,
                    item_id=_index_item_id(event),
                    output_index=_optional_int(getattr(event, "index", None)),
                    metadata={"delta_type": delta_type},
                ),
            )
        if status_code is not None:
            return (
                ProviderStreamEvent(
                    kind="status",
                    status_code=status_code,
                    status_message=get_anthropic_status_message(status_code),
                    raw_event_type=event_type,
                    item_id=_index_item_id(event),
                    output_index=_optional_int(getattr(event, "index", None)),
                ),
            )
        return ()

    if event_type == "message_delta":
        status_code = _map_anthropic_status_code(event)
        delta = getattr(event, "delta", None)
        usage = getattr(event, "usage", None)
        stop_reason = getattr(delta, "stop_reason", None)
        return (
            ProviderStreamEvent(
                kind="completion" if stop_reason or usage is not None else "status",
                finish_reason=stop_reason,
                status_code=status_code,
                status_message=get_anthropic_status_message(status_code) if status_code else None,
                raw_event_type=event_type,
                stream_to_client=False,
                usage=map_anthropic_usage(
                    usage,
                    public_model_id=public_model_id,
                    selected_tool_ids=selected_tool_ids,
                ),
            ),
        )

    status_code = _map_anthropic_status_code(event)
    if status_code is not None:
        return (
            ProviderStreamEvent(
                kind="status",
                status_code=status_code,
                status_message=get_anthropic_status_message(status_code),
                raw_event_type=event_type,
                item_id=_index_item_id(event),
                output_index=_optional_int(getattr(event, "index", None)),
                tool_type=_anthropic_tool_type(getattr(event, "content_block", None)),
            ),
        )

    return ()


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


def _map_anthropic_content_block_start(event) -> ProviderStreamEvent | None:
    content_block = getattr(event, "content_block", None)
    content_type = getattr(content_block, "type", None)
    if content_type == "web_search_tool_result":
        return ProviderStreamEvent(
            kind="tool_result",
            raw_event_type=getattr(event, "type", None),
            tool_type="web_search",
            item_id=getattr(content_block, "tool_use_id", None) or _index_item_id(event),
            output_index=_optional_int(getattr(event, "index", None)),
            text_delta=_format_anthropic_web_search_results(content_block),
            metadata={"content_block": _dump_provider_obj(content_block)},
        )
    if content_type in {
        "code_execution_tool_result",
        "bash_code_execution_tool_result",
        "text_editor_code_execution_tool_result",
    }:
        return ProviderStreamEvent(
            kind="tool_result",
            raw_event_type=getattr(event, "type", None),
            tool_type=_anthropic_result_tool_type(content_type),
            item_id=getattr(content_block, "tool_use_id", None) or _index_item_id(event),
            output_index=_optional_int(getattr(event, "index", None)),
            text_delta=_format_anthropic_code_result(content_block),
            metadata={"content_block": _dump_provider_obj(content_block)},
        )
    return None


def _format_anthropic_web_search_results(content_block) -> str:
    content = _field(content_block, "content") or []
    lines: list[str] = []
    for item in content:
        title = _field(item, "title")
        url = _field(item, "url")
        if title and url:
            lines.append(f"- {title}: {url}")
        elif title:
            lines.append(f"- {title}")
        elif url:
            lines.append(f"- {url}")
    return "\n".join(lines)


def _format_anthropic_code_result(content_block) -> str:
    content = _field(content_block, "content")
    if content is None:
        return ""
    stdout = _field(content, "stdout")
    stderr = _field(content, "stderr")
    parts: list[str] = []
    if stdout:
        parts.append(str(stdout))
    if stderr:
        parts.append(str(stderr))
    return "\n".join(parts)


def _anthropic_result_tool_type(content_type: str) -> str:
    if content_type == "bash_code_execution_tool_result":
        return "bash_code_execution"
    if content_type == "text_editor_code_execution_tool_result":
        return "text_editor_code_execution"
    return "code_execution"


def _anthropic_tool_type(content_block) -> str | None:
    if content_block is None:
        return None
    return _field(content_block, "name") or _field(content_block, "type")


def _field(value, name: str):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _index_item_id(event) -> str | None:
    index = getattr(event, "index", None)
    return f"content_block:{index}" if index is not None else None


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


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
