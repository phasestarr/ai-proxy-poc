from __future__ import annotations

from app.providers.openai.client import build_openai_client


async def count_openai_input_tokens(*, payload: dict[str, object]) -> int | None:
    client = build_openai_client()
    try:
        response = await client.responses.input_tokens.count(**payload)
        input_tokens = getattr(response, "input_tokens", None)
        return int(input_tokens) if input_tokens is not None else None
    finally:
        await client.close()
