from __future__ import annotations

import logging
from dataclasses import dataclass

from app.auth.cleanup import purge_expired_auth_data
from app.db.postgres.session import SessionLocal
from app.services.chat.attachment_cleanup import (
    purge_stale_remote_attachment_files,
    reconcile_attachment_remote_files,
)

logger = logging.getLogger("uvicorn.error")


@dataclass(slots=True, frozen=True)
class HousekeepingResult:
    expired_auth_rows_deleted: int
    attachment_refs_reconciled: int
    attachment_remote_files_purged: int


async def run_housekeeping_once() -> HousekeepingResult:
    expired_auth_rows_deleted = 0
    attachment_refs_reconciled = 0
    attachment_remote_files_purged = 0

    with SessionLocal() as db:
        expired_auth_rows_deleted = purge_expired_auth_data(db)

    with SessionLocal() as db:
        attachment_refs_reconciled = await reconcile_attachment_remote_files(db)

    with SessionLocal() as db:
        attachment_remote_files_purged = await purge_stale_remote_attachment_files(db)

    result = HousekeepingResult(
        expired_auth_rows_deleted=expired_auth_rows_deleted,
        attachment_refs_reconciled=attachment_refs_reconciled,
        attachment_remote_files_purged=attachment_remote_files_purged,
    )
    logger.info(
        "Housekeeping completed.",
        extra={
            "expired_auth_rows_deleted": result.expired_auth_rows_deleted,
            "attachment_refs_reconciled": result.attachment_refs_reconciled,
            "attachment_remote_files_purged": result.attachment_remote_files_purged,
        },
    )
    return result
