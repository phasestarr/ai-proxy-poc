"""Application-owned chat and context tuning values."""

from __future__ import annotations


# Latest user input is rejected before persisted context is assembled.
LATEST_PROMPT_MAX_TOKENS = 100_000

# Text-only context budgeting. Attachments have an independent history limit.
EXACT_TEXT_TOKEN_COUNT_TRIGGER = 80_000
TEXT_CONTEXT_COMPACTION_TRIGGER = 100_000

# Compression output guidance. The prompt is built from these values.
COMPRESSION_TARGET_MIN_TOKENS = 5_000
COMPRESSION_TARGET_MAX_TOKENS = 10_000

# Shared heuristic overhead used before provider-native exact counting.
PROVIDER_TEXT_ESTIMATE_BASE_TOKENS = 96
DEFAULT_TEXT_TOKEN_ENCODING = "o200k_base"

# Public request/catalog limits.
MAX_SELECTED_TOOL_IDS = 16

# Stored metadata limits that intentionally match the database schema.
CHAT_HISTORY_TITLE_MAX_CHARS = 255
GENERATED_CHAT_HISTORY_TITLE_MAX_CHARS = 80


def validate_chat_config() -> None:
    if LATEST_PROMPT_MAX_TOKENS < 1:
        raise ValueError("LATEST_PROMPT_MAX_TOKENS must be positive")
    if EXACT_TEXT_TOKEN_COUNT_TRIGGER < 1:
        raise ValueError("EXACT_TEXT_TOKEN_COUNT_TRIGGER must be positive")
    if TEXT_CONTEXT_COMPACTION_TRIGGER < EXACT_TEXT_TOKEN_COUNT_TRIGGER:
        raise ValueError(
            "TEXT_CONTEXT_COMPACTION_TRIGGER must be greater than or equal to "
            "EXACT_TEXT_TOKEN_COUNT_TRIGGER"
        )
    if not 0 < COMPRESSION_TARGET_MIN_TOKENS <= COMPRESSION_TARGET_MAX_TOKENS:
        raise ValueError("compression target token values are invalid")
    if COMPRESSION_TARGET_MAX_TOKENS >= TEXT_CONTEXT_COMPACTION_TRIGGER:
        raise ValueError("compression target must be smaller than the compaction trigger")
    if PROVIDER_TEXT_ESTIMATE_BASE_TOKENS < 0:
        raise ValueError("PROVIDER_TEXT_ESTIMATE_BASE_TOKENS must not be negative")
    if not DEFAULT_TEXT_TOKEN_ENCODING.strip():
        raise ValueError("DEFAULT_TEXT_TOKEN_ENCODING must not be blank")
    if MAX_SELECTED_TOOL_IDS < 1:
        raise ValueError("MAX_SELECTED_TOOL_IDS must be positive")
    if CHAT_HISTORY_TITLE_MAX_CHARS < 1 or GENERATED_CHAT_HISTORY_TITLE_MAX_CHARS < 1:
        raise ValueError("chat history title limits must be positive")
    if GENERATED_CHAT_HISTORY_TITLE_MAX_CHARS > CHAT_HISTORY_TITLE_MAX_CHARS:
        raise ValueError("generated chat history title limit must not exceed the stored title limit")


validate_chat_config()
