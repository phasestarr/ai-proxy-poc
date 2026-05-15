"""
Purpose:
- Register and compose all version 1 endpoint routers.

Responsibilities:
- Include model and chat routes for current PoC scope
- Apply clear tags and route prefixes per domain

Notes:
- Keep this file as a routing index for API version 1.
- Do not place endpoint business logic here.
"""

from fastapi import APIRouter

from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.guest_login import router as guest_login_router
from app.api.v1.endpoints.microsoft_login import router as microsoft_login_router
from app.api.v1.endpoints.models import router as models_router
from app.api.v1.endpoints.session_endpoints import router as session_router

api_router = APIRouter()
api_router.include_router(session_router)
api_router.include_router(guest_login_router)
api_router.include_router(microsoft_login_router)
api_router.include_router(models_router)
api_router.include_router(chat_router)
