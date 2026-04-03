"""
Purpose:
- Centralize optional Vertex AI RAG Engine configuration for chat requests.

Responsibilities:
- Validate the configured RAG corpus resources and retrieval parameters
- Build provider-compatible retrieval tool payloads for google-genai requests
- Keep RAG-specific configuration out of general chat orchestration
"""

from __future__ import annotations

from app.config.ai import ai_settings


class VertexRagConfigurationError(RuntimeError):
    """Raised when Vertex AI RAG settings are malformed."""


def is_vertex_rag_enabled() -> bool:
    return bool(ai_settings.vertex_ai_rag_corpora)


def ensure_vertex_rag_configuration_ready() -> None:
    if not is_vertex_rag_enabled():
        return

    if any(not corpus.strip() for corpus in ai_settings.vertex_ai_rag_corpora):
        raise VertexRagConfigurationError("vertex ai rag corpus resource names must not be blank")

    if ai_settings.vertex_ai_rag_similarity_top_k < 1:
        raise VertexRagConfigurationError("vertex ai rag similarity_top_k must be at least 1")

    threshold = ai_settings.vertex_ai_rag_vector_distance_threshold
    if threshold is not None and threshold < 0:
        raise VertexRagConfigurationError("vertex ai rag vector distance threshold must be non-negative")


def build_vertex_rag_tools(*, types_module=None) -> list[object]:
    ensure_vertex_rag_configuration_ready()
    if not is_vertex_rag_enabled():
        return []

    rag_store: dict[str, object] = {
        "rag_resources": [{"rag_corpus": corpus} for corpus in ai_settings.vertex_ai_rag_corpora],
        "similarity_top_k": ai_settings.vertex_ai_rag_similarity_top_k,
    }

    if ai_settings.vertex_ai_rag_vector_distance_threshold is not None:
        rag_store["vector_distance_threshold"] = ai_settings.vertex_ai_rag_vector_distance_threshold

    tool_payload = {
        "retrieval": {
            "vertex_rag_store": rag_store,
        }
    }

    tool_type = getattr(types_module, "Tool", None) if types_module is not None else None
    if tool_type is None:
        return [tool_payload]

    try:
        return [tool_type(**tool_payload)]
    except Exception:
        return [tool_payload]


__all__ = [
    "VertexRagConfigurationError",
    "build_vertex_rag_tools",
    "ensure_vertex_rag_configuration_ready",
    "is_vertex_rag_enabled",
]
