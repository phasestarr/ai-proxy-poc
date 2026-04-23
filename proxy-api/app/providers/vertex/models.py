"""
Vertex-owned Gemini model catalog and runtime metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.types import ProviderModelDefinition, ProviderToolDefinition

VERTEX_PROVIDER_ID = "vertex_ai"

VERTEX_TOOL_WEB_SEARCH = ProviderToolDefinition(
    public_id="web_search",
    display_name="Google Search",
    available=True,
)
VERTEX_TOOL_RETRIEVAL = ProviderToolDefinition(
    public_id="retrieval",
    display_name="Vertex RAG",
    available=True,
)
VERTEX_TOOL_CODE_EXECUTION = ProviderToolDefinition(
    public_id="code_execution",
    display_name="Code Execution",
    available=True,
)
VERTEX_TOOL_URL_CONTEXT = ProviderToolDefinition(
    public_id="url_context",
    display_name="URL Context",
    available=True,
)


@dataclass(slots=True, frozen=True)
class VertexModelRuntimeDefinition:
    public_id: str
    provider_model: str
    display_name: str
    location: str
    available: bool = True
    supported_tools: tuple[ProviderToolDefinition, ...] = ()

    def to_provider_model_definition(self) -> ProviderModelDefinition:
        return ProviderModelDefinition(
            public_id=self.public_id,
            provider=VERTEX_PROVIDER_ID,
            display_name=self.display_name,
            available=self.available,
            supported_tools=self.supported_tools,
        )


_VERTEX_MODELS: tuple[VertexModelRuntimeDefinition, ...] = (
    VertexModelRuntimeDefinition(
        public_id="gemini-3.1-pro-preview",
        provider_model="gemini-3.1-pro-preview",
        display_name="Gemini 3.1 Pro Preview",
        location="global",
        available=True,
        supported_tools=(
            VERTEX_TOOL_WEB_SEARCH,
            VERTEX_TOOL_RETRIEVAL,
            VERTEX_TOOL_CODE_EXECUTION,
            VERTEX_TOOL_URL_CONTEXT,
        ),
    ),
    VertexModelRuntimeDefinition(
        public_id="gemini-3-flash-preview",
        provider_model="gemini-3-flash-preview",
        display_name="Gemini 3 Flash Preview",
        location="global",
        available=True,
        supported_tools=(
            VERTEX_TOOL_WEB_SEARCH,
            VERTEX_TOOL_RETRIEVAL,
            VERTEX_TOOL_CODE_EXECUTION,
            VERTEX_TOOL_URL_CONTEXT,
        ),
    ),
    VertexModelRuntimeDefinition(
        public_id="gemini-2.5-flash",
        provider_model="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        location="global",
        available=True,
        supported_tools=(
            VERTEX_TOOL_WEB_SEARCH,
            VERTEX_TOOL_RETRIEVAL,
            VERTEX_TOOL_CODE_EXECUTION,
            VERTEX_TOOL_URL_CONTEXT,
        ),
    )
)


def list_vertex_models() -> list[ProviderModelDefinition]:
    return [model.to_provider_model_definition() for model in _VERTEX_MODELS]


def resolve_vertex_model_runtime(*, public_model_id: str) -> VertexModelRuntimeDefinition:
    for model in _VERTEX_MODELS:
        if model.public_id == public_model_id:
            return model

    raise ValueError(f"unsupported vertex model: {public_model_id}")
