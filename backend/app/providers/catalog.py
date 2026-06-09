"""
Purpose:
- Hold the backend-owned provider catalog and request resolution logic.

Responsibilities:
- Expose safe model metadata to the API layer
- Resolve public model and tool selections into provider routes
- Keep provider-specific model bindings out of service modules
"""

from __future__ import annotations

from app.providers.anthropic.provider import list_anthropic_models
from app.providers.openai.provider import list_openai_models
from app.providers.types import ProviderModelDefinition, ProviderRoute
from app.providers.vertex.provider import list_vertex_models
from app.schemas.model import ModelInfo, ToolInfo


def list_available_models() -> list[ModelInfo]:
    return [
        ModelInfo(
            id=model.public_id,
            provider=model.provider,
            display_name=model.display_name,
            available=model.available,
            tools=[
                ToolInfo(
                    id=tool.public_id,
                    display_name=tool.display_name,
                    available=tool.available,
                )
                for tool in model.supported_tools
            ],
        )
        for model in _list_provider_models()
    ]


def resolve_provider_route(
    *,
    model_id: str | None,
    tool_ids: list[str] | None,
) -> ProviderRoute:
    models = _list_provider_models()
    selected_model = _resolve_model(models=models, model_id=model_id)
    normalized_tool_ids = _normalize_tool_ids(tool_ids)
    _validate_tool_ids(model=selected_model, tool_ids=normalized_tool_ids)
    return ProviderRoute(
        model=selected_model,
        tool_ids=normalized_tool_ids,
    )


def _list_provider_models() -> list[ProviderModelDefinition]:
    return [
        *list_anthropic_models(),
        *list_openai_models(),
        *list_vertex_models(),
    ]


def _resolve_model(*, models: list[ProviderModelDefinition], model_id: str | None) -> ProviderModelDefinition:
    normalized_model_id = (model_id or "").strip()
    if not normalized_model_id:
        raise ValueError("model selection is required")

    for model in models:
        if model.public_id == normalized_model_id:
            if not model.available:
                raise ValueError(f"model is not available: {normalized_model_id}")
            return model

    raise ValueError(f"unsupported model: {normalized_model_id}")


def _normalize_tool_ids(tool_ids: list[str] | None) -> tuple[str, ...]:
    if not tool_ids:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for tool_id in tool_ids:
        candidate = tool_id.strip()
        if not candidate or candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
    return tuple(normalized)


def _validate_tool_ids(*, model: ProviderModelDefinition, tool_ids: tuple[str, ...]) -> None:
    supported_tool_ids = set(model.supported_tool_ids)
    for tool_id in tool_ids:
        if tool_id not in supported_tool_ids:
            raise ValueError(f"tool is not supported for model {model.public_id}: {tool_id}")
