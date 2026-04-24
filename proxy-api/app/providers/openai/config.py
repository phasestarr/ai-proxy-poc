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
from app.providers.types import ProviderFunctionDeclaration
from app.providers.openai.tools import build_openai_hosted_tools

_OPENAI_REQUEST_DEFAULTS: dict[str, object] = {
    "store": False,
}

# OpenAI latest Responses shape:
# - `reasoning.effort`: "none" | "low" | "medium" | "high" | "xhigh"
# - `reasoning.summary`: "auto" | "concise" | "detailed"
# - `text.verbosity`: "low" | "medium" | "high"
# - `tool_choice`: usually "none" | "auto" | "required"
# - `max_output_tokens`: total generated output cap, including reasoning tokens.
OPENAI_RESPONSE_PRESETS: dict[str, dict[str, object]] = {
    "none": {
        "max_output_tokens": 1024,
        "reasoning": {
            "effort": "none",
            "summary": "auto",
        },
        "text": {
            "verbosity": "low",
        },
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    },
    "low": {
        "max_output_tokens": 2048,
        "reasoning": {
            "effort": "low",
            "summary": "auto",
        },
        "text": {
            "verbosity": "low",
        },
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    },
    "normal": {
        "max_output_tokens": 4096,
        "reasoning": {
            "effort": "medium",
            "summary": "auto",
        },
        "text": {
            "verbosity": "medium",
        },
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    },
    "high": {
        # "max_output_tokens": 128000,
        "reasoning": {
            "effort": "high",
            "summary": "detailed",
        },
        "text": {
            "verbosity": "medium",
        },
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    },
    "xhigh": {
        # "max_output_tokens": 128000,
        "reasoning": {
            "effort": "xhigh",
            "summary": "detailed",
        },
        "text": {
            "verbosity": "high",
        },
        "tool_choice": "auto",
        "parallel_tool_calls": True,
    },
}

# Change only the preset string on the right.
# - `gpt-5.4`: higher effort for deeper agentic/coding work.
# - `gpt-5.4-mini`: normal is a reasonable default.
# - `gpt-5.4-nano`: low keeps cost/latency down.
OPENAI_MODEL_RESPONSE_PRESET: dict[str, str] = {
    "gpt-5.4": "high",
    "gpt-5.4-mini": "normal",
    "gpt-5.4-nano": "low",
}


def build_openai_responses_request(
    *,
    model: str,
    request_system_instruction: str | None,
    input_messages: list[dict[str, object]],
    selected_tool_ids: Iterable[str],
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> dict[str, object]:
    del function_declarations

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
