"""OpenAI provider coordination and prepared-request construction."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from copy import deepcopy

from app.config.chat import PROVIDER_TEXT_ESTIMATE_BASE_TOKENS
from app.config.chat_instructions import build_chat_system_instruction
from app.providers.openai.client import OpenAIProviderConfigurationError, ensure_openai_provider_ready
from app.providers.openai.count_tokens import count_openai_input_tokens
from app.providers.openai.mapper import (
    OpenAIStreamState,
    finalize_openai_stream,
    map_chat_messages_to_openai_input,
    map_openai_stream_event,
)
from app.providers.openai.models import OPENAI_PROVIDER_ID, list_openai_models
from app.providers.openai.models import resolve_openai_model_runtime
from app.providers.openai.options import (
    OPENAI_MODEL_MAX_OUTPUT_TOKENS,
    OPENAI_MODEL_RESPONSE_PRESET,
    OPENAI_REQUEST_DEFAULTS,
    OPENAI_RESPONSE_PRESETS,
)
from app.providers.openai.stream import OpenAIProviderError, stream_prepared_openai_raw_chat_completion
from app.providers.openai.tools import build_openai_hosted_tools
from app.providers.token_estimation import estimate_token_count_from_object
from app.providers.types import PreparedProviderChatRequest, ProviderRawStreamChunk, ProviderStreamEvent
from app.schemas.chat import ChatMessage


def prepare_openai_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> dict[str, object]:
    model_runtime = resolve_openai_model_runtime(public_model_id=public_model_id)
    request_system_instruction, input_messages = map_chat_messages_to_openai_input(messages)
    request_kwargs: dict[str, object] = {
        "model": model_runtime.provider_model,
        "instructions": build_chat_system_instruction(request_system_instruction=request_system_instruction),
        "input": input_messages,
        **OPENAI_REQUEST_DEFAULTS,
    }
    _apply_openai_response_options(request_kwargs=request_kwargs, model=model_runtime.provider_model)
    configured_tools = build_openai_hosted_tools(selected_tool_ids=selected_tool_ids)
    if configured_tools:
        request_kwargs["tools"] = configured_tools
    return request_kwargs


def build_openai_prepared_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> PreparedProviderChatRequest:
    normalized_tool_ids = _normalize_tool_ids(selected_tool_ids)
    request_kwargs = prepare_openai_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=normalized_tool_ids,
    )
    text_input = _build_openai_text_input(request_kwargs)
    return PreparedProviderChatRequest(
        provider=OPENAI_PROVIDER_ID,
        public_model_id=public_model_id,
        payload=request_kwargs,
        estimated_text_tokens=estimate_token_count_from_object(
            text_input,
            base_tokens=PROVIDER_TEXT_ESTIMATE_BASE_TOKENS,
        ),
        selected_tool_ids=normalized_tool_ids,
        text_token_count_payload=text_input,
    )


def map_prepared_openai_raw_stream_event(
    prepared_request: PreparedProviderChatRequest,
    raw_chunk: ProviderRawStreamChunk,
    *,
    state: OpenAIStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    return map_openai_stream_event(
        raw_chunk.raw_chunk,
        state=state,
        public_model_id=prepared_request.public_model_id,
        selected_tool_ids=prepared_request.selected_tool_ids,
    )


async def stream_openai_chat_completion(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> AsyncIterator[ProviderStreamEvent]:
    prepared_request = build_openai_prepared_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=selected_tool_ids,
    )
    state = OpenAIStreamState()
    async for raw_chunk in stream_prepared_openai_raw_chat_completion(prepared_request):
        for event in map_prepared_openai_raw_stream_event(prepared_request, raw_chunk, state=state):
            yield event
    finalize_openai_stream(state)


def _apply_openai_response_options(*, request_kwargs: dict[str, object], model: str) -> None:
    try:
        preset_name = OPENAI_MODEL_RESPONSE_PRESET[model]
        request_patch = deepcopy(OPENAI_RESPONSE_PRESETS[preset_name])
        request_kwargs["max_output_tokens"] = OPENAI_MODEL_MAX_OUTPUT_TOKENS[model]
    except KeyError as exc:
        raise ValueError(f"incomplete OpenAI response options for model: {model}") from exc
    request_kwargs.update(_prune_none_values(request_patch))


def _build_openai_text_input(request_kwargs: dict[str, object]) -> dict[str, object]:
    supported_keys = {"input", "instructions", "model"}
    return {key: value for key, value in request_kwargs.items() if key in supported_keys}


def _normalize_tool_ids(selected_tool_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tool_id.strip() for tool_id in selected_tool_ids if tool_id.strip()))


def _prune_none_values(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, object] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, dict):
            nested = _prune_none_values(item)
            if nested:
                cleaned[key] = nested
        else:
            cleaned[key] = item
    return cleaned


__all__ = [
    "OPENAI_PROVIDER_ID",
    "OpenAIStreamState",
    "OpenAIProviderConfigurationError",
    "OpenAIProviderError",
    "ensure_openai_provider_ready",
    "count_openai_input_tokens",
    "build_openai_prepared_chat_completion_request",
    "finalize_openai_stream",
    "list_openai_models",
    "map_prepared_openai_raw_stream_event",
    "prepare_openai_chat_completion_request",
    "stream_prepared_openai_raw_chat_completion",
    "stream_openai_chat_completion",
]
