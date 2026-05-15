from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(slots=True, frozen=True)
class WeightedOutcomeMessage:
    text: str
    weight: int


VERTEX_SUCCESS_RESULT_CODE = "vertex_finish_stop"

VERTEX_SUCCESS_MESSAGES: tuple[WeightedOutcomeMessage, ...] = (
    WeightedOutcomeMessage("Done! You got more questions?", 10),
    WeightedOutcomeMessage("Text generation completed.", 10),
    WeightedOutcomeMessage("Response ready.", 10),
)

VERTEX_RESULT_MESSAGES: dict[str, str] = {
    VERTEX_SUCCESS_RESULT_CODE: "Response ready.",
    "vertex_finish_max_tokens": "Gemini stopped because it reached the output token limit.",
    "vertex_finish_safety": "Gemini stopped because the response was blocked for safety reasons.",
    "vertex_finish_recitation": "Gemini stopped because the response may be recitation.",
    "vertex_finish_other": "Gemini stopped before completing the response.",
    "vertex_finish_blocklist": "Gemini stopped because the response matched a blocklist.",
    "vertex_finish_prohibited_content": "Gemini stopped because the response may contain prohibited content.",
    "vertex_finish_spii": "Gemini stopped because the response may contain sensitive personal information.",
    "vertex_finish_malformed_function_call": "Gemini generated an invalid function call.",
    "vertex_finish_model_armor": "Gemini stopped because Model Armor blocked the response.",
    "vertex_finish_image_safety": "Gemini stopped because generated image output violated safety policies.",
    "vertex_finish_image_prohibited_content": "Gemini stopped because generated image output may contain prohibited content.",
    "vertex_finish_image_recitation": "Gemini stopped because generated image output may be recitation.",
    "vertex_finish_image_other": "Gemini stopped while generating image output.",
    "vertex_finish_unexpected_tool_call": "Gemini generated an unexpected tool call.",
    "vertex_finish_no_image": "Gemini was expected to generate an image but did not.",
    "vertex_prompt_blocked": "Gemini blocked the prompt before generating a response.",
    "vertex_stream_error": "Gemini failed while streaming the response.",
    "vertex_empty_output": "Gemini finished without returning visible text.",
    "vertex_provider_bad_request": "Gemini rejected the request after it was sent.",
    "vertex_provider_rate_limited": "Gemini is rate limiting requests.",
    "vertex_provider_unavailable": "Gemini is temporarily unavailable.",
    "vertex_provider_failed": "Gemini failed while processing the request.",
}

VERTEX_STATUS_MESSAGES: dict[str, str] = {
    "vertex_streaming": "Gemini is generating a response.",
    "vertex_function_call": "Gemini is preparing a function call.",
    "vertex_thinking": "Gemini is thinking.",
    "vertex_safety_review": "Gemini is evaluating safety constraints.",
}


def pick_vertex_success_message() -> str:
    total_weight = sum(item.weight for item in VERTEX_SUCCESS_MESSAGES)
    random_value = random.random() * total_weight

    cumulative_weight = 0
    for item in VERTEX_SUCCESS_MESSAGES:
        cumulative_weight += item.weight
        if random_value <= cumulative_weight:
            return item.text

    return VERTEX_SUCCESS_MESSAGES[-1].text


def get_vertex_result_message(code: str) -> str:
    return VERTEX_RESULT_MESSAGES.get(code, VERTEX_RESULT_MESSAGES["vertex_provider_failed"])


def get_vertex_status_message(code: str) -> str:
    return VERTEX_STATUS_MESSAGES.get(code, "Gemini is processing the response.")


def build_vertex_finish_detail(*, finish_reason: str | None) -> str:
    if finish_reason:
        return f"Gemini stopped with finishReason={finish_reason}."
    return "Gemini stopped without a finishReason."


def build_vertex_prompt_block_detail(*, block_reason: str | None, block_message: str | None) -> str:
    if block_reason and block_message:
        return f"Gemini blocked the prompt with reason={block_reason}: {block_message}"
    if block_reason:
        return f"Gemini blocked the prompt with reason={block_reason}."
    if block_message:
        return f"Gemini blocked the prompt: {block_message}"
    return "Gemini blocked the prompt."


def build_vertex_empty_output_detail(*, finish_reason: str | None) -> str:
    if finish_reason:
        return f"Gemini stopped with finishReason={finish_reason} but produced no visible text."
    return "Gemini finished without producing visible text."


def build_vertex_status_error_detail(*, status_code: int | None, message: str | None) -> str:
    if status_code is not None and message:
        return f"Gemini request failed with HTTP {status_code}: {message}"
    if message:
        return f"Gemini request failed: {message}"
    if status_code is not None:
        return f"Gemini request failed with HTTP {status_code}."
    return "Gemini request failed."
