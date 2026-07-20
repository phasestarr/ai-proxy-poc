"""Frequently adjusted Vertex request and hosted-tool options."""

from __future__ import annotations

from app.providers.vertex.config import VERTEX_MODELS

VERTEX_RESPONSE_PRESETS: dict[str, dict[str, object]] = {
    "minimal": {"thinking_config": {"thinking_level": "MINIMAL", "include_thoughts": False}},
    "low": {"thinking_config": {"thinking_level": "LOW", "include_thoughts": False}},
    "normal": {"thinking_config": {"thinking_level": "MEDIUM", "include_thoughts": False}},
    "high": {"thinking_config": {"thinking_level": "HIGH", "include_thoughts": True}},
}

VERTEX_MODEL_RESPONSE_PRESET: dict[str, str] = {
    "gemini-3.5-flash": "high",
    "gemini-3.1-pro-preview": "high",
    "gemini-3-flash-preview": "high",
}

VERTEX_MODEL_MAX_OUTPUT_TOKENS: dict[str, int] = {
    "gemini-3.5-flash": 65_535,
    "gemini-3.1-pro-preview": 65_536,
    "gemini-3-flash-preview": 65_536,
}

VERTEX_TOOL_OPTIONS: dict[str, dict[str, object]] = {
    "retrieval": {
        "similarity_top_k": 5,
        "vector_distance_threshold": None,
    },
}


def validate_vertex_options() -> None:
    provider_models = {model.provider_model: model for model in VERTEX_MODELS}
    if set(VERTEX_MODEL_RESPONSE_PRESET) != set(provider_models):
        raise ValueError("Vertex response presets must cover every configured provider model")
    if set(VERTEX_MODEL_MAX_OUTPUT_TOKENS) != set(provider_models):
        raise ValueError("Vertex output token caps must cover every configured provider model")
    for provider_model, preset in VERTEX_MODEL_RESPONSE_PRESET.items():
        if preset not in VERTEX_RESPONSE_PRESETS:
            raise ValueError(f"unknown Vertex response preset: {preset}")
        if preset not in provider_models[provider_model].allowed_response_presets:
            raise ValueError(f"Vertex response preset {preset!r} is not supported by {provider_model}")
    if any(value < 1 for value in VERTEX_MODEL_MAX_OUTPUT_TOKENS.values()):
        raise ValueError("Vertex output token caps must be positive")
    retrieval_options = VERTEX_TOOL_OPTIONS.get("retrieval", {})
    if int(retrieval_options.get("similarity_top_k") or 0) < 1:
        raise ValueError("Vertex retrieval similarity_top_k must be positive")
    threshold = retrieval_options.get("vector_distance_threshold")
    if threshold is not None and float(threshold) < 0:
        raise ValueError("Vertex retrieval vector_distance_threshold must not be negative")


validate_vertex_options()
