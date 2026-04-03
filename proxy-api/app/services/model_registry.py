"""
Purpose:
- Implement backend logic for model availability and model policy.

Current responsibilities:
- Expose the public model registry
- Map public model IDs to provider-specific model names
- Keep provider model names outside the public API contract

Notes:
- The backend, not the frontend, controls model availability.
"""

from dataclasses import dataclass

from app.config.ai import ai_settings
from app.schemas.model import ModelInfo

DEFAULT_MODEL_ID = "vertex-default"
VERTEX_PROVIDER = "vertex_ai"


@dataclass(slots=True, frozen=True)
class ModelDefinition:
    public_id: str
    provider: str
    provider_model: str
    display_name: str
    available: bool = True


def _build_default_model_definition() -> ModelDefinition:
    return ModelDefinition(
        public_id=DEFAULT_MODEL_ID,
        provider=VERTEX_PROVIDER,
        provider_model=ai_settings.vertex_ai_model,
        display_name=f"Vertex AI ({ai_settings.vertex_ai_model})",
        available=True,
    )


def list_available_models() -> list[ModelInfo]:
    model = _build_default_model_definition()
    return [
        ModelInfo(
            id=model.public_id,
            provider=model.provider,
            display_name=model.display_name,
            available=model.available,
        ),
    ]


def get_model_definition(model_id: str) -> ModelDefinition | None:
    model = _build_default_model_definition()
    if model_id != model.public_id:
        return None
    return model


def is_supported_model(model_id: str) -> bool:
    return get_model_definition(model_id) is not None
