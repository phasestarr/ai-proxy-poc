"""
OpenAI Responses API request assembly.

Purpose:
- Keep provider request defaults and config wiring out of the stream executor.
- Keep the small set of OpenAI knobs we actually tweak often.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from app.config.chat_instructions import build_chat_system_instruction
from app.providers.openai.tools import build_openai_hosted_tools

_OPENAI_REQUEST_DEFAULTS: dict[str, object] = {
    "store": False,
}

# OpenAI latest Responses shape:
# - `reasoning.effort`: "none" | "low" | "medium" | "high" | "xhigh" | "max"
#   (`max` availability depends on the selected model.)
# - `reasoning.summary`: "auto" | "concise" | "detailed"
# - `text.verbosity`: "low" | "medium" | "high"
# - `max_output_tokens`: total generated output cap, including reasoning tokens.
OPENAI_RESPONSE_PRESETS: dict[str, dict[str, object]] = {
    "none": {
        "reasoning": {
            "effort": "none",
            "summary": "auto",
        },
        "text": {
            "verbosity": "low",
        },
    },
    "low": {
        "reasoning": {
            "effort": "low",
            "summary": "auto",
        },
        "text": {
            "verbosity": "low",
        },
    },
    "normal": {
        "reasoning": {
            "effort": "medium",
            "summary": "auto",
        },
        "text": {
            "verbosity": "medium",
        },
    },
    "high": {
        "reasoning": {
            "effort": "high",
            "summary": "detailed",
        },
        "text": {
            "verbosity": "medium",
        },
    },
    "xhigh": {
        "reasoning": {
            "effort": "xhigh",
            "summary": "detailed",
        },
        "text": {
            "verbosity": "high",
        },
    },
    "max": {
        "reasoning": {
            "effort": "max",
            "summary": "detailed",
        },
        "text": {
            "verbosity": "high",
        },
    },
}

# Change only the preset string on the right.
# - GPT-5.6 Sol supports: `none` | `low` | `normal` | `high` | `xhigh` | `max`.
# - GPT-5.6 Terra supports: `none` | `low` | `normal` | `high` | `xhigh` | `max`.
# - GPT-5.6 Luna supports: `none` | `low` | `normal` | `high` | `xhigh` | `max`.
# - GPT-5.4 Mini supports: `none` | `low` | `normal` | `high` | `xhigh`.
OPENAI_MODEL_RESPONSE_PRESET: dict[str, str] = {
    "gpt-5.6-sol": "max",
    "gpt-5.6-terra": "xhigh",
    "gpt-5.6-luna": "high",
    "gpt-5.4-mini": "high",
}

# Provider max output caps from OpenAI model docs (checked 2026-07-16).
# To clamp lower later, change only the numeric value on the right.
OPENAI_MODEL_MAX_OUTPUT_TOKENS: dict[str, int] = {
    "gpt-5.6-sol": 128_000,
    "gpt-5.6-terra": 128_000,
    "gpt-5.6-luna": 128_000,
    "gpt-5.4-mini": 128_000,
}


def build_openai_responses_request(
    *,
    model: str,
    request_system_instruction: str | None,
    input_messages: list[dict[str, object]],
    selected_tool_ids: Iterable[str],
) -> dict[str, object]:
    request_kwargs: dict[str, object] = {
        "model": model,
        "instructions": build_chat_system_instruction(
            request_system_instruction=request_system_instruction,
        ),
        "input": input_messages,
        **_OPENAI_REQUEST_DEFAULTS,
    }
    _apply_openai_response_preset(
        request_kwargs=request_kwargs,
        model=model,
    )

    configured_tools = build_openai_hosted_tools(selected_tool_ids=selected_tool_ids)
    if configured_tools:
        request_kwargs["tools"] = configured_tools

    return request_kwargs


def _apply_openai_response_preset(
    *,
    request_kwargs: dict[str, object],
    model: str,
) -> None:
    preset_name = OPENAI_MODEL_RESPONSE_PRESET.get(model)
    if not preset_name:
        return

    if preset_name not in OPENAI_RESPONSE_PRESETS:
        raise ValueError(f"unknown openai response preset: {preset_name}")

    request_patch = deepcopy(OPENAI_RESPONSE_PRESETS[preset_name])
    try:
        request_kwargs["max_output_tokens"] = OPENAI_MODEL_MAX_OUTPUT_TOKENS[model]
    except KeyError as exc:
        raise ValueError(f"missing openai model max_output_tokens: {model}") from exc

    for key, value in _prune_none_values(request_patch).items():
        request_kwargs[key] = value


def _prune_none_values(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}

    cleaned: dict[str, object] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, dict):
            nested = _prune_none_values(item)
            if nested:
                cleaned[key] = nested
            continue
        cleaned[key] = item
    return cleaned
