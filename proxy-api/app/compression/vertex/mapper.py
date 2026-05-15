from __future__ import annotations

from app.providers.types import ProviderUsageMetadata


def map_compression_usage(response) -> ProviderUsageMetadata | None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    return ProviderUsageMetadata(
        prompt_token_count=getattr(usage, "prompt_token_count", None),
        candidates_token_count=getattr(usage, "candidates_token_count", None),
        total_token_count=getattr(usage, "total_token_count", None),
    )
