from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies.db import get_db
from app.api.v1.dependencies.request import get_client_ip
from app.api.v1.presenters.authentication import (
    build_auth_session_envelope,
    build_conflict_resolution_response_error,
    build_conflict_ticket_response_error,
    build_session_lookup_response_error,
)
from app.auth.conflict_tickets import inspect_session_conflict_ticket, resolve_session_conflict
from app.auth.cookies import clear_session_conflict_cookie, clear_session_cookie, set_session_cookie
from app.auth.session_lifecycle import delete_session, resolve_session
from app.auth.types import SessionConflictResolutionError
from app.config.settings import settings
from app.schemas.authentication import AuthIssueResponse, AuthSessionEnvelope, SessionConflictResolveRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/me",
    response_model=AuthSessionEnvelope,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": AuthIssueResponse},
        status.HTTP_409_CONFLICT: {"model": AuthIssueResponse},
    },
)
def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> AuthSessionEnvelope:
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

    return build_auth_session_envelope(lookup.context)


@router.post(
    "/session-conflicts/resolve",
    response_model=AuthSessionEnvelope,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": AuthIssueResponse},
        status.HTTP_409_CONFLICT: {"model": AuthIssueResponse},
    },
)
def resolve_conflicting_session(
    payload: SessionConflictResolveRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionEnvelope:
    try:
        created_session = resolve_session_conflict(
            db,
            raw_session_key=request.cookies.get(settings.auth_session_cookie_name),
            raw_conflict_ticket=request.cookies.get(settings.auth_conflict_cookie_name),
            requested_auth_type=payload.auth_type,
            client_ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except SessionConflictResolutionError as exc:
        raise build_conflict_resolution_response_error(exc) from exc

    set_session_cookie(
        response,
        session_key=created_session.raw_session_key,
        persistent=created_session.context.persistent,
        absolute_expires_at=created_session.context.absolute_expires_at,
    )
    clear_session_conflict_cookie(response)
    return build_auth_session_envelope(created_session.context)


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
    clear_session_conflict_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
