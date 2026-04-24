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

from app.config.providers.openai import openai_settings
from app.providers.types import ProviderToolDefinition

# `models.py` decides what model to use what tool.
OPENAI_TOOL_DEFINITIONS_BY_ID: dict[str, ProviderToolDefinition] = {
    "web_search": ProviderToolDefinition(
        public_id="web_search",
        display_name="Web Search",
        available=True,
    ),
    "retrieval": ProviderToolDefinition(
        public_id="retrieval",
        display_name="File Search",
        available=True,
    ),
    "code_execution": ProviderToolDefinition(
        public_id="code_execution",
        display_name="Code Interpreter",
        available=True,
    ),
}


class OpenAIToolConfigurationError(RuntimeError):
    """Raised when a selected OpenAI tool cannot be configured."""


_OPENAI_TOOL_OPTION_DEFAULTS: dict[str, object] = {
    "web_search": {
        "filters": {"enabled": False, "value": {}},
        "search_context_size": {"enabled": False, "value": "medium"},
        "type": {"enabled": False, "value": "web_search"},
        "user_location": {"enabled": False, "value": {}},
    },
    "file_search": {
        "filters": {"enabled": False, "value": {}},
        "max_num_results": {"enabled": False, "value": 5},
        "ranking_options": {
            "enabled": False,
            "score_threshold": None,
            "ranker": None,
        },
    },
    "code_interpreter": {
        "container": {"enabled": False, "value": {}},
    },
}


def build_openai_hosted_tools(
    *,
    selected_tool_ids: Iterable[str],
) -> list[dict[str, object]]:
    configured_tools: list[dict[str, object]] = []
    tool_builders: dict[str, object] = {
        "web_search": _build_openai_web_search_tool,
        "retrieval": _build_openai_file_search_tool,
        "code_execution": _build_openai_code_interpreter_tool,
    }
    normalized_tool_options = deepcopy(_OPENAI_TOOL_OPTION_DEFAULTS)

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
    tool_payload: dict[str, object] = {
        "type": _get_enabled_scalar_value(
            web_search_options.get("type"),
            fallback="web_search",
        ),
    }

    filters = _get_enabled_scalar_value(web_search_options.get("filters"))
    if filters:
        tool_payload["filters"] = filters

    search_context_size = _get_enabled_scalar_value(web_search_options.get("search_context_size"))
    if search_context_size:
        tool_payload["search_context_size"] = search_context_size

    user_location = _get_enabled_scalar_value(web_search_options.get("user_location"))
    if user_location:
        tool_payload["user_location"] = user_location

    return tool_payload


def _build_openai_file_search_tool(tool_options: dict[str, object]) -> dict[str, object]:
    _ensure_openai_file_search_tool_ready()
    file_search_options = tool_options.get("file_search", {})

    tool_payload: dict[str, object] = {
        "type": "file_search",
        "vector_store_ids": openai_settings.vector_store_ids,
        "max_num_results": _get_enabled_scalar_value(
            file_search_options.get("max_num_results"),
            fallback=openai_settings.file_search_max_num_results,
        ),
    }

    filters = _get_enabled_scalar_value(file_search_options.get("filters"))
    if filters:
        tool_payload["filters"] = filters

    ranking_options_config = file_search_options.get("ranking_options")
    ranking_options: dict[str, object] = {}
    if openai_settings.file_search_score_threshold is not None:
        ranking_options["score_threshold"] = openai_settings.file_search_score_threshold
    if isinstance(ranking_options_config, dict) and ranking_options_config.get("enabled"):
        if ranking_options_config.get("score_threshold") is not None:
            ranking_options["score_threshold"] = ranking_options_config.get("score_threshold")
        if ranking_options_config.get("ranker"):
            ranking_options["ranker"] = ranking_options_config.get("ranker")
    if ranking_options:
        tool_payload["ranking_options"] = ranking_options

    return tool_payload


def _build_openai_code_interpreter_tool(tool_options: dict[str, object]) -> dict[str, object]:
    tool_payload = {
        "type": "code_interpreter",
        "container": {
            "type": "auto",
            "memory_limit": openai_settings.code_interpreter_memory_limit,
        },
    }

    code_interpreter_options = tool_options.get("code_interpreter", {})
    container_override = _get_enabled_scalar_value(code_interpreter_options.get("container"))
    if container_override:
        tool_payload["container"] = container_override

    return tool_payload


def _ensure_openai_file_search_tool_ready() -> None:
    if not openai_settings.vector_store_ids:
        raise OpenAIToolConfigurationError("openai retrieval tool is selected but no vector store ids are configured")

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


def _get_enabled_scalar_value(option_config: object, *, fallback: object = None) -> object:
    if not isinstance(option_config, dict) or not option_config.get("enabled"):
        return fallback
    return option_config.get("value")
