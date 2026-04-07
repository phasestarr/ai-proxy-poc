"""
Purpose:
- Implement chat request preparation logic for the backend service layer.

Current responsibilities:
- Validate request values at business-rule level
- Resolve the public model and tool selections into a provider route
- Normalize the request into a stream-ready structure

Notes:
- Endpoint routers should call chat orchestration and remain thin.
- Provider-specific mechanics should be isolated behind provider modules later.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.catalog import resolve_provider_route
from app.providers.types import ProviderRoute
from app.schemas.chat import ChatCompletionRequest, ChatMessage
from app.services.auth import SessionContext


@dataclass(slots=True, frozen=True)
class PreparedChatCompletionRequest:
    route: ProviderRoute
    messages: list[ChatMessage]


def prepare_chat_completion_request(
    payload: ChatCompletionRequest,
    *,
    session: SessionContext,
) -> PreparedChatCompletionRequest:
    del session

    if not payload.messages:
        raise ValueError("messages must not be empty")

    return PreparedChatCompletionRequest(
        route=resolve_provider_route(
            model_id=payload.model_id,
            tool_ids=payload.tool_ids,
        ),
        messages=list(payload.messages),
    )


__all__ = [
    "PreparedChatCompletionRequest",
    "prepare_chat_completion_request",
]
