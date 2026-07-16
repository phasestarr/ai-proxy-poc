from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.providers.types import ProviderPriceEstimate, ProviderUsageMetadata

VERTEX_PRICING_VERSION = "vertex-2026-07-16"
_VERTEX_GOOGLE_SEARCH_COST_PER_1K_QUERIES = 14.0
_VERTEX_RETRIEVAL_COST_PER_1K_PROMPTS = 2.5


@dataclass(slots=True, frozen=True)
class _VertexPriceCard:
    input_per_million_usd: float
    input_per_million_long_context_usd: float | None
    cached_input_per_million_usd: float | None
    cached_input_per_million_long_context_usd: float | None
    output_per_million_usd: float
    output_per_million_long_context_usd: float | None


_VERTEX_PRICE_CARDS: dict[str, _VertexPriceCard] = {
    "gemini-3.5-flash": _VertexPriceCard(
        input_per_million_usd=1.5,
        input_per_million_long_context_usd=1.5,
        cached_input_per_million_usd=0.15,
        cached_input_per_million_long_context_usd=0.15,
        output_per_million_usd=9.0,
        output_per_million_long_context_usd=9.0,
    ),
    "gemini-3.1-pro-preview": _VertexPriceCard(
        input_per_million_usd=2.0,
        input_per_million_long_context_usd=4.0,
        cached_input_per_million_usd=0.2,
        cached_input_per_million_long_context_usd=0.4,
        output_per_million_usd=12.0,
        output_per_million_long_context_usd=18.0,
    ),
    "gemini-3-flash-preview": _VertexPriceCard(
        input_per_million_usd=0.5,
        input_per_million_long_context_usd=0.5,
        cached_input_per_million_usd=0.05,
        cached_input_per_million_long_context_usd=0.05,
        output_per_million_usd=3.0,
        output_per_million_long_context_usd=3.0,
    ),
}


def map_vertex_usage(
    usage,
    *,
    public_model_id: str,
    selected_tool_ids: Iterable[str] = (),
) -> ProviderUsageMetadata | None:
    if usage is None:
        return None

    prompt_token_count = _optional_int(getattr(usage, "prompt_token_count", None))
    candidates_token_count = _optional_int(getattr(usage, "candidates_token_count", None))
    total_token_count = _optional_int(getattr(usage, "total_token_count", None))
    cached_content_token_count = _optional_int(getattr(usage, "cached_content_token_count", None))
    tool_use_prompt_token_count = _optional_int(getattr(usage, "tool_use_prompt_token_count", None))
    thoughts_token_count = _optional_int(getattr(usage, "thoughts_token_count", None))
    if (
        prompt_token_count is None
        and candidates_token_count is None
        and total_token_count is None
        and cached_content_token_count is None
    ):
        return None

    return ProviderUsageMetadata(
        prompt_token_count=prompt_token_count,
        candidates_token_count=candidates_token_count,
        total_token_count=total_token_count,
        cache_read_input_tokens=cached_content_token_count,
        reasoning_token_count=thoughts_token_count,
        tool_result_prompt_token_count=tool_use_prompt_token_count,
        provider_raw_usage=_serialize_raw_usage(usage),
        price_estimate=estimate_vertex_price(
            public_model_id=public_model_id,
            selected_tool_ids=selected_tool_ids,
            prompt_token_count=prompt_token_count,
            candidates_token_count=candidates_token_count,
            cached_content_token_count=cached_content_token_count,
        ),
    )


def estimate_vertex_price(
    *,
    public_model_id: str,
    selected_tool_ids: Iterable[str],
    prompt_token_count: int | None,
    candidates_token_count: int | None,
    cached_content_token_count: int | None,
) -> ProviderPriceEstimate:
    price_card = _VERTEX_PRICE_CARDS.get(public_model_id)
    notes: list[str] = []
    completeness = "complete"
    if price_card is None:
        notes.append(f"missing Vertex price card for model {public_model_id}")
        completeness = "partial"
        input_cost = 0.0
        output_cost = 0.0
        cached_input_cost = 0.0
    else:
        prompt_tokens = max(int(prompt_token_count or 0), 0)
        cached_tokens = max(int(cached_content_token_count or 0), 0)
        regular_prompt_tokens = max(prompt_tokens - cached_tokens, 0)
        use_long_context_rates = prompt_tokens > 200_000
        input_rate = price_card.input_per_million_long_context_usd if use_long_context_rates else price_card.input_per_million_usd
        cached_rate = (
            price_card.cached_input_per_million_long_context_usd
            if use_long_context_rates
            else price_card.cached_input_per_million_usd
        )
        output_rate = (
            price_card.output_per_million_long_context_usd
            if use_long_context_rates
            else price_card.output_per_million_usd
        )
        input_cost = _cost_for_tokens(regular_prompt_tokens, input_rate or 0.0)
        cached_input_cost = _cost_for_tokens(cached_tokens, cached_rate or 0.0)
        output_cost = _cost_for_tokens(max(int(candidates_token_count or 0), 0), output_rate or 0.0)

    selected_tool_ids_set = {tool_id for tool_id in selected_tool_ids if tool_id}
    tool_cost = 0.0
    if "retrieval" in selected_tool_ids_set:
        tool_cost += _VERTEX_RETRIEVAL_COST_PER_1K_PROMPTS / 1000.0
    if "google_search" in selected_tool_ids_set:
        completeness = "partial"
        notes.append("Vertex Google Search billing depends on query counts that are not exposed in response usage.")
    if "code_execution" in selected_tool_ids_set:
        completeness = "partial"
        notes.append("Vertex code execution runtime billing is not derivable from response usage.")
    if "url_context" in selected_tool_ids_set:
        completeness = "partial"
        notes.append("Vertex URL context billing is not modeled in the current price estimator.")
    if "google_maps" in selected_tool_ids_set:
        completeness = "partial"
        notes.append("Vertex Google Maps billing depends on query counts that are not exposed in response usage.")

    total_cost = input_cost + cached_input_cost + output_cost + tool_cost
    return ProviderPriceEstimate(
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        cache_read_cost_usd=cached_input_cost,
        tool_cost_usd=tool_cost,
        total_cost_usd=total_cost,
        pricing_version=VERTEX_PRICING_VERSION,
        completeness=completeness,
        notes=tuple(notes),
    )


def _serialize_raw_usage(usage) -> dict[str, object] | None:
    if usage is None:
        return None
    model_dump = getattr(usage, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", exclude_none=True)
    return {
        "prompt_token_count": getattr(usage, "prompt_token_count", None),
        "candidates_token_count": getattr(usage, "candidates_token_count", None),
        "total_token_count": getattr(usage, "total_token_count", None),
        "cached_content_token_count": getattr(usage, "cached_content_token_count", None),
        "tool_use_prompt_token_count": getattr(usage, "tool_use_prompt_token_count", None),
        "thoughts_token_count": getattr(usage, "thoughts_token_count", None),
    }


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cost_for_tokens(token_count: int, price_per_million_usd: float) -> float:
    return token_count * price_per_million_usd / 1_000_000.0
