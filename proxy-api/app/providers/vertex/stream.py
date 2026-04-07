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

from app.providers.vertex.client import build_vertex_ai_client
from app.providers.vertex.mapper import map_chat_messages_to_vertex_contents, map_vertex_stream_chunk
from app.providers.vertex.tools import VertexToolConfigurationError, build_vertex_tools
from app.schemas.chat import ChatMessage

logger = logging.getLogger("uvicorn.error")


class VertexProviderError(RuntimeError):
    """Raised when a Vertex AI request fails while streaming."""


async def stream_vertex_chat_completion(
    *,
    model_name: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> AsyncIterator:
    client = build_vertex_ai_client()

    try:
        from google.genai import types

        system_instruction, contents = map_chat_messages_to_vertex_contents(messages)
        config = _build_generate_content_config(
            types=types,
            system_instruction=system_instruction,
            selected_tool_ids=selected_tool_ids,
        )

        async with client.aio as aio_client:
            stream = await aio_client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                yield map_vertex_stream_chunk(chunk)
    except Exception as exc:
        logger.exception("Vertex AI streaming request failed.")
        raise _map_vertex_exception(exc) from exc
    finally:
        client.close()


def _map_vertex_exception(exc: Exception) -> VertexProviderError:
    if isinstance(exc, VertexToolConfigurationError):
        return VertexProviderError(str(exc))

    try:
        from google.genai import errors
    except ImportError:
        errors = None
    else:
        if isinstance(exc, errors.APIError):
            detail = _format_vertex_api_error(exc)
            return VertexProviderError(detail)

    return VertexProviderError("vertex ai request failed")


def _build_generate_content_config(*, types, system_instruction: str | None, selected_tool_ids: Iterable[str]):
    config_kwargs: dict[str, object] = {}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    configured_tools = build_vertex_tools(
        selected_tool_ids=selected_tool_ids,
        types_module=types,
    )
    if configured_tools:
        config_kwargs["tools"] = configured_tools

    if not config_kwargs:
        return None

    return types.GenerateContentConfig(**config_kwargs)


def _format_vertex_api_error(exc) -> str:
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    message = getattr(exc, "message", None)

    status_text = f" {status}" if status else ""
    message_text = f": {message}" if message else ""
    code_text = str(code) if code is not None else "unknown"
    return f"vertex ai request failed ({code_text}{status_text}){message_text}"
