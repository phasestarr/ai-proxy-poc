from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.auth.session_lifecycle import delete_session_row, expire_session, is_session_expired
from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.auth_conflicts import AuthConflictTicket
from app.db.postgres.models.auth_sessions import AuthSession
from app.db.postgres.models.chat_attachment import ChatHistoryFile
from app.db.postgres.models.chat_history import ChatHistory, ChatMessage
from app.db.postgres.models.oauth_transactions import OAuthTransaction


def purge_expired_auth_data(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    current_time = now or utc_now()
    deleted_count = 0
    active_sessions = db.execute(
        select(AuthSession).where(AuthSession.state == "active")
    ).scalars().all()
    for auth_session in active_sessions:
        if not is_session_expired(auth_session, now=current_time):
            continue
        expire_session(
            auth_session,
            now=current_time,
            reason_code="idle_timeout",
            reason="Session expired after 6 hours of inactivity.",
        )

    expired_sessions = db.execute(
        select(AuthSession).where(AuthSession.state == "expired")
    ).scalars().all()
    for auth_session in expired_sessions:
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

    stale_empty_history_cutoff = current_time - timedelta(
        minutes=max(5, settings.auth_cleanup_interval_minutes)
    )
    stale_empty_histories = db.execute(
        select(ChatHistory).where(
            ChatHistory.last_message_at.is_(None),
            ChatHistory.created_at <= stale_empty_history_cutoff,
            ~exists(
                select(ChatMessage.id).where(ChatMessage.chat_history_id == ChatHistory.id)
            ),
            ~exists(
                select(ChatHistoryFile.id).where(ChatHistoryFile.chat_history_id == ChatHistory.id)
            ),
        )
    ).scalars().all()
    for history in stale_empty_histories:
        db.delete(history)
        deleted_count += 1

    db.commit()
    return deleted_count
