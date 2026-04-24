"""
OpenAI-owned model catalog and runtime metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.openai.tools import get_openai_tool_definitions
from app.providers.types import ProviderModelDefinition, ProviderToolDefinition

OPENAI_PROVIDER_ID = "openai"

# To change OpenAI model list, change `here` and `config.py` preset-mapping.

@dataclass(slots=True, frozen=True)
class OpenAIModelRuntimeDefinition:
    public_id: str
    provider_model: str
    display_name: str
    available: bool = True
    supported_tools: tuple[ProviderToolDefinition, ...] = ()

    def to_provider_model_definition(self) -> ProviderModelDefinition:
        return ProviderModelDefinition(
            public_id=self.public_id,
            provider=OPENAI_PROVIDER_ID,
            display_name=self.display_name,
            available=self.available,
            supported_tools=self.supported_tools,
        )

_OPENAI_MODELS: tuple[OpenAIModelRuntimeDefinition, ...] = (
    OpenAIModelRuntimeDefinition(
        public_id="gpt-5.4",
        provider_model="gpt-5.4",
        display_name="GPT 5.4",
        available=True,
        supported_tools=get_openai_tool_definitions(
            "web_search",
            "retrieval",
            "code_execution",
        ),
    ),
    OpenAIModelRuntimeDefinition(
        public_id="gpt-5.4-mini",
        provider_model="gpt-5.4-mini",
        display_name="GPT 5.4 Mini",
        available=True,
        supported_tools=get_openai_tool_definitions(
            "web_search",
            "retrieval",
            "code_execution",
        ),
    ),
    OpenAIModelRuntimeDefinition(
        public_id="gpt-5.4-nano",
        provider_model="gpt-5.4-nano",
        display_name="GPT 5.4 Nano",
        available=True,
        supported_tools=get_openai_tool_definitions(
            "web_search",
            "retrieval",
            "code_execution",
        ),
    ),
)


def list_openai_models() -> list[ProviderModelDefinition]:
    return [model.to_provider_model_definition() for model in _OPENAI_MODELS]


def resolve_openai_model_runtime(*, public_model_id: str) -> OpenAIModelRuntimeDefinition:
    for model in _OPENAI_MODELS:
        if model.public_id == public_model_id:
            return model

    raise ValueError(f"unsupported openai model: {public_model_id}")
