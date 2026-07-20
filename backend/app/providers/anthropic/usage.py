from __future__ import annotations

from collections.abc import Iterable

from app.providers.anthropic.config import (
    ANTHROPIC_PRICE_CARDS as _ANTHROPIC_PRICE_CARDS,
    ANTHROPIC_PRICING_VERSION,
    ANTHROPIC_WEB_SEARCH_COST_PER_1K_CALLS as _ANTHROPIC_WEB_SEARCH_COST_PER_1K_CALLS,
)
from app.providers.types import ProviderPriceEstimate, ProviderUsageMetadata


def map_anthropic_usage(
    usage,
    *,
    public_model_id: str,
    selected_tool_ids: Iterable[str] = (),
) -> ProviderUsageMetadata | None:
    if usage is None:
        return None

    input_tokens = _optional_int(getattr(usage, "input_tokens", None))
    output_tokens = _optional_int(getattr(usage, "output_tokens", None))
    cache_read_input_tokens = _optional_int(getattr(usage, "cache_read_input_tokens", None))
    cache_write_input_tokens = _optional_int(getattr(usage, "cache_creation_input_tokens", None))
    server_tool_use = getattr(usage, "server_tool_use", None)
    web_search_request_count = _optional_int(getattr(server_tool_use, "web_search_requests", None))
    web_fetch_request_count = _optional_int(getattr(server_tool_use, "web_fetch_requests", None))
    if input_tokens is None and output_tokens is None and cache_read_input_tokens is None and cache_write_input_tokens is None:
        return None

    total_tokens = None
    if input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    return ProviderUsageMetadata(
        prompt_token_count=input_tokens,
        candidates_token_count=output_tokens,
        total_token_count=total_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
        cache_write_input_tokens=cache_write_input_tokens,
        web_search_request_count=web_search_request_count,
        web_fetch_request_count=web_fetch_request_count,
        provider_raw_usage=_serialize_raw_usage(usage),
        price_estimate=estimate_anthropic_price(
            public_model_id=public_model_id,
            selected_tool_ids=selected_tool_ids,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            cache_write_input_tokens=cache_write_input_tokens,
            web_search_request_count=web_search_request_count,
        ),
    )


def estimate_anthropic_price(
    *,
    public_model_id: str,
    selected_tool_ids: Iterable[str],
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_input_tokens: int | None,
    cache_write_input_tokens: int | None,
    web_search_request_count: int | None,
) -> ProviderPriceEstimate:
    price_card = _ANTHROPIC_PRICE_CARDS.get(public_model_id)
    notes: list[str] = []
    completeness = "complete"
    if price_card is None:
        return ProviderPriceEstimate(
            pricing_version=ANTHROPIC_PRICING_VERSION,
            completeness="partial",
            notes=(f"missing Anthropic price card for model {public_model_id}",),
        )

    if "code_execution" in set(selected_tool_ids):
        completeness = "partial"
        notes.append("Anthropic code execution session-hour billing is not derivable from response usage.")

    if int(cache_write_input_tokens or 0) > 0:
        completeness = "partial"
        notes.append("Anthropic cache creation tokens are recorded, but cache write pricing tier is not configured.")

    input_cost = _cost_for_tokens(max(int(input_tokens or 0), 0), price_card.input_per_million_usd)
    cache_read_cost = _cost_for_tokens(max(int(cache_read_input_tokens or 0), 0), price_card.cache_read_per_million_usd)
    output_cost = _cost_for_tokens(max(int(output_tokens or 0), 0), price_card.output_per_million_usd)
    tool_cost = max(int(web_search_request_count or 0), 0) * _ANTHROPIC_WEB_SEARCH_COST_PER_1K_CALLS / 1000.0
    total_cost = input_cost + cache_read_cost + output_cost + tool_cost
    return ProviderPriceEstimate(
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        cache_read_cost_usd=cache_read_cost,
        tool_cost_usd=tool_cost,
        total_cost_usd=total_cost,
        pricing_version=ANTHROPIC_PRICING_VERSION,
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
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
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
