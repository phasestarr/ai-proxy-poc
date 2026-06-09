from __future__ import annotations

import logging

from app.compression.types import CompressionResult, ContextCompressionError
from app.compression.vertex.client import CompressionVertexConfigurationError, build_compression_vertex_client
from app.compression.vertex.config import (
    COMPRESSION_VERTEX_LOCATION,
    COMPRESSION_VERTEX_MODEL,
    build_compression_generate_content_config,
)
from app.compression.vertex.mapper import map_compression_usage

logger = logging.getLogger("uvicorn.error")


async def compress_with_vertex_flash(
    *,
    system_instruction: str,
    user_prompt: str,
) -> CompressionResult:
    from google.genai import types

    client = build_compression_vertex_client(location=COMPRESSION_VERTEX_LOCATION)
    config = build_compression_generate_content_config(
        types=types,
        system_instruction=system_instruction,
    )
    contents = [
        {
            "role": "user",
            "parts": [{"text": user_prompt}],
        }
    ]

    try:
        async with client.aio as aio_client:
            response = await aio_client.models.generate_content(
                model=COMPRESSION_VERTEX_MODEL,
                contents=contents,
                config=config,
            )
    except CompressionVertexConfigurationError as exc:
        raise ContextCompressionError(str(exc)) from exc
    except Exception as exc:
        logger.exception("Context compression request failed.")
        raise ContextCompressionError("vertex context compression failed") from exc
    finally:
        client.close()

    summary_text = (getattr(response, "text", None) or "").strip()
    if not summary_text:
        raise ContextCompressionError("vertex context compression returned empty output")

    return CompressionResult(
        summary_text=summary_text,
        usage=map_compression_usage(response),
    )
