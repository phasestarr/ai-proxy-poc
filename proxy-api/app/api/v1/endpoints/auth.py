"""
Purpose:
- Define authentication and current-session HTTP endpoints.

Responsibilities:
- Return current session information
- Issue guest sessions
- Revoke sessions on logout
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.auth import get_client_ip
from app.config.settings import settings
from app.api.v1.dependencies.db import get_db
from app.schemas.auth import AuthAnonymousResponse, AuthSessionEnvelope, SessionView
from app.services.auth import create_guest_session, delete_session, resolve_session
from app.services.auth_security import clear_session_cookie, set_session_cookie
from app.services.microsoft_auth import (
    MicrosoftOAuthConfigurationError,
    MicrosoftOAuthRedirectError,
    build_microsoft_authorization_url,
    complete_microsoft_authorization,
    get_microsoft_return_to,
)

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


@router.get("/login/microsoft")
def login_microsoft(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        authorization_url = build_microsoft_authorization_url(
            db,
            redirect_uri=_build_external_redirect_uri(request),
            return_to=request.query_params.get("return_to"),
            requester_ip=get_client_ip(request),
            requester_user_agent=request.headers.get("user-agent"),
        )
    except MicrosoftOAuthConfigurationError:
        return _build_frontend_redirect("/", auth_error="microsoft_login_unavailable")
    except MicrosoftOAuthRedirectError as exc:
        return _build_frontend_redirect(exc.return_to or "/", auth_error=exc.error_code)

    return RedirectResponse(url=authorization_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback/microsoft")
def callback_microsoft(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    auth_response = dict(request.query_params)
    fallback_return_to = get_microsoft_return_to(db, state=auth_response.get("state"))

    try:
        created_session, return_to = complete_microsoft_authorization(
            db,
            auth_response=auth_response,
            redirect_uri=_build_external_redirect_uri(request),
            requester_ip=get_client_ip(request),
            requester_user_agent=request.headers.get("user-agent"),
        )
    except MicrosoftOAuthConfigurationError:
        return _build_frontend_redirect(fallback_return_to, auth_error="microsoft_login_unavailable")
    except MicrosoftOAuthRedirectError as exc:
        return _build_frontend_redirect(exc.return_to or fallback_return_to, auth_error=exc.error_code)

    response = _build_frontend_redirect(return_to)
    set_session_cookie(
        response,
        session_key=created_session.raw_session_key,
        persistent=created_session.context.persistent,
        absolute_expires_at=created_session.context.absolute_expires_at,
    )
    return response


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


def _build_external_redirect_uri(request: Request) -> str:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    forwarded_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    ).split(",")[0].strip()
    forwarded_port = (request.headers.get("x-forwarded-port") or "").split(",")[0].strip()

    host = forwarded_host
    if host and ":" not in host and forwarded_port:
        is_default_port = (forwarded_proto == "https" and forwarded_port == "443") or (
            forwarded_proto == "http" and forwarded_port == "80"
        )
        if not is_default_port:
            host = f"{host}:{forwarded_port}"

    return f"{forwarded_proto}://{host}{settings.microsoft_redirect_path}"


def _build_frontend_redirect(
    return_to: str,
    *,
    auth_error: str | None = None,
) -> RedirectResponse:
    normalized_return_to = _normalize_return_to(return_to)
    if auth_error:
        normalized_return_to = _append_query_param(normalized_return_to, "auth_error", auth_error)
    return RedirectResponse(url=normalized_return_to, status_code=status.HTTP_302_FOUND)


def _normalize_return_to(return_to: str | None) -> str:
    candidate = (return_to or "/").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    return candidate


def _append_query_param(path: str, key: str, value: str) -> str:
    split_result = urlsplit(path)
    query_items = parse_qsl(split_result.query, keep_blank_values=True)
    query_items = [(item_key, item_value) for item_key, item_value in query_items if item_key != key]
    query_items.append((key, value))
    return urlunsplit(
        (
            split_result.scheme,
            split_result.netloc,
            split_result.path,
            urlencode(query_items),
            split_result.fragment,
        )
    )
