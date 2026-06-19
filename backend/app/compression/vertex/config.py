from __future__ import annotations


COMPRESSION_VERTEX_MODEL = "gemini-3-flash-preview"
COMPRESSION_VERTEX_LOCATION = "global"


def build_compression_generate_content_config(*, types, system_instruction: str):
    thinking_level = "MEDIUM"
    thinking_level_type = getattr(types, "ThinkingLevel", None)
    if thinking_level_type is not None:
        thinking_level = getattr(thinking_level_type, "MEDIUM", thinking_level)

    thinking_config_payload = {
        "thinking_level": thinking_level,
        "include_thoughts": False,
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
