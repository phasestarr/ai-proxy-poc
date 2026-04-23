from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.session_lifecycle import delete_session_row
from app.config.time import utc_now
from app.db.postgres.models.auth_conflicts import AuthConflictTicket
from app.db.postgres.models.auth_sessions import AuthSession
from app.db.postgres.models.oauth_transactions import OAuthTransaction


def purge_expired_auth_data(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    current_time = now or utc_now()
    expired_sessions = db.execute(
        select(AuthSession).where(
            or_(
                AuthSession.absolute_expires_at <= current_time,
                AuthSession.idle_expires_at <= current_time,
            )
        )
    ).scalars().all()

    deleted_count = 0
    for auth_session in expired_sessions:
        delete_session_row(db, auth_session)
        deleted_count += 1

    revoked_sessions = db.execute(
        select(AuthSession).where(AuthSession.state != "active")
    ).scalars().all()
    for auth_session in revoked_sessions:
        if auth_session in expired_sessions:
            continue
        delete_session_row(db, auth_session)
        deleted_count += 1

    expired_transactions = db.execute(
        select(OAuthTransaction).where(
            or_(
                OAuthTransaction.expires_at <= current_time,
                OAuthTransaction.consumed_at.is_not(None),
            )
        )
    ).scalars().all()
    for transaction in expired_transactions:
        db.delete(transaction)
        deleted_count += 1

    expired_conflict_tickets = db.execute(
        select(AuthConflictTicket).where(
            or_(
                AuthConflictTicket.expires_at <= current_time,
                AuthConflictTicket.consumed_at.is_not(None),
            )
        )
    ).scalars().all()
    for conflict_ticket in expired_conflict_tickets:
        db.delete(conflict_ticket)
        deleted_count += 1

    db.commit()
    return deleted_count

