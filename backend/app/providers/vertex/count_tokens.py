from __future__ import annotations

from dataclasses import dataclass

from app.providers.vertex.client import build_vertex_client


VERTEX_CHAT_COUNT_MODEL_SOURCE = "payload.provider_model"
VERTEX_ATTACHMENT_COUNT_MODEL_ID = "gemini-3-flash-preview"


@dataclass(slots=True, frozen=True)
class VertexCountTokensPayload:
    provider_model: str
    location: str
    contents: list[dict[str, object]]
    config: object | None = None


async def count_vertex_input_tokens(*, payload: VertexCountTokensPayload) -> int | None:
    # Chat text counting follows the exact model already embedded in the provider payload.
    client = build_vertex_client(location=payload.location)
    try:
        async with client.aio as aio_client:
            response = await aio_client.models.count_tokens(
                model=payload.provider_model,
                contents=payload.contents,
                config=payload.config,
            )
        total_tokens = getattr(response, "total_tokens", None)
        if total_tokens is None:
            raise RuntimeError("vertex input token count did not return a token value")
        return int(total_tokens)
    finally:
        client.close()
