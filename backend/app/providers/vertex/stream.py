"""
Purpose:
- Execute streamed Vertex AI text generation requests.

Responsibilities:
- Call the Google Gen AI async streaming API
- Translate provider chunks into normalized internal stream chunks
- Surface provider failures as controlled exceptions
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass

from app.providers.vertex.client import build_vertex_client
from app.providers.vertex.config import build_vertex_generate_content_config
from app.providers.vertex.models import resolve_vertex_model_runtime
from app.providers.vertex.mapper import (
    VertexStreamState,
    map_chat_messages_to_vertex_contents,
    map_vertex_stream_chunk,
)
from app.providers.vertex.count_tokens import VertexCountTokensPayload
from app.providers.vertex.outcomes import (
    build_vertex_empty_output_detail,
    build_vertex_prompt_block_detail,
    build_vertex_status_error_detail,
    get_vertex_result_message,
)
from app.providers.types import (
    ProviderRawStreamChunk,
    ProviderStreamEvent,
)
from app.providers.token_estimation import estimate_token_count_from_object
from app.providers.types import PreparedProviderChatRequest
from app.providers.vertex.tools import VertexToolConfigurationError
from app.schemas.chat import ChatMessage

logger = logging.getLogger("uvicorn.error")


class VertexProviderError(RuntimeError):
    """Raised when a Vertex AI request fails while streaming."""

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
class _VertexStreamFailure:
    result_code: str
    result_message: str
    detail: str
    status_code: int | None = None
    error_code: str | None = None


async def stream_vertex_chat_completion(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> AsyncIterator[ProviderStreamEvent]:
    prepared_request = build_vertex_prepared_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=selected_tool_ids,
    )
    async for chunk in stream_prepared_vertex_chat_completion(prepared_request):
        yield chunk


async def stream_prepared_vertex_chat_completion(
    prepared_request: PreparedProviderChatRequest,
) -> AsyncIterator[ProviderStreamEvent]:
    state = VertexStreamState()
    async for raw_chunk in stream_prepared_vertex_raw_chat_completion(prepared_request):
        for stream_event in map_prepared_vertex_raw_stream_event(
            prepared_request,
            raw_chunk,
            state=state,
        ):
            yield stream_event


async def stream_prepared_vertex_raw_chat_completion(
    prepared_request: PreparedProviderChatRequest,
) -> AsyncIterator[ProviderRawStreamChunk]:
    saw_visible_text = False
    saw_terminal_finish_reason = False
    last_finish_reason: str | None = None

    try:
        payload = prepared_request.payload
        if not isinstance(payload, dict):
            raise VertexProviderError("vertex prepared payload must be a dict")

        location = str(payload["location"])
        config = payload["config"]
        client = build_vertex_client(location=location)

        async with client.aio as aio_client:
            stream = await aio_client.models.generate_content_stream(
                model=str(payload["provider_model"]),
                contents=payload["contents"],
                config=config,
            )
            async for chunk in stream:
                failure = extract_vertex_stream_error(chunk)
                if failure:
                    raise VertexProviderError(
                        failure.detail,
                        status_code=failure.status_code,
                        error_code=failure.error_code,
                        result_code=failure.result_code,
                        result_message=failure.result_message,
                    )

                if _vertex_chunk_has_visible_answer_text(chunk):
                    saw_visible_text = True
                finish_reason = _extract_vertex_finish_reason(chunk)
                if finish_reason is not None:
                    saw_terminal_finish_reason = True
                    last_finish_reason = finish_reason
                yield ProviderRawStreamChunk(
                    provider="vertex_ai",
                    raw_chunk=chunk,
                    raw_event_type=type(chunk).__name__,
                )

        if not saw_terminal_finish_reason:
            result_code = "vertex_stream_error"
            raise VertexProviderError(
                "Gemini stream ended without a terminal finishReason.",
                result_code=result_code,
                result_message=get_vertex_result_message(result_code),
            )

        if not saw_visible_text:
            result_code = "vertex_empty_output"
            raise VertexProviderError(
                build_vertex_empty_output_detail(finish_reason=last_finish_reason),
                result_code=result_code,
                result_message=get_vertex_result_message(result_code),
            )
    except VertexProviderError:
        raise
    except Exception as exc:
        logger.exception("Vertex AI streaming request failed.")
        raise _map_vertex_exception(exc) from exc
    finally:
        if "client" in locals():
            client.close()


def map_prepared_vertex_raw_stream_event(
    prepared_request: PreparedProviderChatRequest,
    raw_chunk: ProviderRawStreamChunk,
    *,
    state: VertexStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    payload = prepared_request.payload
    if not isinstance(payload, dict):
        raise VertexProviderError("vertex prepared payload must be a dict")
    return map_vertex_stream_chunk(
        raw_chunk.raw_chunk,
        state=state,
        public_model_id=prepared_request.public_model_id,
        selected_tool_ids=_extract_selected_tool_ids(payload["config"]),
    )


def prepare_vertex_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
):
    from google.genai import types

    model_runtime = resolve_vertex_model_runtime(public_model_id=public_model_id)
    request_system_instruction, contents = map_chat_messages_to_vertex_contents(messages)
    config = build_vertex_generate_content_config(
        types=types,
        model=model_runtime.public_id,
        request_system_instruction=request_system_instruction,
        selected_tool_ids=selected_tool_ids,
    )
    count_config = types.CountTokensConfig(
        system_instruction=getattr(config, "system_instruction", None),
        tools=getattr(config, "tools", None),
        generation_config=types.GenerationConfig(
            max_output_tokens=getattr(config, "max_output_tokens", None),
            thinking_config=getattr(config, "thinking_config", None),
        ),
    )
    return model_runtime, contents, config, count_config


def build_vertex_prepared_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> PreparedProviderChatRequest:
    model_runtime, contents, config, count_config = prepare_vertex_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=selected_tool_ids,
    )
    estimate_source = {
        "model": model_runtime.provider_model,
        "location": model_runtime.location,
        "contents": contents,
        "config": repr(config),
    }
    return PreparedProviderChatRequest(
        provider="vertex_ai",
        public_model_id=public_model_id,
        payload={
            "provider_model": model_runtime.provider_model,
            "location": model_runtime.location,
            "contents": contents,
            "config": config,
            "count_config": count_config,
            "estimate_source": estimate_source,
        },
        estimated_input_tokens=estimate_token_count_from_object(estimate_source, base_tokens=96),
        input_token_count_payload=VertexCountTokensPayload(
            provider_model=model_runtime.provider_model,
            location=model_runtime.location,
            contents=contents,
            config=count_config,
        ),
    )


def _map_vertex_exception(exc: Exception) -> VertexProviderError:
    if isinstance(exc, VertexToolConfigurationError):
        return VertexProviderError(str(exc))
    if isinstance(exc, ValueError):
        return VertexProviderError(str(exc))

    try:
        from google.genai import errors
    except ImportError:
        errors = None
    else:
        if isinstance(exc, errors.APIError):
            detail = _format_vertex_api_error(exc)
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            result_code = _map_vertex_http_result_code(code if isinstance(code, int) else None)
            return VertexProviderError(
                build_vertex_status_error_detail(status_code=code if isinstance(code, int) else None, message=detail),
                status_code=code if isinstance(code, int) else None,
                error_code=str(status) if status else None,
                result_code=result_code,
                result_message=get_vertex_result_message(result_code),
            )

    result_code = "vertex_provider_failed"
    return VertexProviderError(
        build_vertex_status_error_detail(status_code=None, message=None),
        result_code=result_code,
        result_message=get_vertex_result_message(result_code),
    )


def _format_vertex_api_error(exc) -> str:
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    message = getattr(exc, "message", None)

    status_text = f" {status}" if status else ""
    message_text = f": {message}" if message else ""
    code_text = str(code) if code is not None else "unknown"
    return f"vertex ai request failed ({code_text}{status_text}){message_text}"


def extract_vertex_stream_error(chunk) -> _VertexStreamFailure | None:
    prompt_feedback = getattr(chunk, "prompt_feedback", None)
    if prompt_feedback is None:
        return None

    block_reason = getattr(prompt_feedback, "block_reason", None)
    block_reason_name = getattr(block_reason, "name", None) or str(block_reason) if block_reason is not None else None
    block_message = getattr(prompt_feedback, "block_reason_message", None)
    result_code = "vertex_prompt_blocked"
    return _VertexStreamFailure(
        result_code=result_code,
        result_message=get_vertex_result_message(result_code),
        detail=build_vertex_prompt_block_detail(block_reason=block_reason_name, block_message=block_message),
        error_code=block_reason_name,
    )


def _extract_vertex_finish_reason(chunk) -> str | None:
    candidates = getattr(chunk, "candidates", None) or []
    for candidate in candidates:
        finish_reason_value = getattr(candidate, "finish_reason", None)
        if finish_reason_value is not None:
            return getattr(finish_reason_value, "name", None) or str(finish_reason_value)
    return None


def _vertex_chunk_has_visible_answer_text(chunk) -> bool:
    for candidate in getattr(chunk, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", None) is not True and bool(getattr(part, "text", None)):
                return True
    return False


def _map_vertex_http_result_code(status_code: int | None) -> str:
    if status_code == 429:
        return "vertex_provider_rate_limited"
    if status_code is not None and 400 <= status_code < 500:
        return "vertex_provider_bad_request"
    if status_code is not None and status_code >= 500:
        return "vertex_provider_unavailable"
    return "vertex_provider_failed"


def _extract_selected_tool_ids(config: object) -> tuple[str, ...]:
    tools = getattr(config, "tools", None)
    if not tools:
        return ()

    selected_tool_ids: list[str] = []
    for tool in tools:
        if getattr(tool, "google_search", None) is not None:
            selected_tool_ids.append("google_search")
        if getattr(tool, "retrieval", None) is not None:
            selected_tool_ids.append("retrieval")
        if getattr(tool, "code_execution", None) is not None:
            selected_tool_ids.append("code_execution")
        if getattr(tool, "url_context", None) is not None:
            selected_tool_ids.append("url_context")
        if getattr(tool, "google_maps", None) is not None:
            selected_tool_ids.append("google_maps")
    return tuple(selected_tool_ids)
