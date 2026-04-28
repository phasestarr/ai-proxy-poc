"""
Vertex request config assembly.

Purpose:
- Keep provider request defaults and config wiring out of the stream executor.
- Keep the small set of Vertex knobs we actually tweak often.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from app.config.chat_instructions import build_chat_system_instruction
from app.providers.types import ProviderFunctionDeclaration
from app.providers.vertex.tools import build_vertex_hosted_tools

# Gemini 3 thinking shape:
# - `thinking_config.thinking_level`: `MINIMAL` | `LOW` | `MEDIUM` | `HIGH`
# - `thinking_config.include_thoughts`: `True` | `False`
# - Gemini 3 Pro currently allows only `LOW` and `HIGH`.
# - `maxOutputTokens`: generated output cap. Keep this output-only; don't manage thinking separately.
VERTEX_RESPONSE_PRESETS: dict[str, dict[str, object]] = {
    "none": {
        "thinking_config": {
            "thinking_level": "MINIMAL",
            "include_thoughts": False,
        },
    },
    "low": {
        "thinking_config": {
            "thinking_level": "LOW",
            "include_thoughts": False,
        },
    },
    "normal": {
        "thinking_config": {
            "thinking_level": "MEDIUM",
            "include_thoughts": False,
        },
    },
    "high": {
        "thinking_config": {
            "thinking_level": "HIGH",
            "include_thoughts": True,
        },
    },
}

# Change only the preset string on the right.
# - `gemini-3.1-pro-preview`: current Gemini 3 Pro docs allow `LOW` or `HIGH` only.
# - `gemini-3-flash-preview`: `normal` maps to `MEDIUM`.
# - `gemini-3.1-flash-lite-preview`: `low` is the default here.
VERTEX_MODEL_RESPONSE_PRESET: dict[str, str] = {
    "gemini-3.1-pro-preview": "high",
    "gemini-3-flash-preview": "normal",
    "gemini-3.1-flash-lite-preview": "low",
}

# Provider max output caps from Vertex AI model docs (checked 2026-04-28).
# To clamp lower later, change only the numeric value on the right.
VERTEX_MODEL_MAX_OUTPUT_TOKENS: dict[str, int] = {
    "gemini-3.1-pro-preview": 65_536,
    "gemini-3-flash-preview": 65_536,
    "gemini-3.1-flash-lite-preview": 65_535,
}


def build_vertex_generate_content_config(
    *,
    types,
    model: str,
    request_system_instruction: str | None,
    selected_tool_ids: Iterable[str],
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
):
    del function_declarations

    config_kwargs: dict[str, object] = {
        "systemInstruction": build_chat_system_instruction(
            request_system_instruction=request_system_instruction,
        ),
    }

    configured_tools = build_vertex_hosted_tools(
        selected_tool_ids=selected_tool_ids,
        types_module=types,
    )
    if configured_tools:
        config_kwargs["tools"] = configured_tools

    _apply_vertex_response_preset(
        config_kwargs=config_kwargs,
        model=model,
        types_module=types,
    )

    return types.GenerateContentConfig(**config_kwargs)


def _apply_vertex_response_preset(
    *,
    config_kwargs: dict[str, object],
    model: str,
    types_module,
) -> None:
    preset_name = VERTEX_MODEL_RESPONSE_PRESET.get(model)
    if not preset_name:
        return

    if preset_name not in VERTEX_RESPONSE_PRESETS:
        raise ValueError(f"unknown vertex response preset: {preset_name}")

    if model == "gemini-3.1-pro-preview" and preset_name not in {"low", "high"}:
        raise ValueError("gemini-3.1-pro-preview must use vertex preset 'low' or 'high'")

    request_patch = deepcopy(VERTEX_RESPONSE_PRESETS[preset_name])
    try:
        config_kwargs["maxOutputTokens"] = VERTEX_MODEL_MAX_OUTPUT_TOKENS[model]
    except KeyError as exc:
        raise ValueError(f"missing vertex model maxOutputTokens: {model}") from exc

    thinking_config = request_patch.get("thinking_config")
    if isinstance(thinking_config, dict):
        config_kwargs["thinkingConfig"] = _build_vertex_thinking_config(
            thinking_config=thinking_config,
            types_module=types_module,
        )


def _build_vertex_thinking_config(*, thinking_config: dict[str, object], types_module):
    thinking_level = thinking_config.get("thinking_level")
    thinking_level_type = getattr(types_module, "ThinkingLevel", None)
    if thinking_level_type is not None and isinstance(thinking_level, str):
        thinking_level = getattr(thinking_level_type, thinking_level, thinking_level)

    payload = {
        "thinking_level": thinking_level,
        "include_thoughts": bool(thinking_config.get("include_thoughts", False)),
    }

    thinking_config_type = getattr(types_module, "ThinkingConfig", None)
    if thinking_config_type is None:
        return payload
    return thinking_config_type(**payload)
