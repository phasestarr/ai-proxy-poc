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

from app.providers.anthropic.config import (
    ANTHROPIC_CODE_EXECUTION_TOOL_VERSION,
    ANTHROPIC_DIRECT_WEB_TOOL_MODELS,
    ANTHROPIC_TOOLS,
    ANTHROPIC_WEB_FETCH_TOOL_VERSION,
    ANTHROPIC_WEB_SEARCH_TOOL_VERSION,
)
from app.providers.anthropic.options import ANTHROPIC_TOOL_OPTIONS
from app.providers.types import ProviderToolDefinition, provider_identifier_display_name

# `models.py` decides what model to use what tool.
ANTHROPIC_TOOL_DEFINITIONS_BY_ID = {
    tool_id: ProviderToolDefinition(tool_id, provider_identifier_display_name(tool_id), available)
    for tool_id, available in ANTHROPIC_TOOLS
}


class AnthropicToolConfigurationError(RuntimeError):
    """Raised when a selected Anthropic tool cannot be configured."""


def build_anthropic_hosted_tools(
    *,
    selected_tool_ids: Iterable[str],
    model: str | None = None,
) -> list[dict[str, object]]:
    configured_tools: list[dict[str, object]] = []
    tool_builders: dict[str, object] = {
        "web_search": _build_anthropic_web_search_tool,
        "web_fetch": _build_anthropic_web_fetch_tool,
        "code_execution": _build_anthropic_code_execution_tool,
    }
    normalized_tool_options = deepcopy(ANTHROPIC_TOOL_OPTIONS)

    for tool_id in _normalize_selected_tool_ids(selected_tool_ids):
        builder = tool_builders.get(tool_id)
        if builder is None:
            continue
        configured_tools.append(builder(normalized_tool_options, model=model))

    return configured_tools


def build_anthropic_beta_headers(*, selected_tool_ids: Iterable[str]) -> list[str]:
    del selected_tool_ids
    return []


def get_anthropic_tool_definitions(*tool_ids: str) -> tuple[ProviderToolDefinition, ...]:
    return tuple(
        ANTHROPIC_TOOL_DEFINITIONS_BY_ID[tool_id]
        for tool_id in tool_ids
        if tool_id in ANTHROPIC_TOOL_DEFINITIONS_BY_ID
    )


def _build_anthropic_web_search_tool(tool_options: dict[str, object], *, model: str | None = None) -> dict[str, object]:
    web_search_options = tool_options.get("web_search", {})
    if not isinstance(web_search_options, dict):
        raise AnthropicToolConfigurationError("anthropic web_search options must be a mapping")
    tool_payload: dict[str, object] = {
        "type": ANTHROPIC_WEB_SEARCH_TOOL_VERSION,
        "name": "web_search",
        **_prune_none_values(web_search_options),
    }
    if model in ANTHROPIC_DIRECT_WEB_TOOL_MODELS:
        tool_payload["allowed_callers"] = ["direct"]

    allowed_domains = web_search_options.get("allowed_domains")
    blocked_domains = web_search_options.get("blocked_domains")
    if allowed_domains and blocked_domains:
        raise AnthropicToolConfigurationError(
            "anthropic web search cannot use allowed and blocked domains at the same time"
        )
    if allowed_domains:
        tool_payload["allowed_domains"] = allowed_domains
    if blocked_domains:
        tool_payload["blocked_domains"] = blocked_domains

    return tool_payload


def _build_anthropic_web_fetch_tool(tool_options: dict[str, object], *, model: str | None = None) -> dict[str, object]:
    web_fetch_options = tool_options.get("web_fetch", {})
    if not isinstance(web_fetch_options, dict):
        raise AnthropicToolConfigurationError("anthropic web_fetch options must be a mapping")
    tool_payload: dict[str, object] = {
        "type": ANTHROPIC_WEB_FETCH_TOOL_VERSION,
        "name": "web_fetch",
        **_prune_none_values(web_fetch_options),
    }
    if model in ANTHROPIC_DIRECT_WEB_TOOL_MODELS:
        tool_payload["allowed_callers"] = ["direct"]
    return tool_payload


def _build_anthropic_code_execution_tool(tool_options: dict[str, object], *, model: str | None = None) -> dict[str, object]:
    del tool_options
    del model
    return {
        "type": ANTHROPIC_CODE_EXECUTION_TOOL_VERSION,
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


def _prune_none_values(value: dict[str, object]) -> dict[str, object]:
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
