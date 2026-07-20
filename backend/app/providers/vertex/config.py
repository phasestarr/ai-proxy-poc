"""Operator-facing Vertex catalog, capability, version, and pricing configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class VertexModelConfig:
    public_id: str
    provider_model: str
    display_name: str
    location: str
    available: bool
    supported_tool_ids: tuple[str, ...]
    allowed_response_presets: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class VertexPriceCard:
    input_per_million_usd: float
    input_per_million_long_context_usd: float | None
    cached_input_per_million_usd: float | None
    cached_input_per_million_long_context_usd: float | None
    output_per_million_usd: float
    output_per_million_long_context_usd: float | None


_ALL_TOOL_IDS = ("google_search", "url_context", "code_execution", "google_maps", "retrieval")
VERTEX_MODELS = (
    VertexModelConfig(
        public_id="gemini-3.5-flash",
        provider_model="gemini-3.5-flash",
        display_name="Gemini 3.5 Flash",
        location="global",
        available=True,
        supported_tool_ids=_ALL_TOOL_IDS,
        allowed_response_presets=("minimal", "low", "normal", "high"),
    ),
    VertexModelConfig(
        public_id="gemini-3.1-pro-preview",
        provider_model="gemini-3.1-pro-preview",
        display_name="Gemini 3.1 Pro Preview",
        location="global",
        available=True,
        supported_tool_ids=_ALL_TOOL_IDS,
        allowed_response_presets=("low", "normal", "high"),
    ),
    VertexModelConfig(
        public_id="gemini-3-flash-preview",
        provider_model="gemini-3-flash-preview",
        display_name="Gemini 3 Flash Preview",
        location="global",
        available=True,
        supported_tool_ids=_ALL_TOOL_IDS,
        allowed_response_presets=("minimal", "low", "normal", "high"),
    ),
)
VERTEX_TOOLS: tuple[tuple[str, bool], ...] = tuple((tool_id, True) for tool_id in _ALL_TOOL_IDS)
VERTEX_API_VERSION = "v1"
VERTEX_ATTACHMENT_COUNT_MODEL_ID = "gemini-3-flash-preview"
VERTEX_PRICING_VERSION = "vertex-2026-07-16"
VERTEX_GOOGLE_SEARCH_COST_PER_1K_QUERIES = 14.0
VERTEX_RETRIEVAL_COST_PER_1K_PROMPTS = 2.5
VERTEX_LONG_CONTEXT_PRICE_THRESHOLD = 200_000
VERTEX_PRICE_CARDS = {
    "gemini-3.5-flash": VertexPriceCard(1.5, 1.5, 0.15, 0.15, 9.0, 9.0),
    "gemini-3.1-pro-preview": VertexPriceCard(2.0, 4.0, 0.2, 0.4, 12.0, 18.0),
    "gemini-3-flash-preview": VertexPriceCard(0.5, 0.5, 0.05, 0.05, 3.0, 3.0),
}


def validate_vertex_config() -> None:
    model_ids = {model.public_id for model in VERTEX_MODELS}
    provider_model_ids = {model.provider_model for model in VERTEX_MODELS}
    tool_ids = {tool_id for tool_id, _ in VERTEX_TOOLS}
    if len(model_ids) != len(VERTEX_MODELS) or len(provider_model_ids) != len(VERTEX_MODELS):
        raise ValueError("Vertex public and provider model ids must be unique")
    if len(tool_ids) != len(VERTEX_TOOLS):
        raise ValueError("Vertex tool ids must be unique")
    if not VERTEX_API_VERSION.strip():
        raise ValueError("Vertex API version must not be blank")
    if set(VERTEX_PRICE_CARDS) != model_ids:
        raise ValueError("Vertex pricing must cover every model")
    if any(not set(model.supported_tool_ids) <= tool_ids for model in VERTEX_MODELS):
        raise ValueError("Vertex model references an unknown tool")
    if any(not model.allowed_response_presets for model in VERTEX_MODELS):
        raise ValueError("Vertex models must declare at least one allowed response preset")
    if VERTEX_ATTACHMENT_COUNT_MODEL_ID not in model_ids:
        raise ValueError("Vertex attachment count model must be in the public model catalog")
    if any(
        value is not None and value < 0
        for card in VERTEX_PRICE_CARDS.values()
        for value in (
            card.input_per_million_usd,
            card.input_per_million_long_context_usd,
            card.cached_input_per_million_usd,
            card.cached_input_per_million_long_context_usd,
            card.output_per_million_usd,
            card.output_per_million_long_context_usd,
        )
    ):
        raise ValueError("Vertex price card values must not be negative")


def get_vertex_model_config(provider_model: str) -> VertexModelConfig:
    for model in VERTEX_MODELS:
        if model.provider_model == provider_model:
            return model
    raise ValueError(f"missing Vertex model configuration: {provider_model}")


validate_vertex_config()
