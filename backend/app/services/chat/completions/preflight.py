from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.config.chat_outcomes import get_error_message
from app.db.redis.chat_drafts import ChatDraftUnavailableError, load_chat_draft, refresh_chat_draft
from app.db.redis.chat_coordination import (
    ChatCoordinationUnavailableError,
    ChatRateLimitExceededError,
    enforce_chat_rate_limits,
)
from app.providers.dispatcher import ProviderConfigurationError, ensure_provider_ready
from app.providers.types import ProviderRoute
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.completions.route_selection import prepare_chat_completion_request
from app.services.chat.errors import ChatHistoryNotFoundError, ChatProxyError, build_preparation_error
from app.services.chat.histories.service import load_user_history
from app.services.usage_caps import enforce_user_usage_cap


@dataclass(slots=True, frozen=True)
class ChatPreflightResult:
    route: ProviderRoute
    history_id: str
    draft_chat_id: str | None = None


def run_chat_preflight(
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    db: Session,
) -> ChatPreflightResult:
    try:
        prepared = prepare_chat_completion_request(payload, session=session)
    except ValueError as exc:
        raise build_preparation_error(exc) from exc

    route = prepared.route
    try:
        ensure_provider_ready(provider=route.model.provider)
    except ProviderConfigurationError as exc:
        raise ChatProxyError(
            code="provider_not_configured",
            origin="proxy",
            detail=build_safe_error_detail("provider_not_configured"),
            http_status=503,
            provider=route.model.provider,
        ) from exc

    history_id, draft_chat_id = resolve_conversation_target(
        payload=payload,
        session=session,
        db=db,
    )

    enforce_user_usage_cap(
        db,
        session=session,
        payload=payload,
        route=route,
    )

    try:
        enforce_chat_rate_limits(user_id=session.user_id)
    except ChatRateLimitExceededError as exc:
        raise map_rate_limit_error(exc) from exc
    except ChatCoordinationUnavailableError as exc:
        raise ChatProxyError(
            code="coordination_unavailable",
            origin="proxy",
            detail=build_safe_error_detail("coordination_unavailable"),
            http_status=503,
        ) from exc

    return ChatPreflightResult(
        route=route,
        history_id=history_id,
        draft_chat_id=draft_chat_id,
    )


def resolve_conversation_target(
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    db: Session,
) -> tuple[str, str | None]:
    if payload.chat_history_id:
        history = load_user_history(
            db,
            user_id=session.user_id,
            history_id=payload.chat_history_id,
        )
        if history is None:
            raise ChatHistoryNotFoundError("chat history not found")
        return history.id, None

    draft_chat_id = payload.draft_chat_id or ""
    history = load_user_history(
        db,
        user_id=session.user_id,
        history_id=draft_chat_id,
    )
    if history is not None:
        return history.id, None

    try:
        draft = load_chat_draft(draft_chat_id=draft_chat_id)
    except ChatDraftUnavailableError as exc:
        raise ChatProxyError(
            code="coordination_unavailable",
            origin="proxy",
            detail=build_safe_error_detail("coordination_unavailable"),
            http_status=503,
        ) from exc

    if draft is None or draft.user_id != session.user_id:
        raise ChatHistoryNotFoundError("chat history not found")

    try:
        refresh_chat_draft(draft_chat_id=draft_chat_id)
    except ChatDraftUnavailableError as exc:
        raise ChatProxyError(
            code="coordination_unavailable",
            origin="proxy",
            detail=build_safe_error_detail("coordination_unavailable"),
            http_status=503,
        ) from exc

    return draft_chat_id, draft_chat_id


def build_safe_error_detail(code: str) -> str:
    return get_error_message(code)


def map_rate_limit_error(exc: ChatRateLimitExceededError) -> ChatProxyError:
    code = "rate_limit_hour" if exc.window == "hour" else "rate_limit_minute"
    return ChatProxyError(
        code=code,
        origin="proxy",
        detail=build_safe_error_detail(code),
        http_status=429,
        retry_after_seconds=exc.retry_after_seconds,
    )
