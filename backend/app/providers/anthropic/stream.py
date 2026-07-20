"""Anthropic Messages API streaming transport and SDK error normalization."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.providers.anthropic.client import build_anthropic_client
from app.providers.anthropic.outcomes import (
    build_anthropic_status_error_detail,
    build_anthropic_stream_error_detail,
    get_anthropic_result_message,
)
from app.providers.types import PreparedProviderChatRequest, ProviderRawStreamChunk

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


async def stream_prepared_anthropic_raw_chat_completion(
    prepared_request: PreparedProviderChatRequest,
) -> AsyncIterator[ProviderRawStreamChunk]:
    client = build_anthropic_client()
    try:
        stream = await client.beta.messages.create(**prepared_request.payload, stream=True)
        async for event in stream:
            event_type = getattr(event, "type", None)
            failure = extract_anthropic_stream_error(event)
            if failure:
                raise AnthropicProviderError(
                    failure.detail,
                    status_code=failure.status_code,
                    error_code=failure.error_code,
                    result_code=failure.result_code,
                    result_message=failure.result_message,
                )
            yield ProviderRawStreamChunk(
                provider="anthropic",
                raw_chunk=event,
                raw_event_type=event_type,
            )
    except AnthropicProviderError:
        raise
    except Exception as exc:
        logger.exception("Anthropic streaming request failed.")
        raise _map_anthropic_exception(exc) from exc
    finally:
        await client.close()


def _map_anthropic_exception(exc: Exception) -> AnthropicProviderError:
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
