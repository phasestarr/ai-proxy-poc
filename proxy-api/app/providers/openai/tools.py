"""
Purpose:
- Build OpenAI-specific hosted tool payloads for the Responses API.

Responsibilities:
- Keep OpenAI hosted tool wiring inside the OpenAI provider package
- Translate backend-owned tool ids into provider-native tool definitions
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config.providers.openai import openai_settings


class OpenAIToolConfigurationError(RuntimeError):
    """Raised when a selected OpenAI tool cannot be configured."""


def build_openai_hosted_tools(*, selected_tool_ids: Iterable[str]) -> list[dict[str, object]]:
    configured_tools: list[dict[str, object]] = []
    tool_builders = {
        "web_search": _build_openai_web_search_tool,
        "retrieval": _build_openai_file_search_tool,
        "code_execution": _build_openai_code_interpreter_tool,
    }

    for tool_id in _normalize_selected_tool_ids(selected_tool_ids):
        builder = tool_builders.get(tool_id)
        if builder is None:
            continue
        configured_tools.append(builder())

    return configured_tools


def _build_openai_web_search_tool() -> dict[str, object]:
    return {
        "type": "web_search",
    }


def _build_openai_file_search_tool() -> dict[str, object]:
    _ensure_openai_file_search_tool_ready()

    tool_payload: dict[str, object] = {
        "type": "file_search",
        "vector_store_ids": openai_settings.vector_store_ids,
        "max_num_results": openai_settings.file_search_max_num_results,
    }

    if openai_settings.file_search_score_threshold is not None:
        tool_payload["ranking_options"] = {
            "score_threshold": openai_settings.file_search_score_threshold,
        }

    return tool_payload


def _build_openai_code_interpreter_tool() -> dict[str, object]:
    return {
        "type": "code_interpreter",
        "container": {
            "type": "auto",
            "memory_limit": openai_settings.code_interpreter_memory_limit,
        },
    }


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

