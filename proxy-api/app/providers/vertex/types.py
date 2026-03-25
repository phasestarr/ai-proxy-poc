"""
Purpose:
- Define Vertex-specific internal helper types.

Responsibilities:
- Represent normalized stream chunks emitted by the provider adapter
- Keep provider SDK types out of service-layer contracts

Notes:
- Do not let provider-specific types leak into the public API layer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class VertexUsageMetadata:
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    total_token_count: int | None = None


@dataclass(slots=True, frozen=True)
class VertexStreamChunk:
    text: str = ""
    response_id: str | None = None
    model_version: str | None = None
    finish_reason: str | None = None
    usage: VertexUsageMetadata | None = None
