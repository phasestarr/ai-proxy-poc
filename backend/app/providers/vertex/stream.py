"""Vertex AI streaming transport and SDK error normalization."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.providers.types import PreparedProviderChatRequest, ProviderRawStreamChunk
from app.providers.vertex.client import build_vertex_client
from app.providers.vertex.outcomes import (
    build_vertex_prompt_block_detail,
    build_vertex_status_error_detail,
    get_vertex_result_message,
)

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


async def stream_prepared_vertex_raw_chat_completion(
    prepared_request: PreparedProviderChatRequest,
) -> AsyncIterator[ProviderRawStreamChunk]:
    try:
        payload = prepared_request.payload
        if not isinstance(payload, dict):
            raise VertexProviderError("vertex prepared payload must be a dict")
        location = str(payload["location"])
        client = build_vertex_client(location=location)
        async with client.aio as aio_client:
            stream = await aio_client.models.generate_content_stream(
                model=str(payload["provider_model"]),
                contents=payload["contents"],
                config=payload["config"],
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
                yield ProviderRawStreamChunk(
                    provider="vertex_ai",
                    raw_chunk=chunk,
                    raw_event_type=type(chunk).__name__,
                )
    except VertexProviderError:
        raise
    except Exception as exc:
        logger.exception("Vertex AI streaming request failed.")
        raise _map_vertex_exception(exc) from exc
    finally:
        if "client" in locals():
            client.close()


def _map_vertex_exception(exc: Exception) -> VertexProviderError:
    try:
        from google.genai import errors
    except ImportError:
        errors = None
    if errors is not None and isinstance(exc, errors.APIError):
        detail = _format_vertex_api_error(exc)
        code = getattr(exc, "code", None)
        status = getattr(exc, "status", None)
        status_code = code if isinstance(code, int) else None
        result_code = _map_vertex_http_result_code(status_code)
        return VertexProviderError(
            build_vertex_status_error_detail(status_code=status_code, message=detail),
            status_code=status_code,
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


def _map_vertex_http_result_code(status_code: int | None) -> str:
    if status_code == 429:
        return "vertex_provider_rate_limited"
    if status_code is not None and 400 <= status_code < 500:
        return "vertex_provider_bad_request"
    if status_code is not None and status_code >= 500:
        return "vertex_provider_unavailable"
    return "vertex_provider_failed"
