from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.postgres.models.chat_history import ChatHistory, ChatMessage
from app.providers.types import ProviderPriceEstimate, ProviderUsageMetadata

_NORMALIZED_USAGE_KEYS: tuple[str, ...] = (
    "input_tokens_reported",
    "output_tokens_reported",
    "total_tokens_reported",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "reasoning_tokens",
    "tool_result_input_tokens",
    "web_search_requests",
    "file_search_requests",
    "code_execution_requests",
)

_SUMMARY_TOTAL_KEY_MAP: tuple[tuple[str, str], ...] = tuple(
    (key, f"{key}_total")
    for key in _NORMALIZED_USAGE_KEYS
)


def serialize_provider_usage(usage: ProviderUsageMetadata | None) -> dict[str, object] | None:
    if usage is None:
        return None

    payload: dict[str, object] = {
        "normalized": {
            "input_tokens_reported": usage.prompt_token_count,
            "output_tokens_reported": usage.candidates_token_count,
            "total_tokens_reported": usage.total_token_count,
            "cached_input_tokens": usage.cache_read_input_tokens,
            "cache_write_input_tokens": usage.cache_write_input_tokens,
            "reasoning_tokens": usage.reasoning_token_count,
            "tool_result_input_tokens": usage.tool_result_prompt_token_count,
            "web_search_requests": usage.web_search_request_count,
            "file_search_requests": usage.file_search_request_count,
            "code_execution_requests": usage.code_execution_request_count,
        }
    }

    price_estimate = serialize_price_estimate(usage.price_estimate)
    if price_estimate is not None:
        payload["price_estimate"] = price_estimate
    if usage.provider_raw_usage is not None:
        payload["provider_raw"] = usage.provider_raw_usage
    return payload


def serialize_price_estimate(price_estimate: ProviderPriceEstimate | None) -> dict[str, object] | None:
    if price_estimate is None:
        return None
    return {
        "input_cost_usd": _round_usd(price_estimate.input_cost_usd),
        "output_cost_usd": _round_usd(price_estimate.output_cost_usd),
        "cache_read_cost_usd": _round_usd(price_estimate.cache_read_cost_usd),
        "cache_write_cost_usd": _round_usd(price_estimate.cache_write_cost_usd),
        "tool_cost_usd": _round_usd(price_estimate.tool_cost_usd),
        "total_cost_usd": _round_usd(price_estimate.total_cost_usd),
        "currency": price_estimate.currency,
        "pricing_version": price_estimate.pricing_version,
        "completeness": price_estimate.completeness,
        "notes": list(price_estimate.notes),
    }


def update_history_usage_summary(
    db: Session,
    *,
    history_id: str,
    message_usage: dict[str, object] | None,
    aggregated_at: datetime,
) -> dict[str, object] | None:
    history = db.get(ChatHistory, history_id)
    if history is None:
        return None

    history.usage_summary = merge_history_usage_summary(
        existing_summary=history.usage_summary,
        message_usage=message_usage,
        aggregated_at=aggregated_at,
    )
    return history.usage_summary


def rebuild_history_usage_summary(
    db: Session,
    *,
    history_id: str,
    aggregated_at: datetime,
) -> dict[str, object] | None:
    history = db.get(ChatHistory, history_id)
    if history is None:
        return None

    message_usages = db.execute(
        select(ChatMessage.usage).where(ChatMessage.chat_history_id == history_id)
    ).scalars().all()
    summary: dict[str, object] | None = None
    for message_usage in message_usages:
        summary = merge_history_usage_summary(
            existing_summary=summary,
            message_usage=message_usage,
            aggregated_at=aggregated_at,
        )
    history.usage_summary = summary
    return summary


def merge_history_usage_summary(
    *,
    existing_summary: dict[str, object] | None,
    message_usage: dict[str, object] | None,
    aggregated_at: datetime,
) -> dict[str, object]:
    summary = _normalize_existing_history_usage_summary(existing_summary)
    normalized_usage = extract_normalized_usage(message_usage)
    for normalized_key, total_key in _SUMMARY_TOTAL_KEY_MAP:
        summary[total_key] = int(summary.get(total_key) or 0) + int(normalized_usage.get(normalized_key) or 0)

    price_estimate = extract_price_estimate(message_usage)
    summary["estimated_price_total_usd"] = _round_usd(
        float(summary.get("estimated_price_total_usd") or 0.0)
        + float(price_estimate.get("total_cost_usd") or 0.0)
    )
    summary["currency"] = str(price_estimate.get("currency") or summary.get("currency") or "USD")
    pricing_versions = {
        version
        for version in summary.get("pricing_versions_seen", [])
        if isinstance(version, str) and version.strip()
    }
    pricing_version = price_estimate.get("pricing_version")
    if isinstance(pricing_version, str) and pricing_version.strip():
        pricing_versions.add(pricing_version.strip())
    summary["pricing_versions_seen"] = sorted(pricing_versions)
    summary["last_aggregated_at"] = aggregated_at.isoformat()
    return summary


def extract_normalized_usage(usage_payload: dict[str, object] | None) -> dict[str, int | None]:
    normalized = {key: None for key in _NORMALIZED_USAGE_KEYS}
    if not isinstance(usage_payload, dict):
        return normalized

    normalized_payload = usage_payload.get("normalized")
    if isinstance(normalized_payload, dict):
        for key in _NORMALIZED_USAGE_KEYS:
            normalized[key] = _coerce_optional_int(normalized_payload.get(key))
        return normalized

    normalized["input_tokens_reported"] = _coerce_optional_int(usage_payload.get("input_tokens"))
    normalized["output_tokens_reported"] = _coerce_optional_int(usage_payload.get("output_tokens"))
    normalized["total_tokens_reported"] = _coerce_optional_int(usage_payload.get("total_tokens"))
    return normalized


def extract_token_summary(usage_payload: dict[str, object] | None) -> dict[str, int | None]:
    normalized = extract_normalized_usage(usage_payload)
    return {
        "input_tokens": normalized["input_tokens_reported"],
        "output_tokens": normalized["output_tokens_reported"],
        "total_tokens": normalized["total_tokens_reported"],
    }


def extract_price_estimate(usage_payload: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(usage_payload, dict):
        return {}
    price_estimate = usage_payload.get("price_estimate")
    if not isinstance(price_estimate, dict):
        return {}
    return deepcopy(price_estimate)


def _normalize_existing_history_usage_summary(existing_summary: dict[str, object] | None) -> dict[str, object]:
    summary = deepcopy(existing_summary) if isinstance(existing_summary, dict) else {}
    for _, total_key in _SUMMARY_TOTAL_KEY_MAP:
        summary[total_key] = int(summary.get(total_key) or 0)
    summary["estimated_price_total_usd"] = _round_usd(float(summary.get("estimated_price_total_usd") or 0.0))
    summary["currency"] = str(summary.get("currency") or "USD")
    summary["pricing_versions_seen"] = [
        version
        for version in summary.get("pricing_versions_seen", [])
        if isinstance(version, str) and version.strip()
    ]
    return summary


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_usd(value: float) -> float:
    return round(value, 12)
