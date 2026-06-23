from __future__ import annotations

import secrets
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.session_lifecycle import issue_session
from app.auth.types import CreatedSession, SessionLimitStrategy
from app.config.time import utc_now
from app.db.postgres.models.identities import GuestIdentity
from app.db.postgres.models.user import User


def create_guest_session(
    db: Session,
    *,
    created_ip: str | None,
    user_agent: str | None,
    session_limit_strategy: SessionLimitStrategy | None = None,
) -> CreatedSession:
    now = utc_now()
    user = _load_guest_user_by_ip(db, ip_address=created_ip)
    if user is None:
        user = _create_guest_user(
            db,
            ip_address=created_ip,
            now=now,
        )
    else:
        user.status = "active"
        if created_ip:
            user.display_name = created_ip
        user.last_seen_at = now

    return issue_session(
        db,
        user=user,
        auth_type="guest",
        capabilities=["chat:send"],
        persistent=False,
        created_ip=created_ip,
        user_agent=user_agent,
        session_limit_strategy=session_limit_strategy,
    )


def _create_guest_user(
    db: Session,
    *,
    ip_address: str | None,
    now,
) -> User:
    savepoint = db.begin_nested()
    try:
        user = User(
            id=str(uuid4()),
            account_type="guest",
            status="active",
            display_name=ip_address or _build_guest_display_name(),
            last_seen_at=now,
        )
        db.add(user)
        db.flush()

        if ip_address:
            db.add(
                GuestIdentity(
                    id=str(uuid4()),
                    user_id=user.id,
                    provider="guest",
                    ip_address=ip_address,
                )
            )
            db.flush()
        savepoint.commit()
        return user
    except IntegrityError:
        savepoint.rollback()
        existing_user = _load_guest_user_by_ip(db, ip_address=ip_address)
        if existing_user is None:
            raise
        return existing_user


def _load_guest_user_by_ip(
    db: Session,
    *,
    ip_address: str | None,
) -> User | None:
    if not ip_address:
        return None

    guest_identity = db.execute(
        select(GuestIdentity).where(GuestIdentity.ip_address == ip_address)
    ).scalar_one_or_none()
    if guest_identity is None:
        return None
    return guest_identity.user


def _build_guest_display_name() -> str:
    return f"Guest-{secrets.token_hex(3).upper()}"
