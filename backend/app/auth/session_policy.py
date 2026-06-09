from __future__ import annotations

from datetime import timedelta

from app.config.settings import settings
from app.auth.types import AuthType


def get_session_limit(auth_type: AuthType | str) -> int:
    if auth_type == "microsoft":
        return max(1, settings.auth_microsoft_max_sessions)
    return max(1, settings.auth_guest_max_sessions)


def get_session_ttl() -> timedelta:
    return timedelta(minutes=max(1, settings.auth_session_ttl_minutes))
