"""
Purpose:
- Execute streamed Anthropic Messages API requests.

Responsibilities:
- Call the Anthropic async streaming API
- Translate provider events into normalized internal stream chunks
- Surface provider failures as controlled exceptions
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass

from app.providers.anthropic.client import build_anthropic_client
from app.providers.anthropic.config import build_anthropic_messages_request
from app.providers.anthropic.mapper import (
    map_anthropic_stream_event,
    map_chat_messages_to_anthropic_messages,
)
from app.providers.anthropic.models import resolve_anthropic_model_runtime
from app.providers.anthropic.outcomes import (
    build_anthropic_empty_output_detail,
    build_anthropic_status_error_detail,
    build_anthropic_stop_detail,
    build_anthropic_stream_error_detail,
    get_anthropic_result_message,
)
from app.providers.anthropic.tools import AnthropicToolConfigurationError, build_anthropic_beta_headers
from app.providers.token_estimation import estimate_token_count_from_object
from app.providers.types import (
    PreparedProviderChatRequest,
    ProviderFunctionDeclaration,
    ProviderStreamChunk,
)
from app.schemas.chat import ChatMessage

logger = logging.getLogger("uvicorn.error")


class AnthropicProviderError(RuntimeError):
    """Raised when an Anthropic request fails while streaming."""

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
class _AnthropicStreamFailure:
    result_code: str
    result_message: str
    detail: str
    status_code: int | None = None
    error_code: str | None = None


async def stream_anthropic_chat_completion(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> AsyncIterator:
    prepared_request = build_anthropic_prepared_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=selected_tool_ids,
        function_declarations=function_declarations,
    )
    async for chunk in stream_prepared_anthropic_chat_completion(prepared_request):
        yield chunk


async def stream_prepared_anthropic_chat_completion(
    prepared_request: PreparedProviderChatRequest,
) -> AsyncIterator:
    client = build_anthropic_client()
    saw_visible_text = False
    saw_terminal_stop_reason = False
    last_stop_reason: str | None = None

    try:
        stream = await client.beta.messages.create(
            **prepared_request.payload,
            stream=True,
        )
        async for event in stream:
            failure = extract_anthropic_stream_error(event)
            if failure:
                raise AnthropicProviderError(
                    failure.detail,
                    status_code=failure.status_code,
                    error_code=failure.error_code,
                    result_code=failure.result_code,
                    result_message=failure.result_message,
                )

            chunk = map_anthropic_stream_event(
                event,
                public_model_id=prepared_request.public_model_id,
                selected_tool_ids=_extract_selected_tool_ids(prepared_request.payload),
            )
            if chunk is not None:
                if chunk.text:
                    saw_visible_text = True
                if chunk.finish_reason is not None:
                    saw_terminal_stop_reason = True
                    last_stop_reason = chunk.finish_reason
                yield chunk

        if not saw_terminal_stop_reason:
            result_code = "anthropic_stream_error"
            raise AnthropicProviderError(
                "Claude stream ended without a terminal stop_reason.",
                result_code=result_code,
                result_message=get_anthropic_result_message(result_code),
            )

        terminal_failure = _map_anthropic_terminal_failure(last_stop_reason)
        if terminal_failure is not None:
            raise AnthropicProviderError(
                terminal_failure.detail,
                result_code=terminal_failure.result_code,
                result_message=terminal_failure.result_message,
            )

        if not saw_visible_text:
            result_code = "anthropic_empty_output"
            raise AnthropicProviderError(
                build_anthropic_empty_output_detail(stop_reason=last_stop_reason),
                result_code=result_code,
                result_message=get_anthropic_result_message(result_code),
            )
    except AnthropicProviderError:
        raise
    except Exception as exc:
        logger.exception("Anthropic streaming request failed.")
        raise _map_anthropic_exception(exc) from exc
    finally:
        await client.close()


def prepare_anthropic_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> dict[str, object]:
    model_runtime = resolve_anthropic_model_runtime(public_model_id=public_model_id)
    request_system_instruction, anthropic_messages = map_chat_messages_to_anthropic_messages(messages)
    request_kwargs = build_anthropic_messages_request(
        model=model_runtime.provider_model,
        request_system_instruction=request_system_instruction,
        messages=anthropic_messages,
        selected_tool_ids=selected_tool_ids,
        function_declarations=function_declarations,
    )
    beta_headers = build_anthropic_beta_headers(selected_tool_ids=selected_tool_ids)
    existing_betas = [
        str(item).strip()
        for item in (request_kwargs.get("betas") or [])
        if str(item).strip()
    ]
    merged_betas = list(dict.fromkeys([*existing_betas, *beta_headers]))
    if merged_betas:
        request_kwargs["betas"] = merged_betas
    return request_kwargs


def build_anthropic_prepared_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> PreparedProviderChatRequest:
    request_kwargs = prepare_anthropic_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=selected_tool_ids,
        function_declarations=function_declarations,
    )
    return PreparedProviderChatRequest(
        provider="anthropic",
        public_model_id=public_model_id,
        payload=request_kwargs,
        estimated_input_tokens=estimate_token_count_from_object(request_kwargs, base_tokens=96),
        input_token_count_payload=_build_anthropic_input_token_count_payload(request_kwargs),
    )


def _map_anthropic_exception(exc: Exception) -> AnthropicProviderError:
    if isinstance(exc, AnthropicToolConfigurationError):
        return AnthropicProviderError(str(exc))
    if isinstance(exc, ValueError):
        return AnthropicProviderError(str(exc))

    try:
        from anthropic import APIError, APIStatusError
    except ImportError:
        APIError = None
        APIStatusError = None

    if APIStatusError is not None and isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", None)
        error_code = getattr(exc, "code", None)
        message = getattr(exc, "message", None) or str(exc)
        result_code = _map_anthropic_http_result_code(status_code)
        return AnthropicProviderError(
            build_anthropic_status_error_detail(status_code=status_code, message=message),
            status_code=status_code,
            error_code=error_code,
            result_code=result_code,
            result_message=get_anthropic_result_message(result_code),
        )

    if APIError is not None and isinstance(exc, APIError):
        error_code = getattr(exc, "code", None)
        message = getattr(exc, "message", None) or str(exc)
        result_code = "anthropic_provider_failed"
        return AnthropicProviderError(
            build_anthropic_status_error_detail(status_code=None, message=message),
            error_code=error_code,
            result_code=result_code,
            result_message=get_anthropic_result_message(result_code),
        )

    result_code = "anthropic_provider_failed"
    return AnthropicProviderError(
        build_anthropic_status_error_detail(status_code=None, message=None),
        result_code=result_code,
        result_message=get_anthropic_result_message(result_code),
    )


def extract_anthropic_stream_error(event) -> _AnthropicStreamFailure | None:
    event_type = getattr(event, "type", None)
    if event_type != "error":
        return None

    error = getattr(event, "error", None)
    message = getattr(error, "message", None) if error is not None else None
    error_type = getattr(error, "type", None) if error is not None else None
    result_code = "anthropic_stream_error"
    return _AnthropicStreamFailure(
        result_code=result_code,
        result_message=get_anthropic_result_message(result_code),
        detail=build_anthropic_stream_error_detail(error_type=error_type, message=message),
        error_code=error_type,
    )


def _map_anthropic_terminal_failure(stop_reason: str | None) -> _AnthropicStreamFailure | None:
    if stop_reason in {None, "end_turn", "stop_sequence"}:
        return None

    result_code_by_stop_reason = {
        "max_tokens": "anthropic_stop_max_tokens",
        "tool_use": "anthropic_stop_tool_use",
        "pause_turn": "anthropic_stop_pause_turn",
        "refusal": "anthropic_stop_refusal",
        "model_context_window_exceeded": "anthropic_stop_model_context_window_exceeded",
    }
    result_code = result_code_by_stop_reason.get(stop_reason, "anthropic_stream_error")
    return _AnthropicStreamFailure(
        result_code=result_code,
        result_message=get_anthropic_result_message(result_code),
        detail=build_anthropic_stop_detail(stop_reason=stop_reason),
    )


def _map_anthropic_http_result_code(status_code: int | None) -> str:
    if status_code == 429:
        return "anthropic_provider_rate_limited"
    if status_code in {401, 403}:
        return "anthropic_provider_auth_failed"
    if status_code is not None and 400 <= status_code < 500:
        return "anthropic_provider_bad_request"
    if status_code is not None and status_code >= 500:
        return "anthropic_provider_unavailable"
    return "anthropic_provider_failed"


def _build_anthropic_input_token_count_payload(request_kwargs: dict[str, object]) -> dict[str, object]:
    supported_keys = {
        "messages",
        "model",
        "output_config",
        "system",
        "thinking",
        "tool_choice",
        "tools",
        "betas",
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
        tool_name = str(tool.get("name") or "").strip()
        tool_type = str(tool.get("type") or "").strip()
        if tool_name == "web_search" or tool_type.startswith("web_search"):
            selected_tool_ids.append("web_search")
        elif tool_name == "code_execution" or tool_type.startswith("code_execution"):
            selected_tool_ids.append("code_execution")
    return tuple(selected_tool_ids)
