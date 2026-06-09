from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.session_lifecycle import delete_session_row, expire_session, is_session_expired
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
    mark_expired_sessions(db, now=current_time)
    deleted_count = 0
    deleted_count += delete_expired_sessions(db)
    deleted_count += delete_expired_oauth_transactions(db, now=current_time)
    deleted_count += delete_expired_conflict_tickets(db, now=current_time)
    db.commit()
    return deleted_count


def mark_expired_sessions(
    db: Session,
    *,
    now: datetime,
) -> int:
    expired_count = 0
    active_sessions = db.execute(
        select(AuthSession).where(AuthSession.state == "active")
    ).scalars().all()
    for auth_session in active_sessions:
        if not is_session_expired(auth_session, now=now):
            continue
        expire_session(
            auth_session,
            now=now,
            reason_code="idle_timeout",
            reason="Session expired after 6 hours of inactivity.",
        )
        expired_count += 1
    return expired_count


def delete_expired_sessions(db: Session) -> int:
    deleted_count = 0
    expired_sessions = db.execute(
        select(AuthSession).where(AuthSession.state == "expired")
    ).scalars().all()
    for auth_session in expired_sessions:
        delete_session_row(db, auth_session)
        deleted_count += 1
    return deleted_count


def delete_expired_oauth_transactions(
    db: Session,
    *,
    now: datetime,
) -> int:
    deleted_count = 0
    expired_transactions = db.execute(
        select(OAuthTransaction).where(
            or_(
                OAuthTransaction.expires_at <= now,
                OAuthTransaction.consumed_at.is_not(None),
            )
        )
    ).scalars().all()
    for transaction in expired_transactions:
        db.delete(transaction)
        deleted_count += 1
    return deleted_count


def delete_expired_conflict_tickets(
    db: Session,
    *,
    now: datetime,
) -> int:
    deleted_count = 0
    expired_conflict_tickets = db.execute(
        select(AuthConflictTicket).where(
            or_(
                AuthConflictTicket.expires_at <= now,
                AuthConflictTicket.consumed_at.is_not(None),
            )
        )
    ).scalars().all()
    for conflict_ticket in expired_conflict_tickets:
        db.delete(conflict_ticket)
        deleted_count += 1
    return deleted_count
