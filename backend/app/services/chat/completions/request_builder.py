from __future__ import annotations

from dataclasses import replace

from app.auth.types import SessionContext
from app.compression import (
    COMPRESSION_MODEL_ID,
    COMPRESSION_PROVIDER_ID,
    ContextCompressionError,
    compress_chat_history_context,
)
from app.db.postgres.models.chat_history import ChatHistory
from app.db.postgres.session import SessionLocal
from app.providers.dispatcher import (
    ProviderConfigurationError,
    count_provider_chat_input_tokens,
    prepare_provider_chat_completion,
)
from app.providers.types import PreparedProviderChatRequest, ProviderRoute
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.completions.context.budget import should_resolve_exact_input_tokens
from app.services.chat.completions.context.checkpoints import persist_chat_context_checkpoint_ready
from app.services.chat.completions.context.pipeline import (
    BuiltChatContext,
    build_chat_context,
    build_compaction_source_text,
)
from app.services.chat.completions.validation import build_safe_error_detail
from app.services.chat.errors import ChatProxyError
from app.services.chat.histories.service import load_user_history
from app.services.chat.operations import OperationHandle, assert_operation_current
from app.services.usage_ledger import append_chat_usage_ledger_event, serialize_provider_usage


async def build_prepared_request(
    *,
    payload: ChatCompletionRequest,
    session: SessionContext,
    route: ProviderRoute,
    history_id: str | None,
) -> tuple[BuiltChatContext, PreparedProviderChatRequest]:
    latest_user_message = payload.messages[-1]
    with SessionLocal() as pipeline_db:
        history = load_user_history(
            pipeline_db,
            user_id=session.user_id,
            history_id=history_id,
        )
        if history_id and history is None:
            raise ChatProxyError(
                code="chat_failed",
                origin="proxy",
                detail="chat history not found",
                http_status=404,
            )
        built_context = build_chat_context(
            pipeline_db,
            history=history,
            latest_user_content=latest_user_message.content,
        )
        try:
            prepared_request = prepare_provider_chat_completion(
                route=route,
                messages=built_context.provider_messages,
            )
        except ProviderConfigurationError as exc:
            raise ChatProxyError(
                code="provider_not_configured",
                origin="proxy",
                detail=build_safe_error_detail("provider_not_configured"),
                http_status=503,
                provider=route.model.provider,
            ) from exc
        except ValueError as exc:
            raise map_provider_request_validation_error(route=route, exc=exc) from exc
        except Exception as exc:
            raise map_provider_request_validation_error(route=route, exc=exc) from exc
        prepared_request = await _resolve_prepared_request_input_tokens(prepared_request)
        return built_context, prepared_request


async def run_context_compaction(
    *,
    history: ChatHistory,
    user_id: str,
    auth_session_id: str | None,
    operation: OperationHandle,
) -> None:
    with SessionLocal() as compression_db:
        source_text, covered_through_sequence = build_compaction_source_text(
            compression_db,
            history_id=history.id,
        )

    if not source_text or covered_through_sequence is None:
        raise ChatProxyError(
            code="context_compaction_failed",
            origin="proxy",
            detail=build_safe_error_detail("context_compaction_failed"),
            http_status=500,
        )

    try:
        result = await compress_chat_history_context(source_text=source_text)
    except ContextCompressionError as exc:
        raise ChatProxyError(
            code="context_compaction_failed",
            origin="proxy",
            detail=build_safe_error_detail("context_compaction_failed"),
            http_status=500,
        ) from exc

    with SessionLocal() as compression_db:
        assert_operation_current(compression_db, operation)
        persist_chat_context_checkpoint_ready(
            compression_db,
            user_id=user_id,
            history_id=history.id,
            summary_text=result.summary_text,
            covered_through_sequence=covered_through_sequence,
            model_id=COMPRESSION_MODEL_ID,
            provider=COMPRESSION_PROVIDER_ID,
            commit=False,
        )
        append_chat_usage_ledger_event(
            compression_db,
            user_id=user_id,
            auth_session_id=auth_session_id,
            chat_history_id=history.id,
            chat_message_id=None,
            provider=COMPRESSION_PROVIDER_ID,
            model_id=COMPRESSION_MODEL_ID,
            tool_ids=[],
            result_code="context_compaction_succeeded",
            usage_payload=serialize_provider_usage(result.usage),
            operation="context_compression",
        )
        compression_db.commit()


def map_provider_request_validation_error(
    *,
    route: ProviderRoute,
    exc: Exception,
) -> ChatProxyError:
    detail = str(exc)
    if looks_like_proxy_provider_config_error(detail):
        return ChatProxyError(
            code="provider_not_configured",
            origin="proxy",
            detail=build_safe_error_detail("provider_not_configured"),
            http_status=503,
            provider=route.model.provider,
        )
    return ChatProxyError(
        code="chat_failed",
        origin="proxy",
        detail=build_safe_error_detail("chat_failed"),
        http_status=500,
        provider=route.model.provider,
    )


def looks_like_proxy_provider_config_error(detail: str) -> bool:
    return any(
        marker in detail
        for marker in (
            "tool is selected but no",
            "cannot use allowed and blocked",
            "must not be blank",
            "must be at least",
            "could not be constructed",
        )
    )


async def _resolve_prepared_request_input_tokens(
    prepared_request: PreparedProviderChatRequest,
) -> PreparedProviderChatRequest:
    if not should_resolve_exact_input_tokens(prepared_request):
        return prepared_request

    resolved_input_tokens = await count_provider_chat_input_tokens(
        prepared_request=prepared_request,
    )
    if resolved_input_tokens is None:
        return prepared_request

    return replace(
        prepared_request,
        resolved_input_tokens=resolved_input_tokens,
    )
