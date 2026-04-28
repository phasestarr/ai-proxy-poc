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
from app.providers.vertex.mapper import map_chat_messages_to_vertex_contents, map_vertex_stream_chunk
from app.providers.vertex.outcomes import (
    build_vertex_empty_output_detail,
    build_vertex_finish_detail,
    build_vertex_prompt_block_detail,
    build_vertex_status_error_detail,
    get_vertex_result_message,
)
from app.providers.types import ProviderFunctionDeclaration, ProviderStreamChunk
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
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> AsyncIterator:
    saw_visible_text = False
    saw_terminal_finish_reason = False
    last_finish_reason: str | None = None

    try:
        model_runtime, contents, config = prepare_vertex_chat_completion_request(
            public_model_id=public_model_id,
            messages=messages,
            selected_tool_ids=selected_tool_ids,
            function_declarations=function_declarations,
        )
        client = build_vertex_client(location=model_runtime.location)

        async with client.aio as aio_client:
            stream = await aio_client.models.generate_content_stream(
                model=model_runtime.provider_model,
                contents=contents,
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

                mapped_chunk = map_vertex_stream_chunk(chunk)
                if mapped_chunk.text:
                    saw_visible_text = True
                if mapped_chunk.finish_reason is not None:
                    saw_terminal_finish_reason = True
                    last_finish_reason = mapped_chunk.finish_reason
                yield mapped_chunk

        if not saw_terminal_finish_reason:
            result_code = "vertex_stream_error"
            raise VertexProviderError(
                "Gemini stream ended without a terminal finishReason.",
                result_code=result_code,
                result_message=get_vertex_result_message(result_code),
            )

        terminal_failure = _map_vertex_terminal_failure(last_finish_reason)
        if terminal_failure is not None:
            raise VertexProviderError(
                terminal_failure.detail,
                result_code=terminal_failure.result_code,
                result_message=terminal_failure.result_message,
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


def prepare_vertex_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
):
    from google.genai import types

    model_runtime = resolve_vertex_model_runtime(public_model_id=public_model_id)
    request_system_instruction, contents = map_chat_messages_to_vertex_contents(messages)
    config = build_vertex_generate_content_config(
        types=types,
        model=model_runtime.public_id,
        request_system_instruction=request_system_instruction,
        selected_tool_ids=selected_tool_ids,
        function_declarations=function_declarations,
    )
    return model_runtime, contents, config


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


def _map_vertex_terminal_failure(finish_reason: str | None) -> _VertexStreamFailure | None:
    if finish_reason in {None, "STOP"}:
        return None

    result_code_by_finish_reason = {
        "MAX_TOKENS": "vertex_finish_max_tokens",
        "SAFETY": "vertex_finish_safety",
        "RECITATION": "vertex_finish_recitation",
        "OTHER": "vertex_finish_other",
        "BLOCKLIST": "vertex_finish_blocklist",
        "PROHIBITED_CONTENT": "vertex_finish_prohibited_content",
        "SPII": "vertex_finish_spii",
        "MALFORMED_FUNCTION_CALL": "vertex_finish_malformed_function_call",
        "MODEL_ARMOR": "vertex_finish_model_armor",
        "IMAGE_SAFETY": "vertex_finish_image_safety",
        "IMAGE_PROHIBITED_CONTENT": "vertex_finish_image_prohibited_content",
        "IMAGE_RECITATION": "vertex_finish_image_recitation",
        "IMAGE_OTHER": "vertex_finish_image_other",
        "UNEXPECTED_TOOL_CALL": "vertex_finish_unexpected_tool_call",
        "NO_IMAGE": "vertex_finish_no_image",
    }
    result_code = result_code_by_finish_reason.get(finish_reason, "vertex_stream_error")
    return _VertexStreamFailure(
        result_code=result_code,
        result_message=get_vertex_result_message(result_code),
        detail=build_vertex_finish_detail(finish_reason=finish_reason),
    )


def _map_vertex_http_result_code(status_code: int | None) -> str:
    if status_code == 429:
        return "vertex_provider_rate_limited"
    if status_code is not None and 400 <= status_code < 500:
        return "vertex_provider_bad_request"
    if status_code is not None and status_code >= 500:
        return "vertex_provider_unavailable"
    return "vertex_provider_failed"
