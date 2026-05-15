from __future__ import annotations

from app.providers.anthropic.client import build_anthropic_client


async def count_anthropic_input_tokens(*, payload: dict[str, object]) -> int | None:
    client = build_anthropic_client()
    try:
        response = await client.beta.messages.count_tokens(**payload)
        input_tokens = getattr(response, "input_tokens", None)
        return int(input_tokens) if input_tokens is not None else None
    finally:
        await client.close()
