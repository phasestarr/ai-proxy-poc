"""OpenAI Responses API streaming transport and SDK error normalization."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.providers.openai.client import build_openai_client
from app.providers.openai.outcomes import (
    build_openai_failed_detail,
    build_openai_status_error_detail,
    get_openai_result_message,
)
from app.providers.types import PreparedProviderChatRequest, ProviderRawStreamChunk

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


async def stream_prepared_openai_raw_chat_completion(
    prepared_request: PreparedProviderChatRequest,
) -> AsyncIterator[ProviderRawStreamChunk]:
    client = build_openai_client()
    try:
        stream = await client.responses.create(**prepared_request.payload, stream=True)
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
            yield ProviderRawStreamChunk(
                provider="openai",
                raw_chunk=event,
                raw_event_type=event_type,
            )
    except OpenAIProviderError:
        raise
    except Exception as exc:
        logger.exception("OpenAI streaming request failed.")
        raise _map_openai_exception(exc) from exc
    finally:
        await client.close()


def _map_openai_exception(exc: Exception) -> OpenAIProviderError:
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
