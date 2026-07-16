from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.postgres.models.usage_ledger import UsageLedgerEvent
from app.providers.types import ProviderPriceEstimate, ProviderUsageMetadata

USD_LEDGER_PRECISION = Decimal("0.000000001")
USD_DISPLAY_PRECISION = Decimal("0.000001")

_NORMALIZED_USAGE_KEYS: tuple[str, ...] = (
    "input_tokens_reported",
    "output_tokens_reported",
    "total_tokens_reported",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "reasoning_tokens",
    "tool_result_input_tokens",
    "web_search_requests",
    "web_fetch_requests",
    "file_search_requests",
    "code_execution_requests",
    "code_interpreter_requests",
    "shell_requests",
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
            "web_fetch_requests": usage.web_fetch_request_count,
            "file_search_requests": usage.file_search_request_count,
            "code_execution_requests": usage.code_execution_request_count,
            "code_interpreter_requests": usage.code_interpreter_request_count,
            "shell_requests": usage.shell_request_count,
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


def append_chat_usage_ledger_event(
    db: Session,
    *,
    user_id: str,
    auth_session_id: str | None,
    chat_history_id: str,
    chat_message_id: str | None,
    provider: str | None,
    model_id: str | None,
    tool_ids: list[str],
    result_code: str,
    usage_payload: dict[str, object] | None,
    operation: str = "chat_completion",
) -> UsageLedgerEvent:
    normalized_usage = extract_normalized_usage(usage_payload)
    price_estimate = extract_price_estimate(usage_payload)
    provider_raw_usage = _extract_provider_raw_usage(usage_payload)
    total_cost_usd = _ledger_decimal(price_estimate.get("total_cost_usd"))

    event = UsageLedgerEvent(
        id=str(uuid4()),
        user_id=user_id,
        auth_session_id=auth_session_id,
        chat_history_id_snapshot=chat_history_id,
        chat_message_id_snapshot=chat_message_id,
        provider=provider,
        model_id=model_id,
        tool_ids=list(tool_ids),
        operation=operation,
        source="chat_completion",
        status="billable",
        result_code=result_code,
        input_tokens_reported=normalized_usage["input_tokens_reported"],
        output_tokens_reported=normalized_usage["output_tokens_reported"],
        total_tokens_reported=normalized_usage["total_tokens_reported"],
        cached_input_tokens=normalized_usage["cached_input_tokens"],
        cache_write_input_tokens=normalized_usage["cache_write_input_tokens"],
        reasoning_tokens=normalized_usage["reasoning_tokens"],
        tool_result_input_tokens=normalized_usage["tool_result_input_tokens"],
        web_search_requests=normalized_usage["web_search_requests"],
        web_fetch_requests=normalized_usage["web_fetch_requests"],
        file_search_requests=normalized_usage["file_search_requests"],
        code_execution_requests=normalized_usage["code_execution_requests"],
        code_interpreter_requests=normalized_usage["code_interpreter_requests"],
        shell_requests=normalized_usage["shell_requests"],
        price_estimate=price_estimate or None,
        provider_raw_usage=provider_raw_usage,
        total_cost_usd=total_cost_usd,
        currency=str(price_estimate.get("currency") or "USD"),
        pricing_version=_optional_str(price_estimate.get("pricing_version")),
        price_completeness=_optional_str(price_estimate.get("completeness")),
    )
    db.add(event)
    return event


def get_user_estimated_usage_usd(db: Session, *, user_id: str) -> Decimal:
    value = db.execute(
        select(func.coalesce(func.sum(UsageLedgerEvent.total_cost_usd), 0)).where(
            UsageLedgerEvent.user_id == user_id,
            UsageLedgerEvent.status.in_(("billable", "adjustment")),
        )
    ).scalar_one()
    return _display_decimal(value)


def _extract_provider_raw_usage(usage_payload: dict[str, object] | None) -> dict | None:
    if not isinstance(usage_payload, dict):
        return None
    provider_raw_usage = usage_payload.get("provider_raw")
    return provider_raw_usage if isinstance(provider_raw_usage, dict) else None


def _ledger_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(USD_LEDGER_PRECISION)
    except (InvalidOperation, ValueError):
        return Decimal("0").quantize(USD_LEDGER_PRECISION)


def _display_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(USD_DISPLAY_PRECISION)
    except (InvalidOperation, ValueError):
        return Decimal("0").quantize(USD_DISPLAY_PRECISION)


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def _round_usd(value: float) -> float:
    return round(value, 12)
