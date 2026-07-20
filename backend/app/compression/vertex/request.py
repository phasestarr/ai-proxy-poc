"""Vertex request construction for context compression."""

from __future__ import annotations

from app.compression.vertex.options import (
    COMPRESSION_VERTEX_INCLUDE_THOUGHTS,
    COMPRESSION_VERTEX_THINKING_LEVEL,
)


def build_compression_generate_content_config(*, types, system_instruction: str):
    thinking_level = COMPRESSION_VERTEX_THINKING_LEVEL
    thinking_level_type = getattr(types, "ThinkingLevel", None)
    if thinking_level_type is not None:
        thinking_level = getattr(thinking_level_type, COMPRESSION_VERTEX_THINKING_LEVEL, thinking_level)

    thinking_config_payload = {
        "thinking_level": thinking_level,
        "include_thoughts": COMPRESSION_VERTEX_INCLUDE_THOUGHTS,
    }
    thinking_config_type = getattr(types, "ThinkingConfig", None)
    thinking_config = (
        thinking_config_type(**thinking_config_payload)
        if thinking_config_type is not None
        else thinking_config_payload
    )
    return types.GenerateContentConfig(
        systemInstruction=system_instruction,
        thinkingConfig=thinking_config,
    )
