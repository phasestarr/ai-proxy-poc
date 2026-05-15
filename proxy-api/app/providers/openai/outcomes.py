from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(slots=True, frozen=True)
class WeightedOutcomeMessage:
    text: str
    weight: int


OPENAI_SUCCESS_RESULT_CODE = "openai_response_completed"

OPENAI_SUCCESS_MESSAGES: tuple[WeightedOutcomeMessage, ...] = (
    WeightedOutcomeMessage("Done! You got more questions?", 10),
    WeightedOutcomeMessage("Text generation completed.", 10),
    WeightedOutcomeMessage("Response ready.", 10),
)

OPENAI_RESULT_MESSAGES: dict[str, str] = {
    OPENAI_SUCCESS_RESULT_CODE: "Response ready.",
    "openai_response_incomplete": "The OpenAI response ended before it finished.",
    "openai_response_failed": "OpenAI failed while generating the response.",
    "openai_response_empty_output": "OpenAI finished without returning visible text.",
    "openai_provider_auth_failed": "OpenAI rejected the proxy credentials.",
    "openai_provider_bad_request": "OpenAI rejected the request after it was sent.",
    "openai_provider_rate_limited": "OpenAI is rate limiting requests.",
    "openai_provider_unavailable": "OpenAI is temporarily unavailable.",
    "openai_provider_failed": "OpenAI failed while processing the request.",
}

OPENAI_STATUS_MESSAGES: dict[str, str] = {
    "openai_response_created": "OpenAI accepted the request.",
    "openai_response_queued": "OpenAI queued the response.",
    "openai_response_in_progress": "OpenAI is generating a response.",
    "openai_reasoning": "OpenAI is thinking.",
    "openai_function_calling": "OpenAI is preparing a tool call.",
    "openai_web_search": "OpenAI is searching the web.",
    "openai_file_search": "OpenAI is searching files.",
    "openai_code_execution": "OpenAI is running code.",
    "openai_image_generation": "OpenAI is generating an image.",
    "openai_mcp_call": "OpenAI is calling a tool server.",
}


def pick_openai_success_message() -> str:
    total_weight = sum(item.weight for item in OPENAI_SUCCESS_MESSAGES)
    random_value = random.random() * total_weight

    cumulative_weight = 0
    for item in OPENAI_SUCCESS_MESSAGES:
        cumulative_weight += item.weight
        if random_value <= cumulative_weight:
            return item.text

    return OPENAI_SUCCESS_MESSAGES[-1].text


def get_openai_result_message(code: str) -> str:
    return OPENAI_RESULT_MESSAGES.get(code, OPENAI_RESULT_MESSAGES["openai_provider_failed"])


def get_openai_status_message(code: str) -> str:
    return OPENAI_STATUS_MESSAGES.get(code, "OpenAI is processing the response.")


def build_openai_incomplete_detail(*, reason: str | None) -> str:
    if reason:
        return f"OpenAI returned response.incomplete with reason={reason}."
    return "OpenAI returned response.incomplete."


def build_openai_failed_detail(*, error_code: str | None, message: str | None) -> str:
    if error_code and message:
        return f"OpenAI returned response.failed with code={error_code}: {message}"
    if message:
        return f"OpenAI returned response.failed: {message}"
    return "OpenAI returned response.failed."


def build_openai_empty_output_detail() -> str:
    return "OpenAI completed the response without any visible text deltas."


def build_openai_status_error_detail(*, status_code: int | None, message: str | None) -> str:
    if status_code is not None and message:
        return f"OpenAI request failed with HTTP {status_code}: {message}"
    if message:
        return f"OpenAI request failed: {message}"
    if status_code is not None:
        return f"OpenAI request failed with HTTP {status_code}."
    return "OpenAI request failed."
