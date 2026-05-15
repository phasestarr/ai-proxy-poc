from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.config.providers.openai import openai_settings
from app.providers.types import ProviderPriceEstimate, ProviderUsageMetadata

OPENAI_PRICING_VERSION = "openai-2026-05-11"
_OPENAI_WEB_SEARCH_COST_PER_1K_CALLS = 10.0
_OPENAI_FILE_SEARCH_COST_PER_1K_CALLS = 2.5
_OPENAI_CODE_INTERPRETER_COST_BY_MEMORY_LIMIT = {
    "1g": 0.03,
    "4g": 0.12,
    "16g": 0.48,
    "64g": 1.92,
}


@dataclass(slots=True, frozen=True)
class _OpenAIPriceCard:
    input_per_million_usd: float
    cached_input_per_million_usd: float
    output_per_million_usd: float


_OPENAI_PRICE_CARDS: dict[str, _OpenAIPriceCard] = {
    "gpt-5.4": _OpenAIPriceCard(input_per_million_usd=2.5, cached_input_per_million_usd=0.25, output_per_million_usd=15.0),
    "gpt-5.4-mini": _OpenAIPriceCard(input_per_million_usd=0.75, cached_input_per_million_usd=0.075, output_per_million_usd=4.5),
    "gpt-5.4-nano": _OpenAIPriceCard(input_per_million_usd=0.2, cached_input_per_million_usd=0.02, output_per_million_usd=1.25),
}


def map_openai_usage(
    usage,
    *,
    public_model_id: str,
    selected_tool_ids: Iterable[str] = (),
    response_output: object = None,
) -> ProviderUsageMetadata | None:
    if usage is None:
        return None

    input_tokens = _optional_int(getattr(usage, "input_tokens", None))
    output_tokens = _optional_int(getattr(usage, "output_tokens", None))
    total_tokens = _optional_int(getattr(usage, "total_tokens", None))
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None

    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    cached_input_tokens = _optional_int(getattr(input_details, "cached_tokens", None))
    reasoning_tokens = _optional_int(getattr(output_details, "reasoning_tokens", None))
    tool_counts = _count_response_tool_calls(response_output)

    return ProviderUsageMetadata(
        prompt_token_count=input_tokens,
        candidates_token_count=output_tokens,
        total_token_count=total_tokens,
        cache_read_input_tokens=cached_input_tokens,
        reasoning_token_count=reasoning_tokens,
        web_search_request_count=tool_counts["web_search"],
        file_search_request_count=tool_counts["file_search"],
        code_execution_request_count=tool_counts["code_execution"],
        provider_raw_usage=_serialize_raw_usage(usage),
        price_estimate=estimate_openai_price(
            public_model_id=public_model_id,
            selected_tool_ids=selected_tool_ids,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            web_search_request_count=tool_counts["web_search"],
            file_search_request_count=tool_counts["file_search"],
            code_execution_request_count=tool_counts["code_execution"],
        ),
    )


def estimate_openai_price(
    *,
    public_model_id: str,
    selected_tool_ids: Iterable[str],
    input_tokens: int | None,
    output_tokens: int | None,
    cached_input_tokens: int | None,
    web_search_request_count: int | None,
    file_search_request_count: int | None,
    code_execution_request_count: int | None,
) -> ProviderPriceEstimate:
    del selected_tool_ids

    price_card = _OPENAI_PRICE_CARDS.get(public_model_id)
    if price_card is None:
        return ProviderPriceEstimate(
            pricing_version=OPENAI_PRICING_VERSION,
            completeness="partial",
            notes=(f"missing OpenAI price card for model {public_model_id}",),
        )

    cached_tokens = max(int(cached_input_tokens or 0), 0)
    reported_input_tokens = max(int(input_tokens or 0), 0)
    uncached_input_tokens = max(reported_input_tokens - cached_tokens, 0)
    output_token_count = max(int(output_tokens or 0), 0)
    web_search_calls = max(int(web_search_request_count or 0), 0)
    file_search_calls = max(int(file_search_request_count or 0), 0)
    code_execution_calls = max(int(code_execution_request_count or 0), 0)

    input_cost = _cost_for_tokens(uncached_input_tokens, price_card.input_per_million_usd)
    cached_input_cost = _cost_for_tokens(cached_tokens, price_card.cached_input_per_million_usd)
    output_cost = _cost_for_tokens(output_token_count, price_card.output_per_million_usd)
    tool_cost = (
        (web_search_calls * _OPENAI_WEB_SEARCH_COST_PER_1K_CALLS / 1000.0)
        + (file_search_calls * _OPENAI_FILE_SEARCH_COST_PER_1K_CALLS / 1000.0)
        + ((1 if code_execution_calls > 0 else 0) * _OPENAI_CODE_INTERPRETER_COST_BY_MEMORY_LIMIT[openai_settings.code_interpreter_memory_limit])
    )
    total_cost = input_cost + cached_input_cost + output_cost + tool_cost
    return ProviderPriceEstimate(
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        cache_read_cost_usd=cached_input_cost,
        tool_cost_usd=tool_cost,
        total_cost_usd=total_cost,
        pricing_version=OPENAI_PRICING_VERSION,
    )


def _count_response_tool_calls(response_output: object) -> dict[str, int]:
    counts = {
        "web_search": 0,
        "file_search": 0,
        "code_execution": 0,
    }
    for item in response_output or []:
        item_type = _extract_item_type(item)
        if item_type.endswith("web_search_call"):
            counts["web_search"] += 1
        elif item_type.endswith("file_search_call"):
            counts["file_search"] += 1
        elif item_type.endswith("code_interpreter_call"):
            counts["code_execution"] += 1
    return counts


def _extract_item_type(item: object) -> str:
    if isinstance(item, dict):
        return str(item.get("type") or "")
    return str(getattr(item, "type", None) or "")


def _serialize_raw_usage(usage) -> dict[str, object] | None:
    if usage is None:
        return None
    model_dump = getattr(usage, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", exclude_none=True)
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
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
