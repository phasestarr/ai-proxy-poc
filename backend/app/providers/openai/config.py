"""Operator-facing OpenAI catalog, capability, version, and pricing configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class OpenAIModelConfig:
    public_id: str
    provider_model: str
    display_name: str
    available: bool
    supported_tool_ids: tuple[str, ...]
    allowed_response_presets: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class OpenAIPriceCard:
    input_per_million_usd: float
    cached_input_per_million_usd: float
    output_per_million_usd: float
    long_context_threshold: int | None = None
    long_context_input_multiplier: float = 1.0
    long_context_output_multiplier: float = 1.0


OPENAI_MODELS: tuple[OpenAIModelConfig, ...] = (
    OpenAIModelConfig(
        public_id="gpt-5.6-sol",
        provider_model="gpt-5.6-sol",
        display_name="GPT-5.6 Sol",
        available=False,
        supported_tool_ids=("web_search", "code_interpreter", "shell", "file_search"),
        allowed_response_presets=("none", "low", "normal", "high", "xhigh", "max"),
    ),
    OpenAIModelConfig(
        public_id="gpt-5.6-terra",
        provider_model="gpt-5.6-terra",
        display_name="GPT-5.6 Terra",
        available=True,
        supported_tool_ids=("web_search", "code_interpreter", "shell", "file_search"),
        allowed_response_presets=("none", "low", "normal", "high", "xhigh", "max"),
    ),
    OpenAIModelConfig(
        public_id="gpt-5.6-luna",
        provider_model="gpt-5.6-luna",
        display_name="GPT-5.6 Luna",
        available=True,
        supported_tool_ids=("web_search", "code_interpreter", "shell", "file_search"),
        allowed_response_presets=("none", "low", "normal", "high", "xhigh", "max"),
    ),
    OpenAIModelConfig(
        public_id="gpt-5.4-mini",
        provider_model="gpt-5.4-mini",
        display_name="GPT-5.4 Mini",
        available=True,
        supported_tool_ids=("web_search", "code_interpreter", "shell", "file_search"),
        allowed_response_presets=("none", "low", "normal", "high", "xhigh"),
    ),
)

OPENAI_TOOLS: tuple[tuple[str, bool], ...] = (
    ("web_search", True),
    ("file_search", True),
    ("code_interpreter", True),
    ("shell", True),
)

OPENAI_ATTACHMENT_COUNT_MODEL_ID = "gpt-5.4-mini"
OPENAI_PRICING_VERSION = "openai-2026-07-16"
OPENAI_WEB_SEARCH_COST_PER_1K_CALLS = 10.0
OPENAI_FILE_SEARCH_COST_PER_1K_CALLS = 2.5
OPENAI_CODE_INTERPRETER_COST_BY_MEMORY_LIMIT = {"1g": 0.03, "4g": 0.12, "16g": 0.48, "64g": 1.92}
OPENAI_PRICE_CARDS = {
    "gpt-5.6-sol": OpenAIPriceCard(5.0, 0.5, 30.0, 272_000, 2.0, 1.5),
    "gpt-5.6-terra": OpenAIPriceCard(2.5, 0.25, 15.0, 272_000, 2.0, 1.5),
    "gpt-5.6-luna": OpenAIPriceCard(1.0, 0.1, 6.0, 272_000, 2.0, 1.5),
    "gpt-5.4-mini": OpenAIPriceCard(0.75, 0.075, 4.5),
}


def validate_openai_config() -> None:
    model_ids = {model.public_id for model in OPENAI_MODELS}
    provider_model_ids = {model.provider_model for model in OPENAI_MODELS}
    tool_ids = {tool_id for tool_id, _ in OPENAI_TOOLS}
    if len(model_ids) != len(OPENAI_MODELS) or len(provider_model_ids) != len(OPENAI_MODELS):
        raise ValueError("OpenAI public and provider model ids must be unique")
    if len(tool_ids) != len(OPENAI_TOOLS):
        raise ValueError("OpenAI tool ids must be unique")
    if set(OPENAI_PRICE_CARDS) != model_ids:
        raise ValueError("OpenAI pricing must cover every model")
    if any(not set(model.supported_tool_ids) <= tool_ids for model in OPENAI_MODELS):
        raise ValueError("OpenAI model references an unknown tool")
    if any(not model.allowed_response_presets for model in OPENAI_MODELS):
        raise ValueError("OpenAI models must declare at least one allowed response preset")
    if OPENAI_ATTACHMENT_COUNT_MODEL_ID not in model_ids:
        raise ValueError("OpenAI attachment count model must be in the public model catalog")
    if any(
        value < 0
        for card in OPENAI_PRICE_CARDS.values()
        for value in (
            card.input_per_million_usd,
            card.cached_input_per_million_usd,
            card.output_per_million_usd,
        )
    ):
        raise ValueError("OpenAI price card values must not be negative")


validate_openai_config()
