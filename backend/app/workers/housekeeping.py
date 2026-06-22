from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config.time import utc_now
from app.db.postgres.session import SessionLocal
from app.workers.auth_cleanup import purge_expired_auth_data
from app.workers.chat_attachment_cleanup import (
    purge_stale_remote_attachment_files,
    reconcile_attachment_remote_files,
)
from app.workers.chat_execution_cleanup import cleanup_stale_chat_executions
from app.workers.chat_history_cleanup import delete_stale_empty_histories
from app.services.chat.attachments.storage import cleanup_due_orphan_stored_files

logger = logging.getLogger("uvicorn.error")


@dataclass(slots=True, frozen=True)
class HousekeepingResult:
    expired_auth_rows_deleted: int
    stale_chat_executions_cleaned: int
    stale_empty_histories_deleted: int
    attachment_refs_reconciled: int
    attachment_remote_files_purged: int
    attachment_blobs_cleaned: int


async def run_housekeeping_once() -> HousekeepingResult:
    now = utc_now()
    expired_auth_rows_deleted = 0
    stale_chat_executions_cleaned = 0
    stale_empty_histories_deleted = 0
    attachment_refs_reconciled = 0
    attachment_remote_files_purged = 0
    attachment_blobs_cleaned = 0

    with SessionLocal() as db:
        expired_auth_rows_deleted = purge_expired_auth_data(db, now=now)

    with SessionLocal() as db:
        stale_chat_executions_cleaned = cleanup_stale_chat_executions(db, now=now)

    with SessionLocal() as db:
        stale_empty_histories_deleted = delete_stale_empty_histories(db, now=now)

    with SessionLocal() as db:
        attachment_refs_reconciled = await reconcile_attachment_remote_files(db)

    with SessionLocal() as db:
        attachment_remote_files_purged = await purge_stale_remote_attachment_files(db, now=now)

    with SessionLocal() as db:
        attachment_blobs_cleaned = await cleanup_due_orphan_stored_files(db, now=now)

    result = HousekeepingResult(
        expired_auth_rows_deleted=expired_auth_rows_deleted,
        stale_chat_executions_cleaned=stale_chat_executions_cleaned,
        stale_empty_histories_deleted=stale_empty_histories_deleted,
        attachment_refs_reconciled=attachment_refs_reconciled,
        attachment_remote_files_purged=attachment_remote_files_purged,
        attachment_blobs_cleaned=attachment_blobs_cleaned,
    )
    logger.info(
        "Housekeeping completed.",
        extra={
            "expired_auth_rows_deleted": result.expired_auth_rows_deleted,
            "stale_chat_executions_cleaned": result.stale_chat_executions_cleaned,
            "stale_empty_histories_deleted": result.stale_empty_histories_deleted,
            "attachment_refs_reconciled": result.attachment_refs_reconciled,
            "attachment_remote_files_purged": result.attachment_remote_files_purged,
            "attachment_blobs_cleaned": result.attachment_blobs_cleaned,
        },
    )
    return result
