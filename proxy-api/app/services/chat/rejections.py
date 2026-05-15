from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.config.time import utc_now
from app.db.postgres.models.chat_request_rejection import ChatRequestRejection
from app.providers.types import ProviderRoute
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.errors import ChatProxyError

REQUEST_VALIDATION_ERROR_CODE = "request_validation_failed"


@dataclass(slots=True, frozen=True)
class RejectionPayload:
    chat_history_id: str | None = None
    draft_chat_id: str | None = None
    model_id: str | None = None


def persist_chat_request_rejection(
    db: Session,
    *,
    session: SessionContext | None,
    payload: ChatCompletionRequest | RejectionPayload | None,
    error_code: str,
    detail: str,
    http_status: int | None,
    retry_after_seconds: int | None = None,
    route: ProviderRoute | None = None,
) -> None:
    normalized_payload = normalize_rejection_payload(payload)
    rejection = ChatRequestRejection(
        id=str(uuid4()),
        user_id=session.user_id if session else None,
        auth_session_id=session.session_id if session else None,
        chat_history_id=normalized_payload.chat_history_id,
        draft_chat_id=normalized_payload.draft_chat_id,
        model_id=route.model.public_id if route else normalized_payload.model_id,
        provider=route.model.provider if route else None,
        error_code=error_code,
        http_status=http_status,
        retry_after_seconds=retry_after_seconds,
        detail=detail,
        created_at=utc_now(),
    )
    db.add(rejection)
    db.commit()


def persist_chat_request_validation_rejection(
    db: Session,
    *,
    session: SessionContext | None,
    validation_error: RequestValidationError,
) -> None:
    payload = normalize_rejection_payload(validation_error.body)
    detail = summarize_validation_error(validation_error)
    persist_chat_request_rejection(
        db,
        session=session,
        payload=payload,
        error_code=REQUEST_VALIDATION_ERROR_CODE,
        detail=detail,
        http_status=422,
    )


def normalize_rejection_payload(
    payload: ChatCompletionRequest | RejectionPayload | dict[str, Any] | None,
) -> RejectionPayload:
    if payload is None:
        return RejectionPayload()
    if isinstance(payload, ChatCompletionRequest):
        return RejectionPayload(
            chat_history_id=payload.chat_history_id,
            draft_chat_id=payload.draft_chat_id,
            model_id=payload.model_id,
        )
    if isinstance(payload, RejectionPayload):
        return payload
    if isinstance(payload, dict):
        chat_history_id = payload.get("chat_history_id")
        draft_chat_id = payload.get("draft_chat_id")
        model_id = payload.get("model_id")
        return RejectionPayload(
            chat_history_id=chat_history_id.strip() if isinstance(chat_history_id, str) and chat_history_id.strip() else None,
            draft_chat_id=draft_chat_id.strip() if isinstance(draft_chat_id, str) and draft_chat_id.strip() else None,
            model_id=model_id.strip() if isinstance(model_id, str) and model_id.strip() else None,
        )
    return RejectionPayload()


def summarize_validation_error(validation_error: RequestValidationError) -> str:
    issues: list[str] = []
    for error in validation_error.errors():
        location = ".".join(str(part) for part in error.get("loc", []) if part is not None)
        message = str(error.get("msg") or "validation error").strip()
        issues.append(f"{location}: {message}" if location else message)
    return "; ".join(issue for issue in issues if issue) or "request validation failed"

def persist_chat_proxy_rejection(
    db: Session,
    *,
    session: SessionContext | None,
    payload: ChatCompletionRequest | RejectionPayload | None,
    error: ChatProxyError,
    route: ProviderRoute | None = None,
) -> None:
    persist_chat_request_rejection(
        db,
        session=session,
        payload=payload,
        error_code=error.code,
        detail=error.detail,
        http_status=error.http_status,
        retry_after_seconds=error.retry_after_seconds,
        route=route,
    )
