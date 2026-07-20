"""OpenAI runtime model definitions derived from operator configuration."""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.openai.config import OPENAI_MODELS
from app.providers.openai.tools import get_openai_tool_definitions
from app.providers.types import ProviderModelDefinition, ProviderToolDefinition

OPENAI_PROVIDER_ID = "openai"


@dataclass(slots=True, frozen=True)
class OpenAIModelRuntimeDefinition:
    public_id: str
    provider_model: str
    display_name: str
    available: bool = True
    supported_tools: tuple[ProviderToolDefinition, ...] = ()

    def to_provider_model_definition(self) -> ProviderModelDefinition:
        return ProviderModelDefinition(self.public_id, OPENAI_PROVIDER_ID, self.display_name, self.available, self.supported_tools)


_OPENAI_MODELS = tuple(
    OpenAIModelRuntimeDefinition(
        public_id=model.public_id,
        provider_model=model.provider_model,
        display_name=model.display_name,
        available=model.available,
        supported_tools=get_openai_tool_definitions(*model.supported_tool_ids),
    )
    for model in OPENAI_MODELS
)


def list_openai_models() -> list[ProviderModelDefinition]:
    return [model.to_provider_model_definition() for model in _OPENAI_MODELS]


def resolve_openai_model_runtime(*, public_model_id: str) -> OpenAIModelRuntimeDefinition:
    for model in _OPENAI_MODELS:
        if model.public_id == public_model_id:
            return model
    raise ValueError(f"unsupported openai model: {public_model_id}")
