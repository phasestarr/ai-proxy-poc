"""Vertex provider coordination and prepared-request construction."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from copy import deepcopy

from app.config.chat import PROVIDER_TEXT_ESTIMATE_BASE_TOKENS
from app.config.chat_instructions import build_chat_system_instruction
from app.providers.vertex.client import VertexProviderConfigurationError, ensure_vertex_provider_ready
from app.providers.token_estimation import estimate_token_count_from_object
from app.providers.types import PreparedProviderChatRequest, ProviderRawStreamChunk, ProviderStreamEvent
from app.providers.vertex.count_tokens import VertexCountTokensPayload, count_vertex_input_tokens
from app.providers.vertex.mapper import (
    VertexStreamState,
    finalize_vertex_stream,
    map_chat_messages_to_vertex_contents,
    map_vertex_stream_chunk,
)
from app.providers.vertex.models import VERTEX_PROVIDER_ID, list_vertex_models
from app.providers.vertex.models import resolve_vertex_model_runtime
from app.providers.vertex.options import (
    VERTEX_MODEL_MAX_OUTPUT_TOKENS,
    VERTEX_MODEL_RESPONSE_PRESET,
    VERTEX_RESPONSE_PRESETS,
)
from app.providers.vertex.stream import VertexProviderError, stream_prepared_vertex_raw_chat_completion
from app.providers.vertex.tools import build_vertex_hosted_tools
from app.schemas.chat import ChatMessage


def prepare_vertex_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
):
    from google.genai import types

    model_runtime = resolve_vertex_model_runtime(public_model_id=public_model_id)
    request_system_instruction, contents = map_chat_messages_to_vertex_contents(messages)
    config_kwargs: dict[str, object] = {
        "systemInstruction": build_chat_system_instruction(request_system_instruction=request_system_instruction),
    }
    configured_tools = build_vertex_hosted_tools(selected_tool_ids=selected_tool_ids, types_module=types)
    if configured_tools:
        config_kwargs["tools"] = configured_tools
    _apply_vertex_response_options(
        config_kwargs=config_kwargs,
        model=model_runtime.provider_model,
        types_module=types,
    )
    config = types.GenerateContentConfig(**config_kwargs)
    count_config = types.CountTokensConfig(system_instruction=getattr(config, "system_instruction", None))
    return model_runtime, contents, config, count_config


def build_vertex_prepared_chat_completion_request(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> PreparedProviderChatRequest:
    normalized_tool_ids = _normalize_tool_ids(selected_tool_ids)
    model_runtime, contents, config, count_config = prepare_vertex_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=normalized_tool_ids,
    )
    estimate_source = {
        "model": model_runtime.provider_model,
        "location": model_runtime.location,
        "contents": contents,
        "system_instruction": getattr(config, "system_instruction", None),
    }
    return PreparedProviderChatRequest(
        provider=VERTEX_PROVIDER_ID,
        public_model_id=public_model_id,
        payload={
            "provider_model": model_runtime.provider_model,
            "location": model_runtime.location,
            "contents": contents,
            "config": config,
            "count_config": count_config,
            "estimate_source": estimate_source,
        },
        estimated_text_tokens=estimate_token_count_from_object(
            estimate_source,
            base_tokens=PROVIDER_TEXT_ESTIMATE_BASE_TOKENS,
        ),
        selected_tool_ids=normalized_tool_ids,
        text_token_count_payload=VertexCountTokensPayload(
            provider_model=model_runtime.provider_model,
            location=model_runtime.location,
            contents=contents,
            config=count_config,
        ),
    )


def map_prepared_vertex_raw_stream_event(
    prepared_request: PreparedProviderChatRequest,
    raw_chunk: ProviderRawStreamChunk,
    *,
    state: VertexStreamState,
) -> tuple[ProviderStreamEvent, ...]:
    return map_vertex_stream_chunk(
        raw_chunk.raw_chunk,
        state=state,
        public_model_id=prepared_request.public_model_id,
        selected_tool_ids=prepared_request.selected_tool_ids,
    )


async def stream_vertex_chat_completion(
    *,
    public_model_id: str,
    messages: list[ChatMessage],
    selected_tool_ids: Iterable[str] = (),
) -> AsyncIterator[ProviderStreamEvent]:
    prepared_request = build_vertex_prepared_chat_completion_request(
        public_model_id=public_model_id,
        messages=messages,
        selected_tool_ids=selected_tool_ids,
    )
    state = VertexStreamState()
    async for raw_chunk in stream_prepared_vertex_raw_chat_completion(prepared_request):
        for event in map_prepared_vertex_raw_stream_event(prepared_request, raw_chunk, state=state):
            yield event
    finalize_vertex_stream(state)


def _apply_vertex_response_options(*, config_kwargs: dict[str, object], model: str, types_module) -> None:
    try:
        preset_name = VERTEX_MODEL_RESPONSE_PRESET[model]
        request_patch = deepcopy(VERTEX_RESPONSE_PRESETS[preset_name])
        config_kwargs["maxOutputTokens"] = VERTEX_MODEL_MAX_OUTPUT_TOKENS[model]
    except KeyError as exc:
        raise ValueError(f"incomplete Vertex response options for model: {model}") from exc
    thinking_config = request_patch.get("thinking_config")
    if isinstance(thinking_config, dict):
        config_kwargs["thinkingConfig"] = _build_vertex_thinking_config(
            thinking_config=thinking_config,
            types_module=types_module,
        )


def _build_vertex_thinking_config(*, thinking_config: dict[str, object], types_module):
    thinking_level = thinking_config.get("thinking_level")
    thinking_level_type = getattr(types_module, "ThinkingLevel", None)
    if thinking_level_type is not None and isinstance(thinking_level, str):
        thinking_level = getattr(thinking_level_type, thinking_level, thinking_level)
    payload = {
        "thinking_level": thinking_level,
        "include_thoughts": bool(thinking_config.get("include_thoughts", False)),
    }
    thinking_config_type = getattr(types_module, "ThinkingConfig", None)
    return payload if thinking_config_type is None else thinking_config_type(**payload)


def _normalize_tool_ids(selected_tool_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tool_id.strip() for tool_id in selected_tool_ids if tool_id.strip()))


__all__ = [
    "VERTEX_PROVIDER_ID",
    "VertexStreamState",
    "VertexProviderConfigurationError",
    "VertexProviderError",
    "ensure_vertex_provider_ready",
    "count_vertex_input_tokens",
    "build_vertex_prepared_chat_completion_request",
    "finalize_vertex_stream",
    "list_vertex_models",
    "map_prepared_vertex_raw_stream_event",
    "prepare_vertex_chat_completion_request",
    "stream_prepared_vertex_raw_chat_completion",
    "stream_vertex_chat_completion",
]
