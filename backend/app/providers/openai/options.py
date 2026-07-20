"""Frequently adjusted OpenAI request and hosted-tool options."""

from __future__ import annotations

from app.providers.openai.config import OPENAI_MODELS

OPENAI_REQUEST_DEFAULTS: dict[str, object] = {"store": False}

OPENAI_RESPONSE_PRESETS: dict[str, dict[str, object]] = {
    "none": {"reasoning": {"effort": "none", "summary": "auto"}, "text": {"verbosity": "low"}},
    "low": {"reasoning": {"effort": "low", "summary": "auto"}, "text": {"verbosity": "low"}},
    "normal": {"reasoning": {"effort": "medium", "summary": "auto"}, "text": {"verbosity": "medium"}},
    "high": {"reasoning": {"effort": "high", "summary": "detailed"}, "text": {"verbosity": "medium"}},
    "xhigh": {"reasoning": {"effort": "xhigh", "summary": "detailed"}, "text": {"verbosity": "high"}},
    "max": {"reasoning": {"effort": "max", "summary": "detailed"}, "text": {"verbosity": "high"}},
}

OPENAI_MODEL_RESPONSE_PRESET: dict[str, str] = {
    "gpt-5.6-sol": "max",
    "gpt-5.6-terra": "xhigh",
    "gpt-5.6-luna": "high",
    "gpt-5.4-mini": "high",
}

OPENAI_MODEL_MAX_OUTPUT_TOKENS: dict[str, int] = {
    "gpt-5.6-sol": 128_000,
    "gpt-5.6-terra": 128_000,
    "gpt-5.6-luna": 128_000,
    "gpt-5.4-mini": 128_000,
}

OPENAI_TOOL_OPTIONS: dict[str, dict[str, object]] = {
    "web_search": {
        "type": "web_search",
        "filters": None,
        "search_context_size": None,
        "user_location": None,
    },
    "file_search": {
        "filters": None,
        "max_num_results": 5,
        "ranking_options": {
            "score_threshold": None,
            "ranker": None,
        },
    },
    "code_interpreter": {
        "container": {
            "type": "auto",
            "memory_limit": "4g",
        },
    },
    "shell": {
        "environment": {"type": "container_auto"},
    },
}

OPENAI_IMAGE_DETAIL = "high"


def validate_openai_options() -> None:
    provider_models = {model.provider_model: model for model in OPENAI_MODELS}
    if set(OPENAI_MODEL_RESPONSE_PRESET) != set(provider_models):
        raise ValueError("OpenAI response presets must cover every configured provider model")
    if set(OPENAI_MODEL_MAX_OUTPUT_TOKENS) != set(provider_models):
        raise ValueError("OpenAI output token caps must cover every configured provider model")
    for provider_model, preset in OPENAI_MODEL_RESPONSE_PRESET.items():
        if preset not in OPENAI_RESPONSE_PRESETS:
            raise ValueError(f"unknown OpenAI response preset: {preset}")
        if preset not in provider_models[provider_model].allowed_response_presets:
            raise ValueError(f"OpenAI response preset {preset!r} is not supported by {provider_model}")
    if any(value < 1 for value in OPENAI_MODEL_MAX_OUTPUT_TOKENS.values()):
        raise ValueError("OpenAI output token caps must be positive")
    file_search_options = OPENAI_TOOL_OPTIONS.get("file_search", {})
    max_num_results = file_search_options.get("max_num_results") if isinstance(file_search_options, dict) else None
    if not isinstance(max_num_results, int) or not 1 <= max_num_results <= 50:
        raise ValueError("OpenAI file_search max_num_results must be between 1 and 50")
    ranking_options = file_search_options.get("ranking_options", {})
    if not isinstance(ranking_options, dict):
        raise ValueError("OpenAI file_search ranking_options must be a mapping")
    score_threshold = ranking_options.get("score_threshold")
    if score_threshold is not None and not 0 <= float(score_threshold) <= 1:
        raise ValueError("OpenAI file_search score_threshold must be between 0 and 1")
    memory_limit = OPENAI_TOOL_OPTIONS.get("code_interpreter", {}).get("container", {})
    if not isinstance(memory_limit, dict) or memory_limit.get("memory_limit") not in {"1g", "4g", "16g", "64g"}:
        raise ValueError("OpenAI code interpreter memory_limit must be one of 1g, 4g, 16g, or 64g")
    if OPENAI_IMAGE_DETAIL not in {"auto", "low", "high"}:
        raise ValueError("OpenAI image detail must be auto, low, or high")


validate_openai_options()
