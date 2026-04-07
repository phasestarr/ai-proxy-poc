"""
Purpose:
- Define model listing and model metadata related HTTP endpoints.

Responsibilities:
- Return models available through the backend proxy
- Expose provider-safe metadata only
- Hide provider internals that should not be public

Notes:
- Model policy is controlled by backend service logic.
- This file should remain thin and compositional.
"""

from fastapi import APIRouter

from app.providers.catalog import list_available_models
from app.schemas.model import ModelListResponse

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelListResponse)
def list_models() -> ModelListResponse:
    return ModelListResponse(data=list_available_models())
