from __future__ import annotations

from app.providers.types import PreparedProviderChatRequest


SOFT_CONTEXT_COMPACTION_THRESHOLD = 50_000
EXACT_INPUT_TOKEN_COUNT_TRIGGER = 40_000


def needs_context_compaction(prepared_request: PreparedProviderChatRequest) -> bool:
    return prepared_request.budget_input_tokens > SOFT_CONTEXT_COMPACTION_THRESHOLD


def should_resolve_exact_input_tokens(prepared_request: PreparedProviderChatRequest) -> bool:
    return (
        prepared_request.input_token_count_payload is not None
        and prepared_request.estimated_input_tokens >= EXACT_INPUT_TOKEN_COUNT_TRIGGER
    )
