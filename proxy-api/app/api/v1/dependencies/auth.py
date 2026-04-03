"""
Purpose:
- Provide reusable authentication dependencies for protected API routes.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.api.v1.dependencies.db import get_db
from app.services.auth import SessionContext, resolve_session


def get_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.client.host if request.client is not None else None


def require_authenticated_session(
    request: Request,
    db: Session = Depends(get_db),
) -> SessionContext:
    lookup = resolve_session(
        db,
        raw_session_key=request.cookies.get(settings.auth_session_cookie_name),
        client_ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        touch=True,
    )

    if lookup.context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )

    return lookup.context


def require_capability(capability: str):
    def dependency(
        session: SessionContext = Depends(require_authenticated_session),
    ) -> SessionContext:
        if capability not in session.capabilities:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing capability: {capability}",
            )
        return session

    return dependency
