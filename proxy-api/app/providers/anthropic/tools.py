"""
Purpose:
- Build Anthropic-specific hosted tool payloads for the Messages API.

Responsibilities:
- Keep Anthropic hosted tool wiring inside the Anthropic provider package
- Translate backend-owned tool ids into provider-native tool definitions
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config.providers.anthropic import anthropic_settings

ANTHROPIC_CODE_EXECUTION_BETA = "code-execution-2025-08-25"


class AnthropicToolConfigurationError(RuntimeError):
    """Raised when a selected Anthropic tool cannot be configured."""


def build_anthropic_hosted_tools(*, selected_tool_ids: Iterable[str]) -> list[dict[str, object]]:
    configured_tools: list[dict[str, object]] = []
    tool_builders = {
        "web_search": _build_anthropic_web_search_tool,
        "code_execution": _build_anthropic_code_execution_tool,
    }

    for tool_id in _normalize_selected_tool_ids(selected_tool_ids):
        builder = tool_builders.get(tool_id)
        if builder is None:
            continue
        configured_tools.append(builder())

    return configured_tools


def build_anthropic_beta_headers(*, selected_tool_ids: Iterable[str]) -> list[str]:
    normalized_tool_ids = set(_normalize_selected_tool_ids(selected_tool_ids))
    betas: list[str] = []
    if "code_execution" in normalized_tool_ids:
        betas.append(ANTHROPIC_CODE_EXECUTION_BETA)
    return betas


def _build_anthropic_web_search_tool() -> dict[str, object]:
    tool_payload: dict[str, object] = {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": anthropic_settings.web_search_max_uses,
    }

    allowed_domains = anthropic_settings.web_search_allowed_domains
    blocked_domains = anthropic_settings.web_search_blocked_domains
    if allowed_domains and blocked_domains:
        raise AnthropicToolConfigurationError(
            "anthropic web search cannot use allowed and blocked domains at the same time"
        )
    if allowed_domains:
        tool_payload["allowed_domains"] = allowed_domains
    if blocked_domains:
        tool_payload["blocked_domains"] = blocked_domains

    return tool_payload


def _build_anthropic_code_execution_tool() -> dict[str, object]:
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

