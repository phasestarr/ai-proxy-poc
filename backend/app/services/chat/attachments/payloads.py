from __future__ import annotations

from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.session import SessionLocal
from app.providers.anthropic.attachments import inject_anthropic_history_files
from app.providers.openai.attachments import inject_openai_history_files
from app.providers.types import PreparedProviderChatRequest, ProviderRoute
from app.providers.vertex.attachments import inject_vertex_history_files
from app.services.chat.attachments.remote_files import best_effort_delete_remote_provider_file, upload_provider_files
from app.services.chat.attachments.service import list_history_files
from app.services.chat.attachments.storage import get_provider_state
from app.services.chat.errors import ChatProxyError
from app.services.chat.operations import OperationHandle, assert_operation_current


async def prepare_history_attachments_for_provider(
    *,
    user_id: str,
    history_id: str | None,
    operation: OperationHandle,
    route: ProviderRoute,
    prepared_request: PreparedProviderChatRequest,
) -> tuple[PreparedProviderChatRequest, list[dict[str, object]]]:
    with SessionLocal() as db:
        assert_operation_current(db, operation)
        if history_id:
            conversation_id = history_id
            conversation_files = list_history_files(db, user_id=user_id, history_id=history_id)
        else:
            return prepared_request, []

        active_conversation_files = [conversation_file for conversation_file in conversation_files if conversation_file.is_active]
        if not active_conversation_files:
            return prepared_request, []

        provider_token_total = 0
        upload_targets: dict[str, tuple[str, object, object]] = {}
        attachments: list[dict[str, object]] = []

        for conversation_file in active_conversation_files:
            stored_file = conversation_file.stored_file
            provider_state = get_provider_state(stored_file=stored_file, provider=route.model.provider)
            if provider_state is None or provider_state.token_count_status != "ready" or provider_state.token_count is None:
                raise ChatProxyError(
                    code="attachments_token_count_failed",
                    origin="proxy",
                    detail="attachment token metadata is unavailable",
                    http_status=503,
                    provider=route.model.provider,
                )

            provider_token_total += int(provider_state.token_count)
            attachments.append(
                {
                    "conversation_file_id": conversation_file.id,
                    "stored_file_id": stored_file.id,
                    "display_name": conversation_file.display_name,
                    "mime_type": conversation_file.mime_type,
                    "byte_size": conversation_file.byte_size,
                    "provider": route.model.provider,
                    "provider_file_id": provider_state.provider_file_id,
                    "token_count": int(provider_state.token_count),
                }
            )
            upload_targets[stored_file.id] = (conversation_file.display_name, stored_file, provider_state)

        if provider_token_total > settings.chat_attachment_max_total_tokens_per_provider:
            raise ChatProxyError(
                code="attachments_too_large",
                origin="client",
                detail="attachment token total exceeds the provider attachment limit",
                http_status=400,
                provider=route.model.provider,
            )

        previous_provider_ids = {
            stored_file_id: provider_state.provider_file_id
            for stored_file_id, (_, _, provider_state) in upload_targets.items()
        }
        uploaded_provider_ids = await upload_provider_files(
            provider=route.model.provider,
            upload_targets=upload_targets,
        )
        newly_uploaded_provider_ids = [
            provider_file_id
            for stored_file_id, provider_file_id in uploaded_provider_ids.items()
            if provider_file_id and provider_file_id != previous_provider_ids.get(stored_file_id)
        ]
        now = utc_now()
        for stored_file_id, provider_file_id in uploaded_provider_ids.items():
            _, _, provider_state = upload_targets[stored_file_id]
            provider_state.provider_file_id = provider_file_id
            provider_state.last_used_at = now

        for conversation_file in active_conversation_files:
            provider_state = get_provider_state(stored_file=conversation_file.stored_file, provider=route.model.provider)
            if provider_state is not None:
                provider_state.last_used_at = now

        try:
            assert_operation_current(db, operation)
            db.commit()
        except Exception:
            db.rollback()
            for provider_file_id in newly_uploaded_provider_ids:
                await best_effort_delete_remote_provider_file(
                    provider=route.model.provider,
                    provider_file_id=provider_file_id,
                )
            raise

        attachment_by_conversation_file_id = {
            attachment["conversation_file_id"]: attachment
            for attachment in attachments
        }
        for conversation_file in active_conversation_files:
            provider_state = get_provider_state(stored_file=conversation_file.stored_file, provider=route.model.provider)
            if provider_state is None or not provider_state.provider_file_id:
                raise ChatProxyError(
                    code="attachments_upload_failed",
                    origin="proxy",
                    detail="provider file upload did not return a reusable file id",
                    http_status=502,
                    provider=route.model.provider,
                )
            attachment = attachment_by_conversation_file_id[conversation_file.id]
            attachment["provider_file_id"] = provider_state.provider_file_id

        snapshots = [
            {
                "chat_history_file_id": attachment["conversation_file_id"],
                "stored_file_id": attachment["stored_file_id"],
                "display_name": attachment["display_name"],
                "mime_type": attachment["mime_type"],
                "byte_size": attachment["byte_size"],
                "provider": attachment["provider"],
                "provider_file_id": attachment["provider_file_id"],
                "token_count": attachment["token_count"],
            }
            for attachment in attachments
        ]

    next_payload = build_provider_attachment_payload(
        provider=route.model.provider,
        payload=prepared_request.payload,
        history_id=conversation_id,
        attachments=attachments,
    )
    return PreparedProviderChatRequest(
        provider=prepared_request.provider,
        public_model_id=prepared_request.public_model_id,
        payload=next_payload,
        estimated_input_tokens=prepared_request.estimated_input_tokens,
        input_token_count_payload=prepared_request.input_token_count_payload,
        resolved_input_tokens=prepared_request.resolved_input_tokens,
    ), snapshots


def build_provider_attachment_payload(
    *,
    provider: str,
    payload: object,
    history_id: str,
    attachments: list[dict[str, object]],
) -> object:
    if not isinstance(payload, dict):
        return payload
    if provider == "openai":
        return inject_openai_history_files(
            payload=payload,
            history_id=history_id,
            attachments=attachments,
        )
    if provider == "anthropic":
        return inject_anthropic_history_files(
            payload=payload,
            attachments=attachments,
        )
    if provider == "vertex_ai":
        return inject_vertex_history_files(
            payload=payload,
            attachments=attachments,
        )
    return payload
