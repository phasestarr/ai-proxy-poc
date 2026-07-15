"""
Purpose:
- Convert internal application request and response structures
  to and from OpenAI Responses API formats.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.providers.openai.usage import map_openai_usage
from app.providers.types import ProviderStreamEvent
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


def map_openai_stream_event(
    event,
    *,
    public_model_id: str,
    selected_tool_ids: Iterable[str] = (),
) -> tuple[ProviderStreamEvent, ...]:
    event_type = getattr(event, "type", None)

    if event_type == "response.reasoning_summary_text.delta":
        return (
            ProviderStreamEvent(
                kind="reasoning_delta",
                text_delta=getattr(event, "delta", None) or "",
                raw_event_type=event_type,
                item_id=getattr(event, "item_id", None),
                output_index=_optional_int(getattr(event, "output_index", None)),
                content_index=_optional_int(getattr(event, "summary_index", None)),
            ),
        )

    if event_type == "response.code_interpreter_call_code.delta":
        return (
            ProviderStreamEvent(
                kind="tool_input_delta",
                text_delta=getattr(event, "delta", None) or "",
                raw_event_type=event_type,
                tool_type="code_interpreter",
                item_id=getattr(event, "item_id", None),
                output_index=_optional_int(getattr(event, "output_index", None)),
            ),
        )

    if event_type == "response.output_text.annotation.added":
        return (
            ProviderStreamEvent(
                kind="citation",
                raw_event_type=event_type,
                item_id=getattr(event, "item_id", None),
                output_index=_optional_int(getattr(event, "output_index", None)),
                content_index=_optional_int(getattr(event, "content_index", None)),
                metadata={"annotation": _dump_provider_obj(getattr(event, "annotation", None))},
            ),
        )

    if event_type == "response.output_text.done":
        return (
            ProviderStreamEvent(
                kind="metadata",
                raw_event_type=event_type,
                stream_to_client=False,
                item_id=getattr(event, "item_id", None),
                output_index=_optional_int(getattr(event, "output_index", None)),
                content_index=_optional_int(getattr(event, "content_index", None)),
            ),
        )

    if event_type == "response.content_part.done":
        part = getattr(event, "part", None)
        if getattr(part, "type", None) == "output_text":
            return (
                ProviderStreamEvent(
                    kind="metadata",
                    raw_event_type=event_type,
                    stream_to_client=False,
                    item_id=getattr(event, "item_id", None),
                    output_index=_optional_int(getattr(event, "output_index", None)),
                    content_index=_optional_int(getattr(event, "content_index", None)),
                ),
            )

    if event_type == "response.refusal.done":
        return (
            ProviderStreamEvent(
                kind="metadata",
                raw_event_type=event_type,
                stream_to_client=False,
                item_id=getattr(event, "item_id", None),
                output_index=_optional_int(getattr(event, "output_index", None)),
                content_index=_optional_int(getattr(event, "content_index", None)),
            ),
        )

    if event_type == "response.output_item.done":
        tool_result = _map_openai_output_item_done(event_type, getattr(event, "item", None))
        if tool_result is not None:
            return (tool_result,)

    status_code = _map_openai_status_code(event_type)
    if status_code is not None:
        return (
            ProviderStreamEvent(
                kind="status",
                status_code=status_code,
                status_message=get_openai_status_message(status_code),
                raw_event_type=event_type,
                item_id=getattr(event, "item_id", None),
                output_index=_optional_int(getattr(event, "output_index", None)),
            ),
        )

    if event_type == "response.output_text.delta":
        return (
            ProviderStreamEvent(
                kind="answer_delta",
                text_delta=getattr(event, "delta", None) or "",
                append_to_message_content=True,
                raw_event_type=event_type,
                item_id=getattr(event, "item_id", None),
                output_index=_optional_int(getattr(event, "output_index", None)),
                content_index=_optional_int(getattr(event, "content_index", None)),
            ),
        )

    if event_type == "response.refusal.delta":
        return (
            ProviderStreamEvent(
                kind="answer_delta",
                text_delta=getattr(event, "delta", None) or "",
                append_to_message_content=True,
                raw_event_type=event_type,
                item_id=getattr(event, "item_id", None),
                output_index=_optional_int(getattr(event, "output_index", None)),
                content_index=_optional_int(getattr(event, "content_index", None)),
            ),
        )

    if event_type == "response.completed":
        response = getattr(event, "response", None)
        return (
            ProviderStreamEvent(
                kind="completion",
                response_id=getattr(response, "id", None),
                model_version=getattr(response, "model", None),
                finish_reason=getattr(response, "status", None) or "completed",
                raw_event_type=event_type,
                stream_to_client=False,
                usage=map_openai_usage(
                    getattr(response, "usage", None),
                    public_model_id=public_model_id,
                    selected_tool_ids=selected_tool_ids,
                    response_output=getattr(response, "output", None),
                ),
            ),
        )

    if event_type == "response.incomplete":
        response = getattr(event, "response", None)
        incomplete_details = getattr(response, "incomplete_details", None)
        reason = getattr(incomplete_details, "reason", None) if incomplete_details is not None else None
        return (
            ProviderStreamEvent(
                kind="completion",
                response_id=getattr(response, "id", None),
                model_version=getattr(response, "model", None),
                finish_reason=reason or getattr(response, "status", None) or "incomplete",
                raw_event_type=event_type,
                stream_to_client=False,
                usage=map_openai_usage(
                    getattr(response, "usage", None),
                    public_model_id=public_model_id,
                    selected_tool_ids=selected_tool_ids,
                    response_output=getattr(response, "output", None),
                ),
            ),
        )

    return ()


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


def _map_openai_output_item_done(event_type: str, item) -> ProviderStreamEvent | None:
    item_type = getattr(item, "type", None)
    item_id = getattr(item, "id", None)
    if item_type == "message":
        return ProviderStreamEvent(
            kind="metadata",
            raw_event_type=event_type,
            stream_to_client=False,
            item_id=item_id,
            metadata={"item_type": item_type, "status": getattr(item, "status", None)},
        )
    if item_type == "web_search_call":
        return ProviderStreamEvent(
            kind="tool_result",
            raw_event_type=event_type,
            tool_type="web_search",
            item_id=item_id,
            metadata={"item": _dump_provider_obj(item)},
        )
    if item_type == "file_search_call":
        return ProviderStreamEvent(
            kind="tool_result",
            raw_event_type=event_type,
            tool_type="file_search",
            item_id=item_id,
            metadata={"item": _dump_provider_obj(item)},
        )
    if item_type == "code_interpreter_call":
        return ProviderStreamEvent(
            kind="tool_result",
            text_delta=_extract_openai_code_outputs_text(item),
            raw_event_type=event_type,
            tool_type="code_interpreter",
            item_id=item_id,
            metadata={"item": _dump_provider_obj(item)},
        )
    return None


def _extract_openai_code_outputs_text(item) -> str:
    outputs = getattr(item, "outputs", None) or []
    chunks: list[str] = []
    for output in outputs:
        output_type = getattr(output, "type", None)
        logs = getattr(output, "logs", None)
        if output_type == "logs" and logs:
            chunks.append(str(logs))
    return "\n".join(chunks)


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
