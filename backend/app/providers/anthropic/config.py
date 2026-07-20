"""Operator-facing Anthropic catalog, capability, version, and pricing configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class AnthropicModelConfig:
    public_id: str
    provider_model: str
    display_name: str
    available: bool
    supported_tool_ids: tuple[str, ...]
    allowed_reasoning_presets: tuple[str, ...]
    disable_thinking_when_none: bool = False


@dataclass(slots=True, frozen=True)
class AnthropicPriceCard:
    input_per_million_usd: float
    cache_read_per_million_usd: float
    output_per_million_usd: float


ANTHROPIC_MODELS = (
    AnthropicModelConfig(
        public_id="claude-opus-4-8",
        provider_model="claude-opus-4-8",
        display_name="Claude Opus 4.8",
        available=False,
        supported_tool_ids=("web_search", "web_fetch", "code_execution"),
        allowed_reasoning_presets=("none", "low", "normal", "high", "xhigh", "max"),
    ),
    AnthropicModelConfig(
        public_id="claude-sonnet-5",
        provider_model="claude-sonnet-5",
        display_name="Claude Sonnet 5",
        available=True,
        supported_tool_ids=("web_search", "web_fetch", "code_execution"),
        allowed_reasoning_presets=("none", "low", "normal", "high", "xhigh", "max"),
        disable_thinking_when_none=True,
    ),
    AnthropicModelConfig(
        public_id="claude-haiku-4-5",
        provider_model="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        available=True,
        supported_tool_ids=("web_search", "web_fetch", "code_execution"),
        allowed_reasoning_presets=("none",),
    ),
)
ANTHROPIC_TOOLS: tuple[tuple[str, bool], ...] = (
    ("web_search", True),
    ("web_fetch", True),
    ("code_execution", True),
)
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_WEB_SEARCH_TOOL_VERSION = "web_search_20260318"
ANTHROPIC_WEB_FETCH_TOOL_VERSION = "web_fetch_20260318"
ANTHROPIC_CODE_EXECUTION_TOOL_VERSION = "code_execution_20260521"
ANTHROPIC_DIRECT_WEB_TOOL_MODELS = frozenset({"claude-haiku-4-5"})
ANTHROPIC_FILES_BETA = "files-api-2025-04-14"
ANTHROPIC_ATTACHMENT_COUNT_MODEL_ID = "claude-haiku-4-5"
ANTHROPIC_PRICING_VERSION = "anthropic-2026-07-16"
ANTHROPIC_WEB_SEARCH_COST_PER_1K_CALLS = 10.0
ANTHROPIC_PRICE_CARDS = {
    "claude-opus-4-8": AnthropicPriceCard(5.0, 0.5, 25.0),
    "claude-sonnet-5": AnthropicPriceCard(2.0, 0.2, 10.0),
    "claude-haiku-4-5": AnthropicPriceCard(1.0, 0.1, 5.0),
}


def validate_anthropic_config() -> None:
    model_ids = {model.public_id for model in ANTHROPIC_MODELS}
    provider_model_ids = {model.provider_model for model in ANTHROPIC_MODELS}
    tool_ids = {tool_id for tool_id, _ in ANTHROPIC_TOOLS}
    if len(model_ids) != len(ANTHROPIC_MODELS) or len(provider_model_ids) != len(ANTHROPIC_MODELS):
        raise ValueError("Anthropic public and provider model ids must be unique")
    if len(tool_ids) != len(ANTHROPIC_TOOLS):
        raise ValueError("Anthropic tool ids must be unique")
    if not ANTHROPIC_API_VERSION.strip():
        raise ValueError("Anthropic API version must not be blank")
    if set(ANTHROPIC_PRICE_CARDS) != model_ids:
        raise ValueError("Anthropic pricing must cover every model")
    if any(not set(model.supported_tool_ids) <= tool_ids for model in ANTHROPIC_MODELS):
        raise ValueError("Anthropic model references an unknown tool")
    if any(not model.allowed_reasoning_presets for model in ANTHROPIC_MODELS):
        raise ValueError("Anthropic models must declare at least one allowed reasoning preset")
    if ANTHROPIC_ATTACHMENT_COUNT_MODEL_ID not in model_ids:
        raise ValueError("Anthropic attachment count model must be in the public model catalog")
    if any(
        value < 0
        for card in ANTHROPIC_PRICE_CARDS.values()
        for value in (
            card.input_per_million_usd,
            card.cache_read_per_million_usd,
            card.output_per_million_usd,
        )
    ):
        raise ValueError("Anthropic price card values must not be negative")


def get_anthropic_model_config(provider_model: str) -> AnthropicModelConfig:
    for model in ANTHROPIC_MODELS:
        if model.provider_model == provider_model:
            return model
    raise ValueError(f"missing Anthropic model configuration: {provider_model}")


validate_anthropic_config()
