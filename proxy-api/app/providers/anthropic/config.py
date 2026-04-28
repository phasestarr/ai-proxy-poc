"""
Anthropic Messages API request assembly.

Purpose:
- Keep provider request defaults and config wiring out of the stream executor.
- Keep the small set of Anthropic knobs we actually tweak often.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from app.config.chat_instructions import build_chat_system_instruction
from app.providers.anthropic.tools import build_anthropic_hosted_tools
from app.providers.types import ProviderFunctionDeclaration

# Anthropic latest request shape:
# - `thinking.type`: "adaptive"
# - `thinking.display`: "summarized" | "omitted"
# - `output_config.effort`: "low" | "medium" | "high" | "xhigh" | "max"
#   (`xhigh` is Opus 4.7 only)
# - `max_tokens` is required on Messages API requests.
# - Thinking tokens count toward `max_tokens`.
ANTHROPIC_REASONING_PRESETS: dict[str, dict[str, object]] = {
    "none": {
        "thinking": None,
        "output_config": None,
    },
    "low": {
        "thinking": {
            "type": "adaptive",
            "display": "summarized",
        },
        "output_config": {
            "effort": "low",
        },
    },
    "normal": {
        "thinking": {
            "type": "adaptive",
            "display": "summarized",
        },
        "output_config": {
            "effort": "medium",
        },
    },
    "high": {
        "thinking": {
            "type": "adaptive",
            "display": "summarized",
        },
        "output_config": {
            "effort": "high",
        },
    },
    "xhigh": {
        "thinking": {
            "type": "adaptive",
            "display": "summarized",
        },
        "output_config": {
            "effort": "xhigh",
        },
    },
    "max": {
        "thinking": {
            "type": "adaptive",
            "display": "summarized",
        },
        "output_config": {
            "effort": "max",
        },
    },
}

# Change only the preset string on the right.
# - Opus 4.7: `xhigh` is useful for long agentic/coding runs.
# - Sonnet 4.6: `high` (`high`) is a decent default.
# - Haiku 4.5: keep `none`. In this codebase we treat Haiku as no-thinking/no-effort.
ANTHROPIC_MODEL_REASONING_PRESET: dict[str, str] = {
    "claude-opus-4-7": "xhigh",
    "claude-sonnet-4-6": "high",
    "claude-haiku-4-5": "none",
}

# Provider max output caps from Anthropic model docs (checked 2026-04-28).
# To clamp lower later, change only the numeric value on the right.
ANTHROPIC_MODEL_MAX_TOKENS: dict[str, int] = {
    "claude-opus-4-7": 128_000,
    "claude-sonnet-4-6": 64_000,
    "claude-haiku-4-5": 64_000,
}


def build_anthropic_messages_request(
    *,
    model: str,
    request_system_instruction: str | None,
    messages: list[dict[str, object]],
    selected_tool_ids: Iterable[str],
    function_declarations: Iterable[ProviderFunctionDeclaration] = (),
) -> dict[str, object]:
    del function_declarations

    request_kwargs: dict[str, object] = {
        "model": model,
        "system": build_chat_system_instruction(
            request_system_instruction=request_system_instruction,
        ),
        "messages": messages,
    }
    _apply_anthropic_reasoning_preset(
        request_kwargs=request_kwargs,
        model=model,
    )

    configured_tools = build_anthropic_hosted_tools(selected_tool_ids=selected_tool_ids)
    if configured_tools:
        request_kwargs["tools"] = configured_tools

    return request_kwargs


def _apply_anthropic_reasoning_preset(
    *,
    request_kwargs: dict[str, object],
    model: str,
) -> None:
    preset_name = ANTHROPIC_MODEL_REASONING_PRESET.get(model)
    if not preset_name:
        return

    if preset_name not in ANTHROPIC_REASONING_PRESETS:
        raise ValueError(f"unknown anthropic reasoning preset: {preset_name}")

    if model == "claude-haiku-4-5" and preset_name != "none":
        raise ValueError("claude-haiku-4-5 must use anthropic reasoning preset 'none'")

    request_patch = deepcopy(ANTHROPIC_REASONING_PRESETS[preset_name])
    try:
        request_kwargs["max_tokens"] = ANTHROPIC_MODEL_MAX_TOKENS[model]
    except KeyError as exc:
        raise ValueError(f"missing anthropic model max_tokens: {model}") from exc

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
