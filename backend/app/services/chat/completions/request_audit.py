from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.config.time import utc_now
from app.db.postgres.models.operator_event import OperatorEvent
from app.providers.types import ProviderRoute
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.errors import ChatProxyError

REQUEST_VALIDATION_ERROR_CODE = "request_validation_failed"


@dataclass(slots=True, frozen=True)
class RejectionPayload:
    chat_history_id: str | None = None
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
    event_type = "usage_cap_exceeded" if error_code == "usage_cap_exceeded" else "chat_request_rejected"
    persist_operator_event(
        db,
        event_type=event_type,
        severity="error" if http_status is not None and http_status >= 500 else "warning",
        session=session,
        chat_history_id=normalized_payload.chat_history_id,
        model_id=route.model.public_id if route else normalized_payload.model_id,
        provider=route.model.provider if route else None,
        operation="chat_completion",
        result_code=error_code,
        http_status=http_status,
        retry_after_seconds=retry_after_seconds,
        message=error_code,
        detail=detail,
    )


def persist_operator_event(
    db: Session,
    *,
    event_type: str,
    severity: str = "info",
    session: SessionContext | None = None,
    user_id: str | None = None,
    auth_session_id: str | None = None,
    chat_history_id: str | None = None,
    chat_message_id: str | None = None,
    stored_file_id: str | None = None,
    model_id: str | None = None,
    provider: str | None = None,
    operation: str | None = None,
    result_code: str | None = None,
    http_status: int | None = None,
    retry_after_seconds: int | None = None,
    message: str | None = None,
    detail: str | None = None,
    metadata: dict[str, object] | None = None,
    commit: bool = True,
) -> OperatorEvent:
    event = OperatorEvent(
        id=str(uuid4()),
        event_type=event_type,
        severity=severity,
        user_id=session.user_id if session else user_id,
        auth_session_id=session.session_id if session else auth_session_id,
        chat_history_id=chat_history_id,
        chat_message_id=chat_message_id,
        stored_file_id=stored_file_id,
        model_id=model_id,
        provider=provider,
        operation=operation,
        result_code=result_code,
        http_status=http_status,
        retry_after_seconds=retry_after_seconds,
        message=message,
        detail=detail,
        event_metadata=metadata,
        created_at=utc_now(),
    )
    db.add(event)
    if commit:
        db.commit()
    return event


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
            model_id=payload.model_id,
        )
    if isinstance(payload, RejectionPayload):
        return payload
    if isinstance(payload, dict):
        chat_history_id = payload.get("chat_history_id")
        model_id = payload.get("model_id")
        return RejectionPayload(
            chat_history_id=chat_history_id.strip() if isinstance(chat_history_id, str) and chat_history_id.strip() else None,
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
