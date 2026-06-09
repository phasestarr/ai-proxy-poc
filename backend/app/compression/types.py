from __future__ import annotations

from dataclasses import dataclass

from app.providers.types import ProviderUsageMetadata


class ContextCompressionError(RuntimeError):
    """Raised when the internal context compression pipeline fails."""


@dataclass(slots=True, frozen=True)
class CompressionResult:
    summary_text: str
    usage: ProviderUsageMetadata | None = None
