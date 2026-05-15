from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies.db import get_db
from app.api.v1.dependencies.request import get_client_ip
from app.api.v1.presenters.authentication import (
    build_conflict_ticket_response_error,
    build_session_lookup_response_error,
)
from app.auth.conflict_tickets import inspect_session_conflict_ticket
from app.auth.session_lifecycle import resolve_session
from app.auth.types import SessionContext
from app.config.settings import settings


def require_authenticated_session(
    request: Request,
    db: Session = Depends(get_db),
) -> SessionContext:
    conflict_lookup = inspect_session_conflict_ticket(
        db,
        raw_conflict_ticket=request.cookies.get(settings.auth_conflict_cookie_name),
    )
    if conflict_lookup.has_conflict:
        raise build_conflict_ticket_response_error(conflict_lookup)

    lookup = resolve_session(
        db,
        raw_session_key=request.cookies.get(settings.auth_session_cookie_name),
        client_ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        touch=True,
    )

    if lookup.context is None:
        auth_error = build_session_lookup_response_error(lookup)
        auth_error.clear_conflict_cookie = conflict_lookup.should_clear_cookie
        raise auth_error

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

