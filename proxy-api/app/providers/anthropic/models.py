"""
Anthropic-owned Claude model catalog and runtime metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.anthropic.tools import get_anthropic_tool_definitions
from app.providers.types import ProviderModelDefinition, ProviderToolDefinition

ANTHROPIC_PROVIDER_ID = "anthropic"

# To change Anthropic model list, change `here` and `config.py` preset-mapping.

@dataclass(slots=True, frozen=True)
class AnthropicModelRuntimeDefinition:
    public_id: str
    provider_model: str
    display_name: str
    available: bool = True
    supported_tools: tuple[ProviderToolDefinition, ...] = ()

    def to_provider_model_definition(self) -> ProviderModelDefinition:
        return ProviderModelDefinition(
            public_id=self.public_id,
            provider=ANTHROPIC_PROVIDER_ID,
            display_name=self.display_name,
            available=self.available,
            supported_tools=self.supported_tools,
        )


_ANTHROPIC_MODELS: tuple[AnthropicModelRuntimeDefinition, ...] = (
    AnthropicModelRuntimeDefinition(
        public_id="claude-opus-4-7",
        provider_model="claude-opus-4-7",
        display_name="Claude Opus 4.7",
        available=False,
        supported_tools=get_anthropic_tool_definitions(
            "web_search",
            "code_execution",
        ),
    ),
    AnthropicModelRuntimeDefinition(
        public_id="claude-sonnet-4-6",
        provider_model="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        available=True,
        supported_tools=get_anthropic_tool_definitions(
            "web_search",
            "code_execution",
        ),
    ),
    AnthropicModelRuntimeDefinition(
        public_id="claude-haiku-4-5",
        provider_model="claude-haiku-4-5",
        display_name="Claude Haiku 4.5",
        available=True,
        supported_tools=get_anthropic_tool_definitions(
            "web_search",
            "code_execution",
        ),
    ),
)


def list_anthropic_models() -> list[ProviderModelDefinition]:
    return [model.to_provider_model_definition() for model in _ANTHROPIC_MODELS]


def resolve_anthropic_model_runtime(*, public_model_id: str) -> AnthropicModelRuntimeDefinition:
    for model in _ANTHROPIC_MODELS:
        if model.public_id == public_model_id:
            return model

    raise ValueError(f"unsupported anthropic model: {public_model_id}")
