"""
Purpose:
- Execute streamed OpenAI Responses API requests.

Responsibilities:
- Call the OpenAI async streaming API
- Translate provider events into normalized internal stream chunks
- Surface provider failures as controlled exceptions
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass

from app.providers.openai.client import build_openai_client
from app.providers.openai.config import build_openai_responses_request
from app.providers.openai.mapper import (
    OpenAIStreamState,
    map_chat_messages_to_openai_input,
    map_openai_stream_event,
)
from app.providers.openai.models import resolve_openai_model_runtime
from app.providers.openai.outcomes import (
    build_openai_empty_output_detail,
    build_openai_failed_detail,
    build_openai_status_error_detail,
    get_openai_result_message,
)
from app.providers.openai.tools import OpenAIToolConfigurationError
from app.providers.token_estimation import estimate_token_count_from_object
from app.providers.types import (
    PreparedProviderChatRequest,
    ProviderRawStreamChunk,
    ProviderStreamEvent,
)
from app.schemas.chat import ChatMessage

logger = logging.getLogger("uvicorn.error")


class OpenAIProviderError(RuntimeError):
    """Raised when an OpenAI request fails while streaming."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        result_code: str | None = None,
        result_message: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.result_code = result_code
        self.result_message = result_message
        super().__init__(message)


@dataclass(slots=True, frozen=True)
class _OpenAIStreamFailure:
    result_code: str
    result_message: str
    detail: str
    status_code: int | None = None
    error_code: str | None = None


async def stream_openai_chat_completion(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> AsyncIterator[ProviderStreamEvent]:
    prepared_request = build_openai_prepared_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=selected_tool_ids,
    )
    async for chunk in stream_prepared_openai_chat_completion(prepared_request):
        yield chunk


async def stream_prepared_openai_chat_completion(
    prepared_request: PreparedProviderChatRequest,
) -> AsyncIterator[ProviderStreamEvent]:
    state = OpenAIStreamState()
    async for raw_chunk in stream_prepared_openai_raw_chat_completion(prepared_request):
        for stream_event in map_prepared_openai_raw_stream_event(
            prepared_request,
            raw_chunk,
            state=state,
        ):
            yield stream_event


async def stream_prepared_openai_raw_chat_completion(
    prepared_request: PreparedProviderChatRequest,
) -> AsyncIterator[ProviderRawStreamChunk]:
    client = build_openai_client()
    saw_visible_text = False
    saw_terminal_completion = False
    message_phases: dict[str, str] = {}

    try:
        stream = await client.responses.create(
            **prepared_request.payload,
            stream=True,
        )
        async for event in stream:
            event_type = getattr(event, "type", None)
            failure = extract_openai_stream_error(event)
            if failure:
                raise OpenAIProviderError(
                    failure.detail,
                    status_code=failure.status_code,
                    error_code=failure.error_code,
                    result_code=failure.result_code,
                    result_message=failure.result_message,
                )

            if event_type == "response.output_item.added":
                item = getattr(event, "item", None)
                if getattr(item, "type", None) == "message":
                    item_id = getattr(item, "id", None)
                    phase = getattr(item, "phase", None)
                    if item_id and phase:
                        message_phases[str(item_id)] = str(phase)
            if event_type in {"response.output_text.delta", "response.refusal.delta"}:
                item_id = getattr(event, "item_id", None)
                if item_id and message_phases.get(str(item_id)) == "final_answer":
                    saw_visible_text = saw_visible_text or bool(getattr(event, "delta", None))
            if event_type in {"response.completed", "response.incomplete"}:
                saw_terminal_completion = True
            yield ProviderRawStreamChunk(
                provider="openai",
                raw_chunk=event,
                raw_event_type=event_type,
            )

        if not saw_terminal_completion:
            result_code = "openai_response_failed"
            raise OpenAIProviderError(
                "OpenAI stream ended without a terminal completion event.",
                result_code=result_code,
                result_message=get_openai_result_message(result_code),
            )

        if saw_terminal_completion and not saw_visible_text:
            raise OpenAIProviderError(
                build_openai_empty_output_detail(),
                result_code="openai_response_empty_output",
                result_message=get_openai_result_message("openai_response_empty_output"),
            )
    except OpenAIProviderError:
        raise
    except Exception as exc:
        logger.exception("OpenAI streaming request failed.")
        raise _map_openai_exception(exc) from exc
    finally:
        await client.close()


def map_prepared_openai_raw_stream_event(
    prepared_request: PreparedProviderChatRequest,
    raw_chunk: ProviderRawStreamChunk,
    *,
    state: OpenAIStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    return map_openai_stream_event(
        raw_chunk.raw_chunk,
        state=state,
        public_model_id=prepared_request.public_model_id,
        selected_tool_ids=_extract_selected_tool_ids(prepared_request.payload),
    )


def prepare_openai_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> dict[str, object]:
    model_runtime = resolve_openai_model_runtime(public_model_id=public_model_id)
    request_system_instruction, input_messages = map_chat_messages_to_openai_input(messages)
    return build_openai_responses_request(
        model=model_runtime.provider_model,
        request_system_instruction=request_system_instruction,
        input_messages=input_messages,
        selected_tool_ids=selected_tool_ids,
    )


def build_openai_prepared_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> PreparedProviderChatRequest:
    request_kwargs = prepare_openai_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=selected_tool_ids,
    )
    return PreparedProviderChatRequest(
        provider="openai",
        public_model_id=public_model_id,
        payload=request_kwargs,
        estimated_input_tokens=estimate_token_count_from_object(request_kwargs, base_tokens=96),
        input_token_count_payload=_build_openai_input_token_count_payload(request_kwargs),
    )


def _map_openai_exception(exc: Exception) -> OpenAIProviderError:
    if isinstance(exc, OpenAIToolConfigurationError):
        return OpenAIProviderError(str(exc))
    if isinstance(exc, ValueError):
        return OpenAIProviderError(str(exc))

    try:
        from openai import APIError, APIStatusError
    except ImportError:
        APIError = None
        APIStatusError = None

    if APIStatusError is not None and isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", None)
        error_code = getattr(exc, "code", None)
        message = getattr(exc, "message", None) or str(exc)
        result_code = _map_openai_http_result_code(status_code)
        return OpenAIProviderError(
            build_openai_status_error_detail(status_code=status_code, message=message),
            status_code=status_code,
            error_code=error_code,
            result_code=result_code,
            result_message=get_openai_result_message(result_code),
        )

    if APIError is not None and isinstance(exc, APIError):
        error_code = getattr(exc, "code", None)
        message = getattr(exc, "message", None) or str(exc)
        result_code = "openai_provider_failed"
        return OpenAIProviderError(
            build_openai_status_error_detail(status_code=None, message=message),
            error_code=error_code,
            result_code=result_code,
            result_message=get_openai_result_message(result_code),
        )

    result_code = "openai_provider_failed"
    return OpenAIProviderError(
        build_openai_status_error_detail(status_code=None, message=None),
        result_code=result_code,
        result_message=get_openai_result_message(result_code),
    )


def extract_openai_stream_error(event) -> _OpenAIStreamFailure | None:
    event_type = getattr(event, "type", None)
    if event_type == "error":
        message = getattr(event, "message", None)
        result_code = "openai_response_failed"
        return _OpenAIStreamFailure(
            result_code=result_code,
            result_message=get_openai_result_message(result_code),
            detail=build_openai_status_error_detail(status_code=None, message=message),
        )

    if event_type == "response.failed":
        response = getattr(event, "response", None)
        error = getattr(response, "error", None)
        message = getattr(error, "message", None) if error is not None else None
        error_code = getattr(error, "code", None) if error is not None else None
        result_code = "openai_response_failed"
        return _OpenAIStreamFailure(
            result_code=result_code,
            result_message=get_openai_result_message(result_code),
            detail=build_openai_failed_detail(error_code=error_code, message=message),
            error_code=error_code,
        )

    return None


def _build_openai_input_token_count_payload(request_kwargs: dict[str, object]) -> dict[str, object]:
    supported_keys = {
        "conversation",
        "input",
        "instructions",
        "model",
        "parallel_tool_calls",
        "previous_response_id",
        "reasoning",
        "text",
        "tool_choice",
        "tools",
        "truncation",
    }
    return {
        key: value
        for key, value in request_kwargs.items()
        if key in supported_keys
    }


def _extract_selected_tool_ids(payload: dict[str, object]) -> tuple[str, ...]:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return ()

    selected_tool_ids: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_type = str(tool.get("type") or "").strip()
        if tool_type == "file_search":
            selected_tool_ids.append("file_search")
        elif tool_type == "code_interpreter":
            selected_tool_ids.append("code_interpreter")
        elif tool_type == "web_search":
            selected_tool_ids.append("web_search")
        elif tool_type == "shell":
            selected_tool_ids.append("shell")
    return tuple(selected_tool_ids)


def _map_openai_http_result_code(status_code: int | None) -> str:
    if status_code == 429:
        return "openai_provider_rate_limited"
    if status_code in {401, 403}:
        return "openai_provider_auth_failed"
    if status_code is not None and 400 <= status_code < 500:
        return "openai_provider_bad_request"
    if status_code is not None and status_code >= 500:
        return "openai_provider_unavailable"
    return "openai_provider_failed"
