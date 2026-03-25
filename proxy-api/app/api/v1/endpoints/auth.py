"""
Purpose:
- Define authentication and current-session HTTP endpoints.

Responsibilities:
- Return current session information
- Issue guest sessions
- Revoke sessions on logout
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.auth import get_client_ip
from app.core.config import settings
from app.core.security import clear_session_cookie, set_session_cookie
from app.api.v1.dependencies.db import get_db
from app.schemas.auth import AuthAnonymousResponse, AuthSessionEnvelope, SessionView
from app.services.auth import create_guest_session, delete_session, resolve_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/me",
    response_model=AuthSessionEnvelope,
    responses={status.HTTP_401_UNAUTHORIZED: {"model": AuthAnonymousResponse}},
)
def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
):
    lookup = resolve_session(
        db,
        raw_session_key=request.cookies.get(settings.auth_session_cookie_name),
        client_ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        touch=True,
    )

    if lookup.context is None:
        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=AuthAnonymousResponse(reason=lookup.reason).model_dump(mode="json"),
        )
        if lookup.should_clear_cookie:
            clear_session_cookie(response)
        return response

    return AuthSessionEnvelope(
        session=SessionView(
            user_id=lookup.context.user_id,
            auth_type=lookup.context.auth_type,
            display_name=lookup.context.display_name,
            email=lookup.context.email,
            capabilities=lookup.context.capabilities,
            persistent=lookup.context.persistent,
            idle_expires_at=lookup.context.idle_expires_at,
            absolute_expires_at=lookup.context.absolute_expires_at,
        )
    )


@router.post("/login/guest", response_model=AuthSessionEnvelope)
def login_guest(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionEnvelope:
    created_session = create_guest_session(
        db,
        created_ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(
        response,
        session_key=created_session.raw_session_key,
        persistent=False,
    )
    return AuthSessionEnvelope(
        session=SessionView(
            user_id=created_session.context.user_id,
            auth_type=created_session.context.auth_type,
            display_name=created_session.context.display_name,
            email=created_session.context.email,
            capabilities=created_session.context.capabilities,
            persistent=created_session.context.persistent,
            idle_expires_at=created_session.context.idle_expires_at,
            absolute_expires_at=created_session.context.absolute_expires_at,
        )
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Response:
    delete_session(
        db,
        raw_session_key=request.cookies.get(settings.auth_session_cookie_name),
    )
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
