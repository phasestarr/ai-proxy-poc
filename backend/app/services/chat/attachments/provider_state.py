from __future__ import annotations

import asyncio
from uuid import uuid4

from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import StoredFile, StoredFileProviderState
from app.services.chat.attachments.remote_files import (
    best_effort_delete_remote_provider_file,
    upload_and_count_provider_file,
)


async def ensure_provider_token_states(
    *,
    stored_file: StoredFile,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> None:
    existing_states = {state.provider: state for state in stored_file.provider_states}
    provider_counts = await resolve_provider_token_counts(
        existing_states=existing_states,
        stored_file_id=stored_file.id,
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
    )
    for provider, payload in provider_counts.items():
        state = existing_states.get(provider)
        if state is None:
            state = StoredFileProviderState(
                id=str(uuid4()),
                provider=provider,
                token_count=int(payload["token_count"]),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            stored_file.provider_states.append(state)

        state.token_count = int(payload["token_count"])
        state.count_model_id = payload.get("count_model_id")
        state.provider_file_id = payload.get("provider_file_id")
        state.uploaded_at = payload.get("uploaded_at")
        state.last_used_at = payload.get("last_used_at")


async def build_provider_token_states(
    *,
    stored_file_id: str,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> list[StoredFileProviderState]:
    provider_counts = await resolve_provider_token_counts(
        existing_states={},
        stored_file_id=stored_file_id,
        display_name=display_name,
        mime_type=mime_type,
        file_bytes=file_bytes,
    )
    provider_states: list[StoredFileProviderState] = []
    for provider, payload in provider_counts.items():
        provider_states.append(
            StoredFileProviderState(
                id=str(uuid4()),
                provider=provider,
                token_count=int(payload["token_count"]),
                provider_file_id=payload.get("provider_file_id"),
                count_model_id=payload.get("count_model_id"),
                uploaded_at=payload.get("uploaded_at"),
                last_used_at=payload.get("last_used_at"),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
    return provider_states


async def resolve_provider_token_counts(
    *,
    existing_states: dict[str, StoredFileProviderState],
    stored_file_id: str,
    display_name: str,
    mime_type: str,
    file_bytes: bytes,
) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    tasks: list[tuple[str, asyncio.Task]] = []

    for provider in ("openai", "anthropic", "vertex_ai"):
        state = existing_states.get(provider)
        if state is not None and state.token_count is not None:
            results[provider] = {
                "token_count": state.token_count,
                "provider_file_id": state.provider_file_id,
                "count_model_id": state.count_model_id,
                "uploaded_at": state.uploaded_at,
                "last_used_at": state.last_used_at,
            }
            continue

        tasks.append(
            (
                provider,
                asyncio.ensure_future(
                    upload_and_count_provider_file(
                        provider=provider,
                        stored_file_id=stored_file_id,
                        display_name=display_name,
                        mime_type=mime_type,
                        file_bytes=file_bytes,
                    )
                ),
            )
        )

    if tasks:
        gathered = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        successful_uploads: list[tuple[str, str]] = []
        failures: list[tuple[str, Exception]] = []

        for (provider, _), outcome in zip(tasks, gathered, strict=False):
            if isinstance(outcome, Exception):
                failures.append((provider, outcome))
                continue
            provider_file_id, token_count, count_model_id = outcome
            successful_uploads.append((provider, provider_file_id))
            now = utc_now()
            results[provider] = {
                "token_count": int(token_count),
                "provider_file_id": provider_file_id,
                "count_model_id": count_model_id,
                "uploaded_at": now,
                "last_used_at": now,
            }

        if failures:
            for provider, provider_file_id in successful_uploads:
                await best_effort_delete_remote_provider_file(
                    provider=provider,
                    provider_file_id=provider_file_id,
                )
            failed_provider, failed_error = failures[0]
            raise RuntimeError(f"{failed_provider} attachment remote preparation failed: {failed_error}") from failed_error

    return results
