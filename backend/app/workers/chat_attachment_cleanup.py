from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.chat_attachment import StoredFileProviderState
from app.services.chat.attachments.remote_files import delete_remote_provider_file, remote_provider_file_exists

logger = logging.getLogger("uvicorn.error")


async def reconcile_attachment_remote_files(db: Session) -> int:
    states = db.execute(
        select(StoredFileProviderState)
        .where(
            StoredFileProviderState.provider_file_id.is_not(None),
            StoredFileProviderState.remote_file_status == "ready",
        )
        .order_by(StoredFileProviderState.updated_at.asc(), StoredFileProviderState.id.asc())
    ).scalars().all()

    reconciled_count = 0
    for state in states:
        provider_file_id = state.provider_file_id
        if not provider_file_id:
            continue

        try:
            remote_exists = await remote_provider_file_exists(
                provider=state.provider,
                provider_file_id=provider_file_id,
            )
        except Exception:
            logger.exception(
                "Attachment remote file existence check failed.",
                extra={
                    "provider": state.provider,
                    "provider_file_id": provider_file_id,
                    "stored_file_id": state.stored_file_id,
                },
            )
            continue

        if remote_exists:
            continue

        mark_provider_state_not_uploaded(state)
        reconciled_count += 1

    db.commit()
    return reconciled_count


async def purge_stale_remote_attachment_files(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    current_time = now or utc_now()
    cutoff = current_time - timedelta(hours=max(1, settings.chat_attachment_remote_ttl_hours))
    states = db.execute(
        select(StoredFileProviderState)
        .where(
            StoredFileProviderState.provider_file_id.is_not(None),
            StoredFileProviderState.remote_file_status == "ready",
            StoredFileProviderState.last_used_at.is_not(None),
            StoredFileProviderState.last_used_at < cutoff,
        )
        .order_by(StoredFileProviderState.last_used_at.asc(), StoredFileProviderState.id.asc())
    ).scalars().all()

    purged_count = 0
    for state in states:
        provider_file_id = state.provider_file_id
        if not provider_file_id:
            continue

        try:
            await delete_remote_provider_file(
                provider=state.provider,
                provider_file_id=provider_file_id,
            )
        except Exception:
            logger.exception(
                "Stale attachment remote file cleanup failed.",
                extra={
                    "provider": state.provider,
                    "provider_file_id": provider_file_id,
                    "stored_file_id": state.stored_file_id,
                },
            )
            continue

        mark_provider_state_not_uploaded(state)
        purged_count += 1

    db.commit()
    return purged_count


def mark_provider_state_not_uploaded(state: StoredFileProviderState) -> None:
    state.provider_file_id = None
    state.remote_file_status = "not_uploaded"
    state.remote_file_error = None
    state.uploaded_at = None
    state.last_used_at = None
