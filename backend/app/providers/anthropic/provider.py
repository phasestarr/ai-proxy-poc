"""Anthropic provider coordination and prepared-request construction."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from copy import deepcopy

from app.config.chat import PROVIDER_TEXT_ESTIMATE_BASE_TOKENS
from app.config.chat_instructions import build_chat_system_instruction
from app.providers.anthropic.client import AnthropicProviderConfigurationError, ensure_anthropic_provider_ready
from app.providers.anthropic.count_tokens import count_anthropic_input_tokens
from app.providers.anthropic.config import get_anthropic_model_config
from app.providers.anthropic.mapper import (
    AnthropicStreamState,
    finalize_anthropic_stream,
    map_anthropic_stream_event,
    map_chat_messages_to_anthropic_messages,
)
from app.providers.anthropic.models import ANTHROPIC_PROVIDER_ID, list_anthropic_models
from app.providers.anthropic.models import resolve_anthropic_model_runtime
from app.providers.anthropic.options import (
    ANTHROPIC_MODEL_MAX_TOKENS,
    ANTHROPIC_MODEL_REASONING_PRESET,
    ANTHROPIC_REASONING_PRESETS,
)
from app.providers.anthropic.stream import AnthropicProviderError, stream_prepared_anthropic_raw_chat_completion
from app.providers.anthropic.tools import build_anthropic_beta_headers, build_anthropic_hosted_tools
from app.providers.token_estimation import estimate_token_count_from_object
from app.providers.types import PreparedProviderChatRequest, ProviderRawStreamChunk, ProviderStreamEvent
from app.schemas.chat import ChatMessage


def prepare_anthropic_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> dict[str, object]:
    model_runtime = resolve_anthropic_model_runtime(public_model_id=public_model_id)
    request_system_instruction, provider_messages = map_chat_messages_to_anthropic_messages(messages)
    request_kwargs: dict[str, object] = {
        "model": model_runtime.provider_model,
        "system": build_chat_system_instruction(request_system_instruction=request_system_instruction),
        "messages": provider_messages,
    }
    _apply_anthropic_reasoning_options(request_kwargs=request_kwargs, model=model_runtime.provider_model)
    configured_tools = build_anthropic_hosted_tools(
        selected_tool_ids=selected_tool_ids,
        model=model_runtime.provider_model,
    )
    if configured_tools:
        request_kwargs["tools"] = configured_tools
    beta_headers = build_anthropic_beta_headers(selected_tool_ids=selected_tool_ids)
    merged_betas = list(
        dict.fromkeys(
            [
                *(str(item).strip() for item in (request_kwargs.get("betas") or []) if str(item).strip()),
                *beta_headers,
            ]
        )
    )
    if merged_betas:
        request_kwargs["betas"] = merged_betas
    return request_kwargs


def build_anthropic_prepared_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> PreparedProviderChatRequest:
    normalized_tool_ids = _normalize_tool_ids(selected_tool_ids)
    request_kwargs = prepare_anthropic_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=normalized_tool_ids,
    )
    text_input = _build_anthropic_text_input(request_kwargs)
    return PreparedProviderChatRequest(
        provider=ANTHROPIC_PROVIDER_ID,
        public_model_id=public_model_id,
        payload=request_kwargs,
        estimated_text_tokens=estimate_token_count_from_object(
            text_input,
            base_tokens=PROVIDER_TEXT_ESTIMATE_BASE_TOKENS,
        ),
        selected_tool_ids=normalized_tool_ids,
        text_token_count_payload=text_input,
    )


def map_prepared_anthropic_raw_stream_event(
    prepared_request: PreparedProviderChatRequest,
    raw_chunk: ProviderRawStreamChunk,
    *,
    state: AnthropicStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    return map_anthropic_stream_event(
        raw_chunk.raw_chunk,
        state=state,
        public_model_id=prepared_request.public_model_id,
        selected_tool_ids=prepared_request.selected_tool_ids,
    )


async def stream_anthropic_chat_completion(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> AsyncIterator[ProviderStreamEvent]:
    prepared_request = build_anthropic_prepared_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=selected_tool_ids,
    )
    state = AnthropicStreamState()
    async for raw_chunk in stream_prepared_anthropic_raw_chat_completion(prepared_request):
        for event in map_prepared_anthropic_raw_stream_event(prepared_request, raw_chunk, state=state):
            yield event
    finalize_anthropic_stream(state)


def _apply_anthropic_reasoning_options(*, request_kwargs: dict[str, object], model: str) -> None:
    try:
        preset_name = ANTHROPIC_MODEL_REASONING_PRESET[model]
        request_patch = deepcopy(ANTHROPIC_REASONING_PRESETS[preset_name])
        request_kwargs["max_tokens"] = ANTHROPIC_MODEL_MAX_TOKENS[model]
    except KeyError as exc:
        raise ValueError(f"incomplete Anthropic response options for model: {model}") from exc
    model_config = get_anthropic_model_config(model)
    if model_config.disable_thinking_when_none and preset_name == "none":
        request_patch["thinking"] = {"type": "disabled"}
    request_kwargs.update(_prune_none_values(request_patch))


def _build_anthropic_text_input(request_kwargs: dict[str, object]) -> dict[str, object]:
    supported_keys = {"messages", "model", "system"}
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
    "ANTHROPIC_PROVIDER_ID",
    "AnthropicStreamState",
    "AnthropicProviderConfigurationError",
    "AnthropicProviderError",
    "ensure_anthropic_provider_ready",
    "count_anthropic_input_tokens",
    "build_anthropic_prepared_chat_completion_request",
    "finalize_anthropic_stream",
    "list_anthropic_models",
    "map_prepared_anthropic_raw_stream_event",
    "prepare_anthropic_chat_completion_request",
    "stream_prepared_anthropic_raw_chat_completion",
    "stream_anthropic_chat_completion",
]
