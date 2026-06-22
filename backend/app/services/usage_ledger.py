from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.postgres.models.usage_ledger import UsageLedgerEvent
from app.services.chat.histories.usage_summary import extract_normalized_usage, extract_price_estimate

USD_LEDGER_PRECISION = Decimal("0.000000001")
USD_DISPLAY_PRECISION = Decimal("0.000001")


def append_chat_usage_ledger_event(
    db: Session,
    *,
    user_id: str,
    auth_session_id: str | None,
    chat_history_id: str,
    chat_message_id: str,
    provider: str | None,
    model_id: str | None,
    tool_ids: list[str],
    result_code: str,
    usage_payload: dict[str, object] | None,
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
        operation="chat_completion",
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
        file_search_requests=normalized_usage["file_search_requests"],
        code_execution_requests=normalized_usage["code_execution_requests"],
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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None
