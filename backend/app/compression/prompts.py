from __future__ import annotations


COMPRESSION_SYSTEM_INSTRUCTION = (
    "You are compressing an existing multi-turn chat history for future context reuse.\n"
    "Write the summary in English only.\n"
    "Keep it plain text only. No JSON, no XML, no markdown tables.\n"
    "Preserve concrete facts, decisions, constraints, user preferences, unresolved questions, "
    "code context, and action items.\n"
    "Do not add new facts. Do not speculate. Do not rewrite into a response to the user.\n"
    "Favor dense factual notes over prose.\n"
    "Target roughly 5,000 to 10,000 tokens worth of content. The input is roughly 100,000 tokens, so it's 5%~10% of the input size.\n"
    "You may copy full original sentences if you think it's important."
    "Remember, 5,000 to 10,000 token is larger than you think. Try to write as long as you can. You don't have to drop too many information to compact it."
)


def build_compression_user_prompt(*, source_text: str) -> str:
    return (
        "Compress the following prior conversation context for future model input reuse.\n"
        "Retain the important details and drop repetition, filler, and low-signal phrasing.\n\n"
        "Conversation context to compress:\n"
        f"{source_text}"
    )
