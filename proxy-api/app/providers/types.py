"""
Common provider contracts shared across provider implementations and service orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ProviderUsageMetadata:
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    total_token_count: int | None = None


@dataclass(slots=True, frozen=True)
class ProviderStreamChunk:
    text: str = ""
    response_id: str | None = None
    model_version: str | None = None
    finish_reason: str | None = None
    usage: ProviderUsageMetadata | None = None


@dataclass(slots=True, frozen=True)
class ProviderToolDefinition:
    public_id: str
    display_name: str
    available: bool = True


@dataclass(slots=True, frozen=True)
class ProviderModelDefinition:
    public_id: str
    provider: str
    provider_model: str
    display_name: str
    available: bool = True
    default: bool = False
    supported_tools: tuple[ProviderToolDefinition, ...] = ()

    @property
    def supported_tool_ids(self) -> tuple[str, ...]:
        return tuple(tool.public_id for tool in self.supported_tools if tool.available)


@dataclass(slots=True, frozen=True)
class ProviderRoute:
    model: ProviderModelDefinition
    tool_ids: tuple[str, ...] = ()
