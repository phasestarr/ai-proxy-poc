"""Vertex runtime model definitions derived from operator configuration."""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.types import ProviderModelDefinition, ProviderToolDefinition
from app.providers.vertex.config import VERTEX_MODELS
from app.providers.vertex.tools import get_vertex_tool_definitions

VERTEX_PROVIDER_ID = "vertex_ai"


@dataclass(slots=True, frozen=True)
class VertexModelRuntimeDefinition:
    public_id: str
    provider_model: str
    display_name: str
    location: str
    available: bool = True
    supported_tools: tuple[ProviderToolDefinition, ...] = ()

    def to_provider_model_definition(self) -> ProviderModelDefinition:
        return ProviderModelDefinition(self.public_id, VERTEX_PROVIDER_ID, self.display_name, self.available, self.supported_tools)


_VERTEX_MODELS = tuple(
    VertexModelRuntimeDefinition(
        public_id=model.public_id,
        provider_model=model.provider_model,
        display_name=model.display_name,
        location=model.location,
        available=model.available,
        supported_tools=get_vertex_tool_definitions(*model.supported_tool_ids),
    )
    for model in VERTEX_MODELS
)


def list_vertex_models() -> list[ProviderModelDefinition]:
    return [model.to_provider_model_definition() for model in _VERTEX_MODELS]


def resolve_vertex_model_runtime(*, public_model_id: str) -> VertexModelRuntimeDefinition:
    for model in _VERTEX_MODELS:
        if model.public_id == public_model_id:
            return model
    raise ValueError(f"unsupported vertex model: {public_model_id}")
