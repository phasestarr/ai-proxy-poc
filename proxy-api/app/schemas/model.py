"""
Purpose:
- Define API schemas related to model listing and model metadata.

Responsibilities:
- Represent the models visible to clients through the backend proxy
- Return only safe and intentionally exposed model information
"""

from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    provider: str
    display_name: str
    available: bool


class ModelListResponse(BaseModel):
    data: list[ModelInfo]
