from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.config.time import utc_now
from app.providers.types import ThinkingDeltaBlock, ToolUsageBlock


@dataclass(slots=True, frozen=True)
class CompletedProviderBlock:
    type: str
    provider_block_id: str
    text: str
    metadata: dict[str, object]
    raw_events: list[object]
    started_at: datetime
    completed_at: datetime


@dataclass(slots=True)
class _AccumulatedProviderBlock:
    type: str
    provider_block_id: str
    started_at: datetime
    text: str = ""
    metadata: dict[str, object] = field(default_factory=dict)
    raw_events: list[object] = field(default_factory=list)


class ProviderBlockAccumulator:
    def __init__(self) -> None:
        self._blocks: dict[tuple[str, str], _AccumulatedProviderBlock] = {}

    def ingest(self, block: ThinkingDeltaBlock | ToolUsageBlock) -> CompletedProviderBlock | None:
        if isinstance(block, ThinkingDeltaBlock):
            return self._ingest_thinking(block)
        return self._ingest_tool(block)

    def _ingest_thinking(self, block: ThinkingDeltaBlock) -> CompletedProviderBlock | None:
        now = utc_now()
        state = self._get_or_create(
            type="thinking",
            provider_block_id=block.block_id,
            now=now,
        )
        if block.text_delta:
            state.text = f"{state.text}{block.text_delta}"
        state.metadata = block.metadata
        if block.operation != "end":
            return None
        del self._blocks[("thinking", block.block_id)]
        return CompletedProviderBlock(
            type="thinking",
            provider_block_id=block.block_id,
            text=state.text,
            metadata=state.metadata,
            raw_events=[],
            started_at=state.started_at,
            completed_at=now,
        )

    def _ingest_tool(self, block: ToolUsageBlock) -> CompletedProviderBlock | None:
        now = utc_now()
        state = self._get_or_create(
            type="tool",
            provider_block_id=block.block_id,
            now=now,
        )
        state.metadata = block.metadata
        state.raw_events.append(block.raw)
        if block.operation != "end":
            return None
        del self._blocks[("tool", block.block_id)]
        return CompletedProviderBlock(
            type="tool",
            provider_block_id=block.block_id,
            text="",
            metadata=state.metadata,
            raw_events=state.raw_events,
            started_at=state.started_at,
            completed_at=now,
        )

    def _get_or_create(
        self,
        *,
        type: str,
        provider_block_id: str,
        now: datetime,
    ) -> _AccumulatedProviderBlock:
        key = (type, provider_block_id)
        block = self._blocks.get(key)
        if block is not None:
            return block
        block = _AccumulatedProviderBlock(
            type=type,
            provider_block_id=provider_block_id,
            started_at=now,
        )
        self._blocks[key] = block
        return block
