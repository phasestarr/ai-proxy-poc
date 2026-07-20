from __future__ import annotations

from app.providers.openai.client import build_openai_client


async def count_openai_input_tokens(*, payload: dict[str, object]) -> int | None:
    # Chat text counting follows the exact model already embedded in the provider payload.
    client = build_openai_client()
    try:
        response = await client.responses.input_tokens.count(**payload)
        input_tokens = getattr(response, "input_tokens", None)
        if input_tokens is None:
            raise RuntimeError("openai input token count did not return a token value")
        return int(input_tokens)
    finally:
        await client.close()
