from __future__ import annotations

from app.compression.prompts import COMPRESSION_SYSTEM_INSTRUCTION, build_compression_user_prompt
from app.compression.types import CompressionResult, ContextCompressionError
from app.compression.vertex.config import COMPRESSION_VERTEX_MODEL
from app.compression.vertex.stream import compress_with_vertex_flash

# Generic Vertex helper work, including internal context compression, stays on Gemini 3 Flash.
COMPRESSION_MODEL_ID = COMPRESSION_VERTEX_MODEL
COMPRESSION_PROVIDER_ID = "vertex_ai"


async def compress_chat_history_context(*, source_text: str) -> CompressionResult:
    trimmed_source = source_text.strip()
    if not trimmed_source:
        raise ContextCompressionError("no chat context is available to compress")

    try:
        return await compress_with_vertex_flash(
            system_instruction=COMPRESSION_SYSTEM_INSTRUCTION,
            user_prompt=build_compression_user_prompt(source_text=trimmed_source),
        )
    except ContextCompressionError:
        raise
    except Exception as exc:
        raise ContextCompressionError("internal context compression failed") from exc
