from __future__ import annotations

from app.config.chat import (
    COMPRESSION_TARGET_MAX_TOKENS,
    COMPRESSION_TARGET_MIN_TOKENS,
    TEXT_CONTEXT_COMPACTION_TRIGGER,
)

def build_compression_system_instruction() -> str:
    return (
        "You are compressing an existing multi-turn chat history for future context reuse.\n"
        "Write the summary in English only.\n"
        "Keep it plain text only. No JSON, no XML, no markdown tables.\n"
        "Preserve concrete facts, decisions, constraints, user preferences, unresolved questions, "
        "code context, and action items.\n"
        "Do not add new facts. Do not speculate. Do not rewrite into a response to the user.\n"
        "Favor dense factual notes over prose.\n"
        f"Target roughly {COMPRESSION_TARGET_MIN_TOKENS:,} to "
        f"{COMPRESSION_TARGET_MAX_TOKENS:,} tokens of content. The input is compacted around "
        f"{TEXT_CONTEXT_COMPACTION_TRIGGER:,} text tokens.\n"
        "You may copy full original sentences when they carry important detail.\n"
        "Retain enough detail for future turns instead of over-compressing the conversation."
    )


def build_compression_user_prompt(*, source_text: str) -> str:
    return (
        "Compress the following prior conversation context for future model input reuse.\n"
        "Retain the important details and drop repetition, filler, and low-signal phrasing.\n\n"
        "Conversation context to compress:\n"
        f"{source_text}"
    )
