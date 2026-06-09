from __future__ import annotations

import asyncio
import logging

from app.db.postgres.models.chat_attachment import StoredFile, StoredFileProviderState
from app.providers.anthropic.attachments import (
    anthropic_file_exists,
    count_anthropic_file_tokens,
    delete_anthropic_file,
    upload_anthropic_file,
)
from app.providers.openai.attachments import (
    count_openai_file_reference_tokens,
    delete_openai_file,
    openai_file_exists,
    upload_openai_file,
)
from app.providers.vertex.attachments import (
    count_vertex_file_tokens,
    delete_vertex_file,
    upload_vertex_file,
    vertex_file_exists,
)
from app.services.chat.errors import ChatProxyError

logger = logging.getLogger("uvicorn.error")


async def upload_and_count_provider_file(
    *,
    provider: str,
    stored_file_id: str,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> tuple[str, int, str]:
    provider_file_id = await upload_provider_file(
        provider=provider,
        stored_file_id=stored_file_id,
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
    )
    try:
        token_count, count_model_id = await count_provider_file_tokens(
            provider=provider,
            display_name=display_name,
            mime_type=mime_type,
            file_bytes=file_bytes,
            provider_file_id=provider_file_id,
        )
    except Exception:
        await best_effort_delete_remote_provider_file(
            provider=provider,
            provider_file_id=provider_file_id,
        )
        raise
    return provider_file_id, token_count, count_model_id


async def count_provider_file_tokens(
    *,
    provider: str,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
    provider_file_id: str,
) -> tuple[int, str]:
    if provider == "openai":
        return await count_openai_file_reference_tokens(
            mime_type=mime_type,
            provider_file_id=provider_file_id,
        )
    if provider == "anthropic":
        return await count_anthropic_file_tokens(
            display_name=display_name,
            mime_type=mime_type,
            file_bytes=file_bytes,
        )
    if provider == "vertex_ai":
        return await count_vertex_file_tokens(
            file_uri=provider_file_id,
            mime_type=mime_type,
        )
    raise RuntimeError(f"unsupported attachment provider: {provider}")


async def upload_provider_files(
    *,
    provider: str,
    upload_targets: dict[str, tuple[str, StoredFile, StoredFileProviderState]],
) -> dict[str, str]:
    uploaded_ids: dict[str, str] = {}
    for stored_file_id, (display_name, stored_file, provider_state) in upload_targets.items():
        try:
            provider_file_id = await upload_provider_file(
                provider=provider,
                stored_file_id=stored_file_id,
                display_name=display_name,
                mime_type=stored_file.mime_type,
                file_bytes=stored_file.content,
            )
        except Exception as exc:
            provider_state.remote_file_status = "failed"
            provider_state.remote_file_error = str(exc)
            raise ChatProxyError(
                code="attachments_upload_failed",
                origin="proxy",
                detail=f"{provider} file upload failed",
                http_status=502,
                provider=provider,
            ) from exc
        uploaded_ids[stored_file_id] = provider_file_id
    return uploaded_ids


async def upload_provider_file(
    *,
    provider: str,
    stored_file_id: str,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> str:
    if provider == "openai":
        return await upload_openai_file(
            display_name=display_name,
            mime_type=mime_type,
            file_bytes=file_bytes,
        )
    if provider == "anthropic":
        return await upload_anthropic_file(
            display_name=display_name,
            mime_type=mime_type,
            file_bytes=file_bytes,
        )
    if provider == "vertex_ai":
        return await upload_vertex_file(
            stored_file_id=stored_file_id,
            display_name=display_name,
            mime_type=mime_type,
            file_bytes=file_bytes,
        )
    raise RuntimeError(f"unsupported attachment provider: {provider}")


async def best_effort_delete_provider_files(*, stored_file: StoredFile) -> None:
    for provider_state in stored_file.provider_states:
        if not provider_state.provider_file_id or provider_state.remote_file_status != "ready":
            continue
        try:
            await delete_remote_provider_file(
                provider=provider_state.provider,
                provider_file_id=provider_state.provider_file_id,
            )
        except Exception:
            logger.exception(
                "Attachment provider file cleanup failed.",
                extra={
                    "provider": provider_state.provider,
                    "provider_file_id": provider_state.provider_file_id,
                    "stored_file_id": stored_file.id,
                },
            )


async def delete_provider_files_for_stored_file(*, stored_file: StoredFile) -> bool:
    delete_targets = [
        provider_state
        for provider_state in stored_file.provider_states
        if provider_state.provider_file_id and provider_state.remote_file_status == "ready"
    ]
    if not delete_targets:
        return True

    outcomes = await asyncio.gather(
        *(
            delete_remote_provider_file(
                provider=provider_state.provider,
                provider_file_id=str(provider_state.provider_file_id),
            )
            for provider_state in delete_targets
        ),
        return_exceptions=True,
    )
    delete_succeeded = True
    for provider_state, outcome in zip(delete_targets, outcomes, strict=False):
        if not isinstance(outcome, Exception):
            provider_state.provider_file_id = None
            provider_state.remote_file_status = "not_uploaded"
            provider_state.remote_file_error = None
            provider_state.uploaded_at = None
            provider_state.last_used_at = None
            continue
        delete_succeeded = False
        logger.error(
            "Attachment provider file cleanup failed; keeping stored file.",
            exc_info=(type(outcome), outcome, outcome.__traceback__),
            extra={
                "provider": provider_state.provider,
                "provider_file_id": provider_state.provider_file_id,
                "stored_file_id": stored_file.id,
            },
        )
    return delete_succeeded


async def best_effort_delete_remote_provider_file(*, provider: str, provider_file_id: str) -> None:
    try:
        await delete_remote_provider_file(
            provider=provider,
            provider_file_id=provider_file_id,
        )
    except Exception:
        logger.exception(
            "Attachment provider file cleanup failed.",
            extra={
                "provider": provider,
                "provider_file_id": provider_file_id,
            },
        )


async def delete_remote_provider_file(*, provider: str, provider_file_id: str) -> None:
    if provider == "openai":
        await delete_openai_file(provider_file_id=provider_file_id)
        return
    if provider == "anthropic":
        await delete_anthropic_file(provider_file_id=provider_file_id)
        return
    if provider == "vertex_ai":
        await delete_vertex_file(file_uri=provider_file_id)
        return
    raise RuntimeError(f"unsupported attachment provider: {provider}")


async def remote_provider_file_exists(*, provider: str, provider_file_id: str) -> bool:
    if provider == "openai":
        return await openai_file_exists(provider_file_id=provider_file_id)
    if provider == "anthropic":
        return await anthropic_file_exists(provider_file_id=provider_file_id)
    if provider == "vertex_ai":
        return await vertex_file_exists(file_uri=provider_file_id)
    raise RuntimeError(f"unsupported attachment provider: {provider}")
