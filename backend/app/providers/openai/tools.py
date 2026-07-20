"""
Purpose:
- Build OpenAI-specific hosted tool payloads for the Responses API.

Responsibilities:
- Keep OpenAI hosted tool wiring inside the OpenAI provider package
- Translate backend-owned tool ids into provider-native tool definitions
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from app.providers.openai.config import OPENAI_TOOLS
from app.providers.openai.options import OPENAI_TOOL_OPTIONS
from app.providers.openai.settings import openai_settings
from app.providers.types import ProviderToolDefinition, provider_identifier_display_name

# `models.py` decides what model to use what tool.
OPENAI_TOOL_DEFINITIONS_BY_ID = {
    tool_id: ProviderToolDefinition(tool_id, provider_identifier_display_name(tool_id), available)
    for tool_id, available in OPENAI_TOOLS
}


class OpenAIToolConfigurationError(RuntimeError):
    """Raised when a selected OpenAI tool cannot be configured."""


def build_openai_hosted_tools(
    *,
    selected_tool_ids: Iterable[str],
) -> list[dict[str, object]]:
    configured_tools: list[dict[str, object]] = []
    tool_builders: dict[str, object] = {
        "web_search": _build_openai_web_search_tool,
        "file_search": _build_openai_file_search_tool,
        "code_interpreter": _build_openai_code_interpreter_tool,
        "shell": _build_openai_shell_tool,
    }
    normalized_tool_options = deepcopy(OPENAI_TOOL_OPTIONS)

    for tool_id in _normalize_selected_tool_ids(selected_tool_ids):
        builder = tool_builders.get(tool_id)
        if builder is None:
            continue
        configured_tools.append(builder(normalized_tool_options))

    return configured_tools


def get_openai_tool_definitions(*tool_ids: str) -> tuple[ProviderToolDefinition, ...]:
    return tuple(
        OPENAI_TOOL_DEFINITIONS_BY_ID[tool_id]
        for tool_id in tool_ids
        if tool_id in OPENAI_TOOL_DEFINITIONS_BY_ID
    )


def _build_openai_web_search_tool(tool_options: dict[str, object]) -> dict[str, object]:
    web_search_options = tool_options.get("web_search", {})
    if not isinstance(web_search_options, dict):
        raise OpenAIToolConfigurationError("openai web_search options must be a mapping")
    return _prune_none_values({"type": "web_search", **web_search_options})


def _build_openai_file_search_tool(tool_options: dict[str, object]) -> dict[str, object]:
    _ensure_openai_file_search_tool_ready()
    file_search_options = tool_options.get("file_search", {})
    if not isinstance(file_search_options, dict):
        raise OpenAIToolConfigurationError("openai file_search options must be a mapping")

    tool_payload: dict[str, object] = {
        "type": "file_search",
        "vector_store_ids": openai_settings.vector_store_ids,
        **file_search_options,
    }
    return _prune_none_values(tool_payload)


def _build_openai_code_interpreter_tool(tool_options: dict[str, object]) -> dict[str, object]:
    code_interpreter_options = tool_options.get("code_interpreter", {})
    if not isinstance(code_interpreter_options, dict):
        raise OpenAIToolConfigurationError("openai code_interpreter options must be a mapping")
    return _prune_none_values({"type": "code_interpreter", **code_interpreter_options})


def _build_openai_shell_tool(tool_options: dict[str, object]) -> dict[str, object]:
    shell_options = tool_options.get("shell", {})
    if not isinstance(shell_options, dict):
        raise OpenAIToolConfigurationError("openai shell options must be a mapping")
    return _prune_none_values({"type": "shell", **shell_options})


def _ensure_openai_file_search_tool_ready() -> None:
    if not openai_settings.vector_store_ids:
        raise OpenAIToolConfigurationError("openai file_search tool is selected but no vector store ids are configured")

    if any(not vector_store_id.strip() for vector_store_id in openai_settings.vector_store_ids):
        raise OpenAIToolConfigurationError("openai vector store ids must not be blank")


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
