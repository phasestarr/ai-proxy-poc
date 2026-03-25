"""
Purpose:
- Define shared security helpers used by authentication and session handling.

Responsibilities:
- Generate and hash session identifiers
- Build cookie parameters consistently
- Keep reusable security-related helpers outside of endpoint modules
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import secrets

from starlette.responses import Response

from app.core.config import settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_session_key() -> str:
    return f"s1_{secrets.token_urlsafe(32)}"


def hash_session_key(raw_session_key: str) -> str:
    return hashlib.sha256(raw_session_key.encode("utf-8")).hexdigest()


def build_guest_display_name() -> str:
    return f"Guest-{secrets.token_hex(3).upper()}"


def set_session_cookie(
    response: Response,
    *,
    session_key: str,
    persistent: bool,
    absolute_expires_at: datetime | None = None,
) -> None:
    cookie_args: dict[str, object] = {
        "key": settings.auth_session_cookie_name,
        "value": session_key,
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "path": settings.auth_cookie_path,
    }

    if settings.auth_cookie_domain:
        cookie_args["domain"] = settings.auth_cookie_domain

    if persistent and absolute_expires_at is not None:
        max_age = max(0, int((absolute_expires_at - utc_now()).total_seconds()))
        cookie_args["expires"] = absolute_expires_at
        cookie_args["max_age"] = max_age

    response.set_cookie(**cookie_args)


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_session_cookie_name,
        path=settings.auth_cookie_path,
        domain=settings.auth_cookie_domain,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
