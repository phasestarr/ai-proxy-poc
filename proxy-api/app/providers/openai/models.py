"""
OpenAI-owned model catalog and runtime metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.types import ProviderModelDefinition, ProviderToolDefinition

OPENAI_PROVIDER_ID = "openai"

OPENAI_TOOL_WEB_SEARCH = ProviderToolDefinition(
    public_id="web_search",
    display_name="Web Search",
    available=True,
)
OPENAI_TOOL_RETRIEVAL = ProviderToolDefinition(
    public_id="retrieval",
    display_name="File Search",
    available=True,
)
OPENAI_TOOL_CODE_EXECUTION = ProviderToolDefinition(
    public_id="code_execution",
    display_name="Code Interpreter",
    available=True,
)


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
        supported_tools=(
            OPENAI_TOOL_WEB_SEARCH,
            OPENAI_TOOL_RETRIEVAL,
            OPENAI_TOOL_CODE_EXECUTION,
        ),
    ),
    OpenAIModelRuntimeDefinition(
        public_id="gpt-5.4-mini",
        provider_model="gpt-5.4-mini",
        display_name="GPT 5.4 Mini",
        available=True,
        supported_tools=(
            OPENAI_TOOL_WEB_SEARCH,
            OPENAI_TOOL_RETRIEVAL,
            OPENAI_TOOL_CODE_EXECUTION,
        ),
    ),
    OpenAIModelRuntimeDefinition(
        public_id="gpt-5-mini",
        provider_model="gpt-5-mini",
        display_name="GPT 5 Mini",
        available=True,
        supported_tools=(
            OPENAI_TOOL_WEB_SEARCH,
            OPENAI_TOOL_RETRIEVAL,
            OPENAI_TOOL_CODE_EXECUTION,
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
