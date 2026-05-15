"""
FastAPI dependency helpers for API version 1.
"""

from app.api.v1.dependencies.db import get_db
from app.api.v1.dependencies.request import get_client_ip
from app.api.v1.dependencies.session import require_authenticated_session, require_capability

__all__ = [
    "get_client_ip",
    "get_db",
    "require_authenticated_session",
    "require_capability",
]
