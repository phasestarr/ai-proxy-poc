from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.db import get_db
from app.api.v1.dependencies.request import get_client_ip
from app.api.v1.presenters.authentication_redirects import (
    build_external_microsoft_redirect_uri,
    build_frontend_redirect,
)
from app.auth.cookies import clear_session_conflict_cookie, set_session_conflict_cookie, set_session_cookie
from app.auth.microsoft_oauth import (
    MicrosoftOAuthConfigurationError,
    MicrosoftOAuthRedirectError,
    build_microsoft_authorization_url,
    complete_microsoft_authorization,
    get_microsoft_return_to,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login/microsoft")
def login_microsoft(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        authorization_url = build_microsoft_authorization_url(
            db,
            redirect_uri=build_external_microsoft_redirect_uri(request),
            return_to=request.query_params.get("return_to"),
            requester_ip=get_client_ip(request),
            requester_user_agent=request.headers.get("user-agent"),
        )
    except MicrosoftOAuthConfigurationError:
        return build_frontend_redirect("/", auth_error="microsoft_login_unavailable")
    except MicrosoftOAuthRedirectError as exc:
        return build_frontend_redirect(exc.return_to or "/", auth_error=exc.error_code)

    return RedirectResponse(url=authorization_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback/microsoft")
def callback_microsoft(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    auth_response = dict(request.query_params)
    fallback_return_to = get_microsoft_return_to(db, state=auth_response.get("state"))

    try:
        completion = complete_microsoft_authorization(
            db,
            auth_response=auth_response,
            redirect_uri=build_external_microsoft_redirect_uri(request),
            requester_ip=get_client_ip(request),
            requester_user_agent=request.headers.get("user-agent"),
        )
    except MicrosoftOAuthConfigurationError:
        return build_frontend_redirect(fallback_return_to, auth_error="microsoft_login_unavailable")
    except MicrosoftOAuthRedirectError as exc:
        return build_frontend_redirect(exc.return_to or fallback_return_to, auth_error=exc.error_code)

    response = build_frontend_redirect(completion.return_to)
    if completion.conflict_ticket is not None:
        set_session_conflict_cookie(
            response,
            conflict_ticket=completion.conflict_ticket.raw_ticket,
            expires_at=completion.conflict_ticket.expires_at,
        )
        return response

    if completion.created_session is None:
        return build_frontend_redirect(completion.return_to, auth_error="microsoft_login_failed")

    set_session_cookie(
        response,
        session_key=completion.created_session.raw_session_key,
        persistent=completion.created_session.context.persistent,
        absolute_expires_at=completion.created_session.context.absolute_expires_at,
    )
    clear_session_conflict_cookie(response)
    return response

