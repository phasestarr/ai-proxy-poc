"""
Purpose:
- Build Anthropic-specific hosted tool payloads for the Messages API.

Responsibilities:
- Keep Anthropic hosted tool wiring inside the Anthropic provider package
- Translate backend-owned tool ids into provider-native tool definitions
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from app.config.providers.anthropic import anthropic_settings
from app.providers.types import ProviderToolDefinition

ANTHROPIC_CODE_EXECUTION_BETA = "code-execution-2025-08-25"

# `models.py` decides what model to use what tool.
ANTHROPIC_TOOL_DEFINITIONS_BY_ID: dict[str, ProviderToolDefinition] = {
    "web_search": ProviderToolDefinition(
        public_id="web_search",
        display_name="Web Search",
        available=True,
    ),
    "code_execution": ProviderToolDefinition(
        public_id="code_execution",
        display_name="Code Execution",
        available=True,
    ),
}

_ANTHROPIC_TOOL_OPTION_DEFAULTS: dict[str, object] = {
    "web_search": {
        "enabled": False,
        "version": "web_search_20250305",
        "allowed_domains": {"enabled": False, "value": []},
        "blocked_domains": {"enabled": False, "value": []},
        "max_uses": {"enabled": False, "value": 5},
    },
}


class AnthropicToolConfigurationError(RuntimeError):
    """Raised when a selected Anthropic tool cannot be configured."""


def build_anthropic_hosted_tools(
    *,
    selected_tool_ids: Iterable[str],
) -> list[dict[str, object]]:
    configured_tools: list[dict[str, object]] = []
    tool_builders: dict[str, object] = {
        "web_search": _build_anthropic_web_search_tool,
        "code_execution": _build_anthropic_code_execution_tool,
    }
    normalized_tool_options = deepcopy(_ANTHROPIC_TOOL_OPTION_DEFAULTS)

    for tool_id in _normalize_selected_tool_ids(selected_tool_ids):
        builder = tool_builders.get(tool_id)
        if builder is None:
            continue
        configured_tools.append(builder(normalized_tool_options))

    return configured_tools


def build_anthropic_beta_headers(*, selected_tool_ids: Iterable[str]) -> list[str]:
    normalized_tool_ids = set(_normalize_selected_tool_ids(selected_tool_ids))
    betas: list[str] = []
    if "code_execution" in normalized_tool_ids:
        betas.append(ANTHROPIC_CODE_EXECUTION_BETA)
    return betas


def get_anthropic_tool_definitions(*tool_ids: str) -> tuple[ProviderToolDefinition, ...]:
    return tuple(
        ANTHROPIC_TOOL_DEFINITIONS_BY_ID[tool_id]
        for tool_id in tool_ids
        if tool_id in ANTHROPIC_TOOL_DEFINITIONS_BY_ID
    )


def _build_anthropic_web_search_tool(tool_options: dict[str, object]) -> dict[str, object]:
    web_search_options = tool_options.get("web_search", {})
    tool_payload: dict[str, object] = {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": _get_enabled_scalar_value(
            web_search_options.get("max_uses"),
            fallback=anthropic_settings.web_search_max_uses,
        ),
    }

    allowed_domains = _get_enabled_scalar_value(
        web_search_options.get("allowed_domains"),
        fallback=anthropic_settings.web_search_allowed_domains,
    )
    blocked_domains = _get_enabled_scalar_value(
        web_search_options.get("blocked_domains"),
        fallback=anthropic_settings.web_search_blocked_domains,
    )
    if allowed_domains and blocked_domains:
        raise AnthropicToolConfigurationError(
            "anthropic web search cannot use allowed and blocked domains at the same time"
        )
    if allowed_domains:
        tool_payload["allowed_domains"] = allowed_domains
    if blocked_domains:
        tool_payload["blocked_domains"] = blocked_domains

    return tool_payload


def _build_anthropic_code_execution_tool(tool_options: dict[str, object]) -> dict[str, object]:
    del tool_options
    return {
        "type": "code_execution_20250825",
        "name": "code_execution",
    }


def _normalize_selected_tool_ids(selected_tool_ids: Iterable[str]) -> list[str]:
    normalized_tool_ids: list[str] = []
    seen_tool_ids: set[str] = set()
    for tool_id in selected_tool_ids:
        normalized_tool_id = tool_id.strip()
        if not normalized_tool_id or normalized_tool_id in seen_tool_ids:
            continue
        normalized_tool_ids.append(normalized_tool_id)
        seen_tool_ids.add(normalized_tool_id)
    return normalized_tool_ids


def _get_enabled_scalar_value(option_config: object, *, fallback: object = None) -> object:
    if not isinstance(option_config, dict) or not option_config.get("enabled"):
        return fallback
    return option_config.get("value")
