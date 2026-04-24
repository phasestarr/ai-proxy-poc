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

from app.providers.anthropic.client import build_anthropic_client
from app.providers.anthropic.config import build_anthropic_messages_request
from app.providers.anthropic.mapper import (
    extract_anthropic_stream_error,
    map_anthropic_stream_event,
    map_chat_messages_to_anthropic_messages,
)
from app.providers.anthropic.models import resolve_anthropic_model_runtime
from app.providers.anthropic.tools import AnthropicToolConfigurationError, build_anthropic_beta_headers
from app.providers.types import ProviderFunctionDeclaration
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
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


async def stream_anthropic_chat_completion(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> AsyncIterator:
    model_runtime = resolve_anthropic_model_runtime(public_model_id=public_model_id)
    client = build_anthropic_client()

    try:
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

        stream = await client.beta.messages.create(
            **request_kwargs,
            stream=True,
        )
        async for event in stream:
            error_detail = extract_anthropic_stream_error(event)
            if error_detail:
                raise AnthropicProviderError(error_detail)

            chunk = map_anthropic_stream_event(event)
            if chunk is not None:
                yield chunk
    except AnthropicProviderError:
        raise
    except Exception as exc:
        logger.exception("Anthropic streaming request failed.")
        raise _map_anthropic_exception(exc) from exc
    finally:
        await client.close()


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
        return AnthropicProviderError(
            f"anthropic request failed ({status_code}): {message}",
            status_code=status_code,
            error_code=error_code,
        )

    if APIError is not None and isinstance(exc, APIError):
        error_code = getattr(exc, "code", None)
        message = getattr(exc, "message", None) or str(exc)
        return AnthropicProviderError(f"anthropic request failed: {message}", error_code=error_code)

    return AnthropicProviderError("anthropic request failed")
