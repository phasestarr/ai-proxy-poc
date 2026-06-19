"""
Backend-owned chat result messages.
"""

from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(slots=True, frozen=True)
class WeightedOutcomeMessage:
    text: str
    weight: int


SUCCESS_RESULT_CODE = "success"

SUCCESS_MESSAGES: tuple[WeightedOutcomeMessage, ...] = (
    WeightedOutcomeMessage("Done! You got more questions?", 10),
    WeightedOutcomeMessage("Text generation completed.", 10),
    WeightedOutcomeMessage("Response ready.", 10),
)

ERROR_MESSAGES: dict[str, str] = {
    "chat_failed": "Chat processing failed.",
    "attachments_too_large": "Attached files exceed the provider file token limit.",
    "attachments_token_count_failed": "Attached file token metadata is unavailable.",
    "attachments_unsupported": "The selected model does not support file attachments.",
    "attachments_upload_failed": "Attached files could not be prepared for the selected provider.",
    "coordination_unavailable": "Chat coordination is temporarily unavailable.",
    "context_compaction_failed": "Conversation context compression failed.",
    "context_still_too_large": "Conversation context is still too large to send.",
    "model_required": "Select a model before sending.",
    "model_unsupported": "The selected model is not supported.",
    "tool_unsupported": "The selected tool is not supported by this model.",
    "provider_auth_failed": "The selected provider rejected the proxy credentials.",
    "provider_bad_request": "The selected provider rejected the request.",
    "provider_failed": "The selected provider failed while processing the request.",
    "provider_not_configured": "The selected provider is not configured.",
    "provider_first_response_timeout": "The selected provider did not start responding in time.",
    "provider_rate_limited": "The selected provider is rate limiting requests.",
    "provider_unavailable": "The selected provider is temporarily unavailable.",
    "rate_limit_hour": "Hourly chat limit reached. Try again later.",
    "rate_limit_minute": "Too many requests. Try again shortly.",
    "request_in_progress": "A chat request is already running for this chat history.",
    "usage_cap_exceeded": "Usage cap reached. Ask the operator to reset or raise the cap.",
}


def pick_success_message() -> str:
    total_weight = sum(item.weight for item in SUCCESS_MESSAGES)
    random_value = random.random() * total_weight

    cumulative_weight = 0
    for item in SUCCESS_MESSAGES:
        cumulative_weight += item.weight
        if random_value <= cumulative_weight:
            return item.text

    return SUCCESS_MESSAGES[-1].text


def get_error_message(code: str) -> str:
    return ERROR_MESSAGES.get(code, ERROR_MESSAGES["chat_failed"])
