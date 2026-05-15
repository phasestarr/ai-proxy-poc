"""
Purpose:
- Define the top-level API router for the backend application.

Responsibilities:
- Aggregate versioned routers under a single entry point
- Keep route registration organized and explicit

Notes:
- This module remains focused on router composition only.
- Route implementation belongs in endpoint modules.
"""

from fastapi import APIRouter

from app.api.v1.api import api_router as v1_router

api_router = APIRouter(prefix="/api")
api_router.include_router(v1_router, prefix="/v1")
