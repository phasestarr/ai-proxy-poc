"""
FastAPI dependency helpers for API version 1.
"""

from app.api.v1.dependencies.auth import get_client_ip, require_authenticated_session, require_capability
from app.api.v1.dependencies.db import get_db

__all__ = [
    "get_client_ip",
    "get_db",
    "require_authenticated_session",
    "require_capability",
]
