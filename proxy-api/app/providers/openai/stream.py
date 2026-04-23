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

from app.providers.openai.client import build_openai_client
from app.providers.openai.config import build_openai_responses_request
from app.providers.openai.mapper import (
    extract_openai_stream_error,
    map_chat_messages_to_openai_input,
    map_openai_stream_event,
)
from app.providers.openai.models import resolve_openai_model_runtime
from app.providers.openai.tools import OpenAIToolConfigurationError
from app.providers.types import ProviderFunctionDeclaration
from app.schemas.chat import ChatMessage

logger = logging.getLogger("uvicorn.error")


class OpenAIProviderError(RuntimeError):
    """Raised when an OpenAI request fails while streaming."""


async def stream_openai_chat_completion(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> AsyncIterator:
    model_runtime = resolve_openai_model_runtime(public_model_id=public_model_id)
    client = build_openai_client()

    try:
        request_system_instruction, input_messages = map_chat_messages_to_openai_input(messages)
        request_kwargs = build_openai_responses_request(
            model=model_runtime.provider_model,
            request_system_instruction=request_system_instruction,
            input_messages=input_messages,
            selected_tool_ids=selected_tool_ids,
            function_declarations=function_declarations,
        )

        stream = await client.responses.create(
            **request_kwargs,
            stream=True,
        )
        async for event in stream:
            error_detail = extract_openai_stream_error(event)
            if error_detail:
                raise OpenAIProviderError(error_detail)

            chunk = map_openai_stream_event(event)
            if chunk is not None:
                yield chunk
    except OpenAIProviderError:
        raise
    except Exception as exc:
        logger.exception("OpenAI streaming request failed.")
        raise _map_openai_exception(exc) from exc
    finally:
        await client.close()


def _map_openai_exception(exc: Exception) -> OpenAIProviderError:
    if isinstance(exc, OpenAIToolConfigurationError):
        return OpenAIProviderError(str(exc))

    try:
        from openai import APIError, APIStatusError
    except ImportError:
        APIError = None
        APIStatusError = None

    if APIStatusError is not None and isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", None)
        message = getattr(exc, "message", None) or str(exc)
        return OpenAIProviderError(f"openai request failed ({status_code}): {message}")

    if APIError is not None and isinstance(exc, APIError):
        message = getattr(exc, "message", None) or str(exc)
        return OpenAIProviderError(f"openai request failed: {message}")

    return OpenAIProviderError("openai request failed")

