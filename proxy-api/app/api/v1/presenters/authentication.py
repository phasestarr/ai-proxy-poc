from __future__ import annotations

from fastapi import status

from app.api.v1.errors.authentication import AuthResponseError
from app.auth.types import (
    SessionConflictResolutionError,
    SessionConflictTicketLookupResult,
    SessionContext,
    SessionLimitExceededError,
    SessionLookupResult,
)
from app.schemas.authentication import AuthIssueResponse, AuthSessionEnvelope, SessionView


def build_session_view(context: SessionContext) -> SessionView:
    return SessionView(
        user_id=context.user_id,
        auth_type=context.auth_type,
        display_name=context.display_name,
        email=context.email,
        capabilities=context.capabilities,
        persistent=context.persistent,
        idle_expires_at=context.idle_expires_at,
        absolute_expires_at=context.absolute_expires_at,
    )


def build_auth_session_envelope(context: SessionContext) -> AuthSessionEnvelope:
    return AuthSessionEnvelope(session=build_session_view(context))


def build_conflict_ticket_response_error(
    lookup: SessionConflictTicketLookupResult,
) -> AuthResponseError:
    return AuthResponseError(
        status_code=status.HTTP_409_CONFLICT,
        payload=AuthIssueResponse(
            reason=lookup.reason,
            detail=lookup.detail,
            action="session_conflict",
            redirect_to="/",
            can_evict_oldest=True,
            auth_type=lookup.auth_type,
            session_limit=lookup.session_limit,
        ),
        clear_cookie=False,
        clear_conflict_cookie=lookup.should_clear_cookie,
    )


def build_session_lookup_response_error(lookup: SessionLookupResult) -> AuthResponseError:
    if lookup.reason == "revoked_session" and lookup.can_evict_oldest and lookup.auth_type:
        return AuthResponseError(
            status_code=status.HTTP_409_CONFLICT,
            payload=AuthIssueResponse(
                reason=lookup.reason,
                detail="This browser session was replaced by a newer login. You can evict the oldest active session and continue here.",
                action="session_conflict",
                redirect_to="/",
                can_evict_oldest=True,
                auth_type=lookup.auth_type,
                session_limit=lookup.session_limit,
            ),
            clear_cookie=False,
        )

    detail = "Sign in again to continue."
    if lookup.reason == "expired_session":
        detail = "Your session expired. Sign in again to continue."
    elif lookup.reason == "invalid_session":
        detail = "This session is no longer valid. Sign in again to continue."
    elif lookup.reason == "user_disabled":
        detail = "This user is disabled."

    return AuthResponseError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        payload=AuthIssueResponse(
            reason=lookup.reason,
            detail=detail,
            action="login",
            redirect_to="/",
        ),
        clear_cookie=lookup.should_clear_cookie,
    )


def build_session_limit_response_error(exc: SessionLimitExceededError) -> AuthResponseError:
    return AuthResponseError(
        status_code=status.HTTP_409_CONFLICT,
        payload=AuthIssueResponse(
            reason="session_limit_reached",
            detail=f"{exc.auth_type} session limit reached ({exc.session_limit}).",
            action="session_conflict",
            redirect_to="/",
            can_evict_oldest=True,
            auth_type=exc.auth_type,
            session_limit=exc.session_limit,
        ),
        clear_cookie=False,
    )


def build_conflict_resolution_response_error(exc: SessionConflictResolutionError) -> AuthResponseError:
    return AuthResponseError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        payload=AuthIssueResponse(
            reason=exc.reason,
            detail=exc.detail,
            action="login",
            redirect_to="/",
            auth_type=exc.auth_type,
        ),
        clear_cookie=True,
        clear_conflict_cookie=True,
    )

