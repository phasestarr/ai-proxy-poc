"""
Purpose:
- Build Vertex-specific tool payloads.

Responsibilities:
- Keep Vertex hosted tool wiring inside the Vertex provider package
- Preserve the tool selection pipeline even while no tools are enabled

Notes:
- Only tools explicitly selected for the current request are attached.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from app.config.providers.vertex import vertex_settings
from app.providers.types import ProviderToolDefinition

# `models.py` decides what model to use what tool.
VERTEX_TOOL_DEFINITIONS_BY_ID: dict[str, ProviderToolDefinition] = {
    "web_search": ProviderToolDefinition(
        public_id="web_search",
        display_name="Google Search",
        available=True,
    ),
    "retrieval": ProviderToolDefinition(
        public_id="retrieval",
        display_name="Vertex RAG",
        available=True,
    ),
    "code_execution": ProviderToolDefinition(
        public_id="code_execution",
        display_name="Code Execution",
        available=True,
    ),
    "url_context": ProviderToolDefinition(
        public_id="url_context",
        display_name="URL Context",
        available=True,
    ),
}

class VertexToolConfigurationError(RuntimeError):
    """Raised when a selected Vertex tool cannot be configured."""


_VERTEX_TOOL_OPTION_DEFAULTS: dict[str, object] = {
    "retrieval": {
        "rag_resources": {"enabled": False, "value": []},
        "similarity_top_k": {"enabled": False, "value": 5},
        "vector_distance_threshold": {"enabled": False, "value": None},
    },
}


def build_vertex_hosted_tools(
    *,
    selected_tool_ids: Iterable[str],
    types_module=None,
) -> list[object]:
    configured_tools: list[object] = []
    tool_builders: dict[str, object] = {
        "web_search": _build_vertex_web_search_tool,
        "retrieval": _build_vertex_retrieval_tool,
        "code_execution": _build_vertex_code_execution_tool,
        "url_context": _build_vertex_url_context_tool,
    }
    normalized_tool_options = deepcopy(_VERTEX_TOOL_OPTION_DEFAULTS)

    for tool_id in _normalize_selected_tool_ids(selected_tool_ids):
        builder = tool_builders.get(tool_id)
        if builder is None:
            continue
        configured_tools.append(
            builder(
                types_module=types_module,
                tool_options=normalized_tool_options,
            )
        )

    return configured_tools


def get_vertex_tool_definitions(*tool_ids: str) -> tuple[ProviderToolDefinition, ...]:
    return tuple(
        VERTEX_TOOL_DEFINITIONS_BY_ID[tool_id]
        for tool_id in tool_ids
        if tool_id in VERTEX_TOOL_DEFINITIONS_BY_ID
    )


def _build_vertex_web_search_tool(*, types_module=None, tool_options: dict[str, object]) -> object:
    del tool_options
    tool_payload = {
        "google_search": {},
    }

    tool_type = getattr(types_module, "Tool", None) if types_module is not None else None
    if tool_type is None:
        return tool_payload

    try:
        return tool_type(**tool_payload)
    except Exception as exc:
        raise VertexToolConfigurationError("vertex web search tool payload could not be constructed") from exc


def _build_vertex_retrieval_tool(*, types_module=None, tool_options: dict[str, object]) -> object:
    _ensure_vertex_retrieval_tool_ready()
    retrieval_options = tool_options.get("retrieval", {})

    rag_store: dict[str, object] = {
        "rag_resources": _get_enabled_scalar_value(
            retrieval_options.get("rag_resources"),
            fallback=[{"rag_corpus": corpus} for corpus in vertex_settings.rag_corpora],
        ),
        "similarity_top_k": _get_enabled_scalar_value(
            retrieval_options.get("similarity_top_k"),
            fallback=vertex_settings.rag_similarity_top_k,
        ),
    }

    vector_distance_threshold = _get_enabled_scalar_value(
        retrieval_options.get("vector_distance_threshold"),
        fallback=vertex_settings.rag_vector_distance_threshold,
    )
    if vector_distance_threshold is not None:
        rag_store["vector_distance_threshold"] = vector_distance_threshold

    tool_payload = {
        "retrieval": {
            "vertex_rag_store": rag_store,
        }
    }

    tool_type = getattr(types_module, "Tool", None) if types_module is not None else None
    if tool_type is None:
        return tool_payload

    try:
        return tool_type(**tool_payload)
    except Exception as exc:
        raise VertexToolConfigurationError("vertex retrieval tool payload could not be constructed") from exc


def _build_vertex_code_execution_tool(*, types_module=None, tool_options: dict[str, object]) -> object:
    del tool_options
    tool_payload = {
        "code_execution": {},
    }

    tool_type = getattr(types_module, "Tool", None) if types_module is not None else None
    if tool_type is None:
        return tool_payload

    try:
        return tool_type(**tool_payload)
    except Exception as exc:
        raise VertexToolConfigurationError("vertex code execution tool payload could not be constructed") from exc


def _build_vertex_url_context_tool(*, types_module=None, tool_options: dict[str, object]) -> object:
    del tool_options
    tool_payload = {
        "url_context": {},
    }

    tool_type = getattr(types_module, "Tool", None) if types_module is not None else None
    if tool_type is None:
        return tool_payload

    try:
        return tool_type(**tool_payload)
    except Exception as exc:
        raise VertexToolConfigurationError("vertex url context tool payload could not be constructed") from exc


def _ensure_vertex_retrieval_tool_ready() -> None:
    if not vertex_settings.rag_corpora:
        raise VertexToolConfigurationError("vertex retrieval tool is selected but no retrieval corpora are configured")

    if any(not corpus.strip() for corpus in vertex_settings.rag_corpora):
        raise VertexToolConfigurationError("vertex retrieval corpus resource names must not be blank")

    if vertex_settings.rag_similarity_top_k < 1:
        raise VertexToolConfigurationError("vertex retrieval similarity_top_k must be at least 1")

    threshold = vertex_settings.rag_vector_distance_threshold
    if threshold is not None and threshold < 0:
        raise VertexToolConfigurationError("vertex retrieval vector distance threshold must be non-negative")


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
