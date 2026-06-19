from __future__ import annotations

from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.session import SessionLocal
from app.providers.anthropic.attachments import inject_anthropic_history_files
from app.providers.openai.attachments import inject_openai_history_files
from app.providers.types import PreparedProviderChatRequest, ProviderRoute
from app.providers.vertex.attachments import inject_vertex_history_files
from app.services.chat.attachments.remote_files import upload_provider_files
from app.services.chat.attachments.service import list_history_files
from app.services.chat.attachments.storage import get_provider_state
from app.services.chat.errors import ChatProxyError


async def prepare_history_attachments_for_provider(
    *,
    user_id: str,
    history_id: str,
    route: ProviderRoute,
    prepared_request: PreparedProviderChatRequest,
) -> tuple[PreparedProviderChatRequest, list[dict[str, object]]]:
    with SessionLocal() as db:
        history_files = list_history_files(db, user_id=user_id, history_id=history_id)
        active_history_files = [history_file for history_file in history_files if history_file.is_active]
        if not active_history_files:
            return prepared_request, []

        provider_token_total = 0
        upload_targets: dict[str, tuple[str, object, object]] = {}
        attachments: list[dict[str, object]] = []

        for history_file in active_history_files:
            stored_file = history_file.stored_file
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
                    "history_file_id": history_file.id,
                    "stored_file_id": stored_file.id,
                    "display_name": history_file.display_name,
                    "mime_type": history_file.mime_type,
                    "byte_size": history_file.byte_size,
                    "provider": route.model.provider,
                    "provider_file_id": provider_state.provider_file_id,
                    "token_count": int(provider_state.token_count),
                }
            )
            upload_targets[stored_file.id] = (history_file.display_name, stored_file, provider_state)

        if provider_token_total > settings.chat_attachment_max_total_tokens_per_provider:
            raise ChatProxyError(
                code="attachments_too_large",
                origin="client",
                detail="attachment token total exceeds the provider attachment limit",
                http_status=400,
                provider=route.model.provider,
            )

        uploaded_provider_ids = await upload_provider_files(
            provider=route.model.provider,
            upload_targets=upload_targets,
        )
        now = utc_now()
        for stored_file_id, provider_file_id in uploaded_provider_ids.items():
            _, _, provider_state = upload_targets[stored_file_id]
            provider_state.provider_file_id = provider_file_id
            provider_state.last_used_at = now

        for history_file in active_history_files:
            provider_state = get_provider_state(stored_file=history_file.stored_file, provider=route.model.provider)
            if provider_state is not None:
                provider_state.last_used_at = now

        db.commit()

        attachment_by_history_file_id = {
            attachment["history_file_id"]: attachment
            for attachment in attachments
        }
        for history_file in active_history_files:
            provider_state = get_provider_state(stored_file=history_file.stored_file, provider=route.model.provider)
            if provider_state is None or not provider_state.provider_file_id:
                raise ChatProxyError(
                    code="attachments_upload_failed",
                    origin="proxy",
                    detail="provider file upload did not return a reusable file id",
                    http_status=502,
                    provider=route.model.provider,
                )
            attachment = attachment_by_history_file_id[history_file.id]
            attachment["provider_file_id"] = provider_state.provider_file_id

        snapshots = [
            {
                "chat_history_file_id": attachment["history_file_id"],
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
        history_id=history_id,
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
