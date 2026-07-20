"""Frequently adjusted Anthropic request and hosted-tool options."""

from __future__ import annotations

from app.providers.anthropic.config import ANTHROPIC_MODELS

ANTHROPIC_REASONING_PRESETS: dict[str, dict[str, object]] = {
    "none": {"thinking": None, "output_config": None},
    "low": {"thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "low"}},
    "normal": {"thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "medium"}},
    "high": {"thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "high"}},
    "xhigh": {"thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "xhigh"}},
    "max": {"thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "max"}},
}

ANTHROPIC_MODEL_REASONING_PRESET: dict[str, str] = {
    "claude-opus-4-8": "max",
    "claude-sonnet-5": "xhigh",
    "claude-haiku-4-5": "none",
}

ANTHROPIC_MODEL_MAX_TOKENS: dict[str, int] = {
    "claude-opus-4-8": 128_000,
    "claude-sonnet-5": 128_000,
    "claude-haiku-4-5": 64_000,
}

ANTHROPIC_TOOL_OPTIONS: dict[str, dict[str, object]] = {
    "web_search": {
        "max_uses": 5,
        "allowed_domains": None,
        "blocked_domains": None,
    },
    "web_fetch": {
        "max_uses": 5,
        "max_content_tokens": 50_000,
        "citations": {"enabled": True},
    },
    "code_execution": {},
}


def validate_anthropic_options() -> None:
    provider_models = {model.provider_model: model for model in ANTHROPIC_MODELS}
    if set(ANTHROPIC_MODEL_REASONING_PRESET) != set(provider_models):
        raise ValueError("Anthropic reasoning presets must cover every configured provider model")
    if set(ANTHROPIC_MODEL_MAX_TOKENS) != set(provider_models):
        raise ValueError("Anthropic output token caps must cover every configured provider model")
    for provider_model, preset in ANTHROPIC_MODEL_REASONING_PRESET.items():
        if preset not in ANTHROPIC_REASONING_PRESETS:
            raise ValueError(f"unknown Anthropic reasoning preset: {preset}")
        if preset not in provider_models[provider_model].allowed_reasoning_presets:
            raise ValueError(f"Anthropic reasoning preset {preset!r} is not supported by {provider_model}")
    if any(value < 1 for value in ANTHROPIC_MODEL_MAX_TOKENS.values()):
        raise ValueError("Anthropic output token caps must be positive")
    web_search_options = ANTHROPIC_TOOL_OPTIONS.get("web_search", {})
    if int(web_search_options.get("max_uses") or 0) < 1:
        raise ValueError("Anthropic web_search max_uses must be positive")
    if web_search_options.get("allowed_domains") and web_search_options.get("blocked_domains"):
        raise ValueError("Anthropic web search cannot configure allowed and blocked domains together")
    web_fetch_options = ANTHROPIC_TOOL_OPTIONS.get("web_fetch", {})
    if int(web_fetch_options.get("max_uses") or 0) < 1:
        raise ValueError("Anthropic web_fetch max_uses must be positive")
    if int(web_fetch_options.get("max_content_tokens") or 0) < 1:
        raise ValueError("Anthropic web_fetch max_content_tokens must be positive")


validate_anthropic_options()
