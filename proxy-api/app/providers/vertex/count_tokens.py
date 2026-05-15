from __future__ import annotations

from dataclasses import dataclass

from app.providers.vertex.client import build_vertex_client


@dataclass(slots=True, frozen=True)
class VertexCountTokensPayload:
    provider_model: str
    location: str
    contents: list[dict[str, object]]
    config: object | None = None


async def count_vertex_input_tokens(*, payload: VertexCountTokensPayload) -> int | None:
    client = build_vertex_client(location=payload.location)
    try:
        async with client.aio as aio_client:
            response = await aio_client.models.count_tokens(
                model=payload.provider_model,
                contents=payload.contents,
                config=payload.config,
            )
        total_tokens = getattr(response, "total_tokens", None)
        return int(total_tokens) if total_tokens is not None else None
    finally:
        client.close()
