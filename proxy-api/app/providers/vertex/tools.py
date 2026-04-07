"""
Purpose:
- Build Vertex-specific tool payloads.

Responsibilities:
- Keep Vertex tool wiring inside the Vertex provider package
- Preserve the tool selection pipeline even while no tools are enabled

Notes:
- Only tools explicitly selected for the current request are attached.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config.providers.vertex import vertex_settings


class VertexToolConfigurationError(RuntimeError):
    """Raised when a selected Vertex tool cannot be configured."""


def build_vertex_tools(
    *,
    selected_tool_ids: Iterable[str],
    types_module=None,
) -> list[object]:
    normalized_tool_ids = {tool_id.strip() for tool_id in selected_tool_ids if tool_id.strip()}
    configured_tools: list[object] = []

    if "rag" in normalized_tool_ids:
        configured_tools.append(_build_vertex_rag_tool(types_module=types_module))

    return configured_tools


def _build_vertex_rag_tool(*, types_module=None) -> object:
    _ensure_vertex_rag_tool_ready()

    rag_store: dict[str, object] = {
        "rag_resources": [{"rag_corpus": corpus} for corpus in vertex_settings.rag_corpora],
        "similarity_top_k": vertex_settings.rag_similarity_top_k,
    }

    if vertex_settings.rag_vector_distance_threshold is not None:
        rag_store["vector_distance_threshold"] = vertex_settings.rag_vector_distance_threshold

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
        raise VertexToolConfigurationError("vertex rag tool payload could not be constructed") from exc


def _ensure_vertex_rag_tool_ready() -> None:
    if not vertex_settings.rag_corpora:
        raise VertexToolConfigurationError("vertex rag tool is selected but no rag corpora are configured")

    if any(not corpus.strip() for corpus in vertex_settings.rag_corpora):
        raise VertexToolConfigurationError("vertex rag corpus resource names must not be blank")

    if vertex_settings.rag_similarity_top_k < 1:
        raise VertexToolConfigurationError("vertex rag similarity_top_k must be at least 1")

    threshold = vertex_settings.rag_vector_distance_threshold
    if threshold is not None and threshold < 0:
        raise VertexToolConfigurationError("vertex rag vector distance threshold must be non-negative")
