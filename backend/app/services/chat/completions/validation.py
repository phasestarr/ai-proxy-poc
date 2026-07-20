from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.config.chat import LATEST_PROMPT_MAX_TOKENS
from app.config.chat_outcomes import get_error_message
from app.db.redis.chat_coordination import (
    ChatCoordinationUnavailableError,
    ChatRateLimitExceededError,
    enforce_chat_rate_limits,
)
from app.providers.dispatcher import ProviderConfigurationError, ensure_provider_ready
from app.providers.types import ProviderRoute
from app.providers.token_estimation import estimate_token_count_from_text
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.completions.route_selection import prepare_chat_completion_request
from app.services.chat.errors import ChatProxyError, build_preparation_error
from app.services.usage_caps import enforce_user_usage_cap


@dataclass(slots=True, frozen=True)
class ChatValidationResult:
    route: ProviderRoute


def run_chat_validation(
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    db: Session,
) -> ChatValidationResult:
    prompt_token_count = estimate_token_count_from_text(payload.prompt)
    if prompt_token_count > LATEST_PROMPT_MAX_TOKENS:
        raise ChatProxyError(
            code="prompt_too_large",
            origin="client",
            detail=(
                f"latest prompt contains {prompt_token_count:,} tokens; "
                f"the limit is {LATEST_PROMPT_MAX_TOKENS:,}"
            ),
            http_status=400,
        )

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

    return ChatValidationResult(
        route=route,
    )


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
