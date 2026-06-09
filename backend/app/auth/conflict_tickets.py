from __future__ import annotations

from datetime import timedelta
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.encryption import decrypt_auth_payload, encrypt_auth_payload
from app.auth.guest_sessions import create_guest_session
from app.auth.keys import generate_conflict_ticket_key, hash_conflict_ticket_key
from app.auth.session_lifecycle import issue_session, load_session_by_raw_key
from app.auth.session_policy import get_session_limit
from app.auth.types import (
    AuthType,
    CreatedSession,
    CreatedSessionConflictTicket,
    SessionConflictResolutionError,
    SessionConflictTicketLookupResult,
)
from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.auth_conflicts import AuthConflictTicket
from app.db.postgres.models.user import User


def create_session_conflict_ticket(
    db: Session,
    *,
    user: User,
    auth_type: AuthType,
    capabilities: list[str],
    persistent: bool,
    return_to: str,
    requester_ip: str | None,
    requester_user_agent: str | None,
) -> CreatedSessionConflictTicket:
    now = utc_now()
    raw_ticket = generate_conflict_ticket_key()
    expires_at = now + timedelta(minutes=max(1, settings.auth_conflict_ticket_minutes))
    payload = {
        "capabilities": list(capabilities),
        "persistent": persistent,
    }

    db.add(
        AuthConflictTicket(
            id=str(uuid4()),
            ticket_hash=hash_conflict_ticket_key(raw_ticket),
            user=user,
            auth_type=auth_type,
            reason="session_limit_reached",
            payload_encrypted=encrypt_auth_payload(json.dumps(payload).encode("utf-8")),
            return_to=return_to,
            created_at=now,
            expires_at=expires_at,
            requester_ip=requester_ip,
            requester_user_agent=requester_user_agent,
        )
    )
    db.commit()

    return CreatedSessionConflictTicket(
        raw_ticket=raw_ticket,
        expires_at=expires_at,
        return_to=return_to,
        auth_type=auth_type,
        session_limit=get_session_limit(auth_type),
    )


def inspect_session_conflict_ticket(
    db: Session,
    *,
    raw_conflict_ticket: str | None,
) -> SessionConflictTicketLookupResult:
    if not raw_conflict_ticket:
        return SessionConflictTicketLookupResult(
            has_conflict=False,
            should_clear_cookie=False,
            reason="missing_conflict_ticket",
        )

    ticket = load_conflict_ticket_by_raw_key(db, raw_conflict_ticket)
    if ticket is None:
        return SessionConflictTicketLookupResult(
            has_conflict=False,
            should_clear_cookie=True,
            reason="invalid_conflict_ticket",
        )

    now = utc_now()
    if ticket.consumed_at is not None:
        return SessionConflictTicketLookupResult(
            has_conflict=False,
            should_clear_cookie=True,
            reason="consumed_conflict_ticket",
        )

    if ticket.expires_at <= now:
        db.delete(ticket)
        db.commit()
        return SessionConflictTicketLookupResult(
            has_conflict=False,
            should_clear_cookie=True,
            reason="expired_conflict_ticket",
        )

    if ticket.user.status != "active":
        return SessionConflictTicketLookupResult(
            has_conflict=False,
            should_clear_cookie=True,
            reason="user_disabled",
        )

    return SessionConflictTicketLookupResult(
        has_conflict=True,
        should_clear_cookie=False,
        reason=ticket.reason,
        detail=(
            f"{ticket.auth_type} session limit reached "
            f"({get_session_limit(ticket.auth_type)})."
        ),
        auth_type=ticket.auth_type,
        session_limit=get_session_limit(ticket.auth_type),
    )


def resolve_session_conflict(
    db: Session,
    *,
    raw_session_key: str | None,
    raw_conflict_ticket: str | None,
    requested_auth_type: AuthType | None,
    client_ip: str | None,
    user_agent: str | None,
) -> CreatedSession:
    conflict_ticket = load_valid_conflict_ticket(db, raw_conflict_ticket)
    if conflict_ticket is not None:
        return _resolve_conflict_ticket(
            db,
            conflict_ticket=conflict_ticket,
            client_ip=client_ip,
            user_agent=user_agent,
        )

    session_row = load_session_by_raw_key(db, raw_session_key) if raw_session_key else None
    if session_row is not None:
        user = session_row.user
        if user.status != "active":
            raise SessionConflictResolutionError(
                reason="user_disabled",
                detail="This user is disabled.",
                auth_type=session_row.auth_type,
            )

        created_session = issue_session(
            db,
            user=user,
            auth_type=session_row.auth_type,
            capabilities=list(session_row.capabilities or []),
            persistent=session_row.persistent,
            created_ip=client_ip,
            user_agent=user_agent,
            session_limit_strategy="evict_oldest",
        )

        db.delete(session_row)
        db.commit()
        return created_session

    if requested_auth_type == "guest":
        return create_guest_session(
            db,
            created_ip=client_ip,
            user_agent=user_agent,
            session_limit_strategy="evict_oldest",
        )

    raise SessionConflictResolutionError(
        reason="missing_session",
        detail="This session can no longer be recovered. Sign in again.",
        auth_type=requested_auth_type,
    )


def load_conflict_ticket_by_raw_key(
    db: Session,
    raw_conflict_ticket: str | None,
) -> AuthConflictTicket | None:
    if not raw_conflict_ticket:
        return None

    return db.execute(
        select(AuthConflictTicket).where(
            AuthConflictTicket.ticket_hash == hash_conflict_ticket_key(raw_conflict_ticket)
        )
    ).scalar_one_or_none()


def load_valid_conflict_ticket(
    db: Session,
    raw_conflict_ticket: str | None,
) -> AuthConflictTicket | None:
    ticket = load_conflict_ticket_by_raw_key(db, raw_conflict_ticket)
    if ticket is None:
        return None

    if ticket.consumed_at is not None:
        return None

    if ticket.expires_at <= utc_now():
        db.delete(ticket)
        db.commit()
        return None

    return ticket


def _resolve_conflict_ticket(
    db: Session,
    *,
    conflict_ticket: AuthConflictTicket,
    client_ip: str | None,
    user_agent: str | None,
) -> CreatedSession:
    user = conflict_ticket.user
    if user.status != "active":
        raise SessionConflictResolutionError(
            reason="user_disabled",
            detail="This user is disabled.",
            auth_type=conflict_ticket.auth_type,
        )

    payload = _decode_conflict_ticket_payload(conflict_ticket.payload_encrypted)
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
        raise SessionConflictResolutionError(
            reason="invalid_conflict_ticket",
            detail="This session conflict can no longer be recovered. Sign in again.",
            auth_type=conflict_ticket.auth_type,
        )

    persistent = payload.get("persistent")
    if not isinstance(persistent, bool):
        persistent = False

    conflict_ticket.consumed_at = utc_now()
    return issue_session(
        db,
        user=user,
        auth_type=conflict_ticket.auth_type,
        capabilities=list(capabilities),
        persistent=persistent,
        created_ip=client_ip,
        user_agent=user_agent,
        session_limit_strategy="evict_oldest",
    )


def _decode_conflict_ticket_payload(payload_encrypted: bytes) -> dict:
    try:
        decoded = decrypt_auth_payload(payload_encrypted).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, TypeError) as exc:
        raise SessionConflictResolutionError(
            reason="invalid_conflict_ticket",
            detail="This session conflict can no longer be recovered. Sign in again.",
        ) from exc

    if not isinstance(payload, dict):
        raise SessionConflictResolutionError(
            reason="invalid_conflict_ticket",
            detail="This session conflict can no longer be recovered. Sign in again.",
        )
    return payload

