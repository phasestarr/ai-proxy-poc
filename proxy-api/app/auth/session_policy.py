from __future__ import annotations

from datetime import timedelta

from app.config.settings import settings
from app.auth.types import AuthType


def get_session_limit(auth_type: AuthType | str) -> int:
    if auth_type == "microsoft":
        return max(1, settings.auth_microsoft_max_sessions)
    return max(1, settings.auth_guest_max_sessions)


def get_idle_duration(auth_type: AuthType | str) -> timedelta:
    if auth_type == "microsoft":
        return timedelta(minutes=settings.auth_microsoft_idle_minutes)
    return timedelta(minutes=settings.auth_guest_idle_minutes)


def get_absolute_duration(auth_type: AuthType | str) -> timedelta:
    if auth_type == "microsoft":
        return timedelta(days=settings.auth_microsoft_absolute_days)
    return timedelta(hours=settings.auth_guest_absolute_hours)

