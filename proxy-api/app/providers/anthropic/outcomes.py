from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(slots=True, frozen=True)
class WeightedOutcomeMessage:
    text: str
    weight: int


ANTHROPIC_SUCCESS_RESULT_CODE = "anthropic_stop_end_turn"

ANTHROPIC_SUCCESS_MESSAGES: tuple[WeightedOutcomeMessage, ...] = (
    WeightedOutcomeMessage("Done! You got more questions?", 10),
    WeightedOutcomeMessage("Text generation completed.", 10),
    WeightedOutcomeMessage("Response ready.", 10),
)

ANTHROPIC_RESULT_MESSAGES: dict[str, str] = {
    ANTHROPIC_SUCCESS_RESULT_CODE: "Response ready.",
    "anthropic_stop_stop_sequence": "Claude stopped at a configured stop sequence.",
    "anthropic_stop_max_tokens": "Claude stopped because it reached the token limit.",
    "anthropic_stop_tool_use": "Claude stopped to request tool execution.",
    "anthropic_stop_pause_turn": "Claude paused before finishing the response.",
    "anthropic_stop_refusal": "Claude refused to complete the response.",
    "anthropic_stop_model_context_window_exceeded": "Claude hit the model context window limit.",
    "anthropic_stream_error": "Claude failed while streaming the response.",
    "anthropic_empty_output": "Claude finished without returning visible text.",
    "anthropic_provider_auth_failed": "Claude rejected the proxy credentials.",
    "anthropic_provider_bad_request": "Claude rejected the request after it was sent.",
    "anthropic_provider_rate_limited": "Claude is rate limiting requests.",
    "anthropic_provider_unavailable": "Claude is temporarily unavailable.",
    "anthropic_provider_failed": "Claude failed while processing the request.",
}

ANTHROPIC_STATUS_MESSAGES: dict[str, str] = {
    "anthropic_message_start": "Claude accepted the request.",
    "anthropic_text_output": "Claude is writing the response.",
    "anthropic_thinking": "Claude is thinking.",
    "anthropic_thinking_delta": "Claude is expanding its reasoning.",
    "anthropic_thinking_signature": "Claude is finalizing its reasoning state.",
    "anthropic_tool_use": "Claude is preparing a tool call.",
    "anthropic_tool_input": "Claude is building tool input.",
    "anthropic_ping": "Claude is still working.",
    "anthropic_message_delta": "Claude is updating the response state.",
    "anthropic_message_stop": "Claude finished streaming the response.",
}


def pick_anthropic_success_message() -> str:
    total_weight = sum(item.weight for item in ANTHROPIC_SUCCESS_MESSAGES)
    random_value = random.random() * total_weight

    cumulative_weight = 0
    for item in ANTHROPIC_SUCCESS_MESSAGES:
        cumulative_weight += item.weight
        if random_value <= cumulative_weight:
            return item.text

    return ANTHROPIC_SUCCESS_MESSAGES[-1].text


def get_anthropic_result_message(code: str) -> str:
    return ANTHROPIC_RESULT_MESSAGES.get(code, ANTHROPIC_RESULT_MESSAGES["anthropic_provider_failed"])


def get_anthropic_status_message(code: str) -> str:
    return ANTHROPIC_STATUS_MESSAGES.get(code, "Claude is processing the response.")


def build_anthropic_stream_error_detail(*, error_type: str | None, message: str | None) -> str:
    if error_type and message:
        return f"Claude returned a stream error with type={error_type}: {message}"
    if message:
        return f"Claude returned a stream error: {message}"
    return "Claude returned a stream error."


def build_anthropic_stop_detail(*, stop_reason: str | None) -> str:
    if stop_reason:
        return f"Claude stopped with stop_reason={stop_reason}."
    return "Claude stopped without a stop_reason."


def build_anthropic_empty_output_detail(*, stop_reason: str | None) -> str:
    if stop_reason:
        return f"Claude stopped with stop_reason={stop_reason} but produced no visible text."
    return "Claude finished without producing visible text."


def build_anthropic_status_error_detail(*, status_code: int | None, message: str | None) -> str:
    if status_code is not None and message:
        return f"Claude request failed with HTTP {status_code}: {message}"
    if message:
        return f"Claude request failed: {message}"
    if status_code is not None:
        return f"Claude request failed with HTTP {status_code}."
    return "Claude request failed."
