"""
Purpose:
- Implement chat request preparation logic for the backend service layer.

Current responsibilities:
- Validate request values at business-rule level
- Resolve the public model ID into a provider model binding
- Normalize the request into a stream-ready structure

Notes:
- Endpoint routers should call chat orchestration and remain thin.
- Provider-specific mechanics should be isolated behind provider modules later.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.chat import ChatCompletionRequest, ChatMessage
from app.services.auth import SessionContext
from app.services.model_registry import ModelDefinition, get_model_definition


@dataclass(slots=True, frozen=True)
class PreparedChatCompletionRequest:
    model: ModelDefinition
    messages: list[ChatMessage]


def prepare_chat_completion_request(
    payload: ChatCompletionRequest,
    *,
    session: SessionContext,
) -> PreparedChatCompletionRequest:
    del session

    model = get_model_definition(payload.model)
    if model is None:
        raise ValueError(f"unsupported model: {payload.model}")

    if not payload.messages:
        raise ValueError("messages must not be empty")

    return PreparedChatCompletionRequest(
        model=model,
        messages=list(payload.messages),
    )


__all__ = [
    "PreparedChatCompletionRequest",
    "prepare_chat_completion_request",
]
