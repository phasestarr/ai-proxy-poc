"""Anthropic runtime model definitions derived from operator configuration."""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.anthropic.config import ANTHROPIC_MODELS
from app.providers.anthropic.tools import get_anthropic_tool_definitions
from app.providers.types import ProviderModelDefinition, ProviderToolDefinition

ANTHROPIC_PROVIDER_ID = "anthropic"


@dataclass(slots=True, frozen=True)
class AnthropicModelRuntimeDefinition:
    public_id: str
    provider_model: str
    display_name: str
    available: bool = True
    supported_tools: tuple[ProviderToolDefinition, ...] = ()

    def to_provider_model_definition(self) -> ProviderModelDefinition:
        return ProviderModelDefinition(self.public_id, ANTHROPIC_PROVIDER_ID, self.display_name, self.available, self.supported_tools)


_ANTHROPIC_MODELS = tuple(
    AnthropicModelRuntimeDefinition(
        public_id=model.public_id,
        provider_model=model.provider_model,
        display_name=model.display_name,
        available=model.available,
        supported_tools=get_anthropic_tool_definitions(*model.supported_tool_ids),
    )
    for model in ANTHROPIC_MODELS
)


def list_anthropic_models() -> list[ProviderModelDefinition]:
    return [model.to_provider_model_definition() for model in _ANTHROPIC_MODELS]


def resolve_anthropic_model_runtime(*, public_model_id: str) -> AnthropicModelRuntimeDefinition:
    for model in _ANTHROPIC_MODELS:
        if model.public_id == public_model_id:
            return model
    raise ValueError(f"unsupported anthropic model: {public_model_id}")
