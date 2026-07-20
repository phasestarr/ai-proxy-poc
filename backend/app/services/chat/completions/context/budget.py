from __future__ import annotations

from app.config.chat import EXACT_TEXT_TOKEN_COUNT_TRIGGER, TEXT_CONTEXT_COMPACTION_TRIGGER
from app.providers.types import PreparedProviderChatRequest


def needs_context_compaction(prepared_request: PreparedProviderChatRequest) -> bool:
    return prepared_request.budget_text_tokens > TEXT_CONTEXT_COMPACTION_TRIGGER


def should_resolve_exact_input_tokens(prepared_request: PreparedProviderChatRequest) -> bool:
    return (
        prepared_request.text_token_count_payload is not None
        and prepared_request.estimated_text_tokens >= EXACT_TEXT_TOKEN_COUNT_TRIGGER
    )
