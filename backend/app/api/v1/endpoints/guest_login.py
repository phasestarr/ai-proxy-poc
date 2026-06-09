from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies.db import get_db
from app.api.v1.dependencies.request import get_client_ip
from app.api.v1.presenters.authentication import build_auth_session_envelope, build_session_limit_response_error
from app.auth.cookies import set_session_cookie
from app.auth.guest_sessions import create_guest_session
from app.auth.types import SessionLimitExceededError
from app.schemas.authentication import AuthSessionEnvelope

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login/guest", response_model=AuthSessionEnvelope)
def login_guest(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionEnvelope:
    try:
        created_session = create_guest_session(
            db,
            created_ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except SessionLimitExceededError as exc:
        raise build_session_limit_response_error(exc) from exc

    set_session_cookie(
        response,
        session_key=created_session.raw_session_key,
        persistent=False,
    )
    return build_auth_session_envelope(created_session.context)

