from __future__ import annotations

from datetime import datetime

from starlette.responses import Response

from app.config.settings import settings
from app.config.time import utc_now

AUTH_COOKIE_SAMESITE = "strict"


def set_session_cookie(
    response: Response,
    *,
    session_key: str,
    persistent: bool,
    expires_at: datetime | None = None,
) -> None:
    cookie_args: dict[str, object] = {
        "key": settings.auth_session_cookie_name,
        "value": session_key,
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": AUTH_COOKIE_SAMESITE,
        "path": settings.auth_cookie_path,
    }

    if settings.auth_cookie_domain:
        cookie_args["domain"] = settings.auth_cookie_domain

    if persistent and expires_at is not None:
        max_age = max(0, int((expires_at - utc_now()).total_seconds()))
        cookie_args["expires"] = expires_at
        cookie_args["max_age"] = max_age

    response.set_cookie(**cookie_args)


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_session_cookie_name,
        path=settings.auth_cookie_path,
        domain=settings.auth_cookie_domain,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
    )


def set_session_conflict_cookie(
    response: Response,
    *,
    conflict_ticket: str,
    expires_at: datetime,
) -> None:
    cookie_args: dict[str, object] = {
        "key": settings.auth_conflict_cookie_name,
        "value": conflict_ticket,
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": AUTH_COOKIE_SAMESITE,
        "path": settings.auth_cookie_path,
        "expires": expires_at,
        "max_age": max(0, int((expires_at - utc_now()).total_seconds())),
    }

    if settings.auth_cookie_domain:
        cookie_args["domain"] = settings.auth_cookie_domain

    response.set_cookie(**cookie_args)


def clear_session_conflict_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_conflict_cookie_name,
        path=settings.auth_cookie_path,
        domain=settings.auth_cookie_domain,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
    )
