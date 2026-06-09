from __future__ import annotations

from app.providers.anthropic.client import build_anthropic_client


ANTHROPIC_CHAT_COUNT_MODEL_SOURCE = "payload.model"
ANTHROPIC_ATTACHMENT_COUNT_MODEL_ID = "claude-haiku-4-5"


async def count_anthropic_input_tokens(*, payload: dict[str, object]) -> int | None:
    # Chat text counting follows the exact model already embedded in the provider payload.
    client = build_anthropic_client()
    try:
        response = await client.beta.messages.count_tokens(**payload)
        input_tokens = getattr(response, "input_tokens", None)
        if input_tokens is None:
            raise RuntimeError("anthropic input token count did not return a token value")
        return int(input_tokens)
    finally:
        await client.close()
