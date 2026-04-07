"""
Purpose:
- Implement backend-owned authentication and session business logic.

Responsibilities:
- Issue browser sessions backed by PostgreSQL
- Resolve and refresh current session state from cookies
- Revoke expired or deleted sessions safely
- Keep provider-specific details outside the router layer
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.auth import AuthIdentity, AuthProviderSession, AuthSession, OAuthTransaction
from app.db.postgres.models.user import User
from app.services.auth_security import build_guest_display_name, generate_session_key, hash_session_key

AuthType = Literal["guest", "microsoft"]


@dataclass(slots=True)
class ProviderSessionArtifacts:
    provider: Literal["microsoft"]
    token_cache_encrypted: bytes
    access_token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None
    tenant_id: str | None = None
    home_account_id: str | None = None
    scopes: list[str] | None = None


@dataclass(slots=True)
class SessionContext:
    session_id: str
    user_id: str
    auth_type: AuthType
    display_name: str
    email: str | None
    capabilities: list[str]
    persistent: bool
    idle_expires_at: datetime
    absolute_expires_at: datetime


@dataclass(slots=True)
class CreatedSession:
    context: SessionContext
    raw_session_key: str


@dataclass(slots=True)
class SessionLookupResult:
    context: SessionContext | None
    reason: str
    should_clear_cookie: bool


def create_guest_session(
    db: Session,
    *,
    created_ip: str | None,
    user_agent: str | None,
) -> CreatedSession:
    now = utc_now()
    user = User(
        id=str(uuid4()),
        account_type="guest",
        status="active",
        display_name=build_guest_display_name(),
        last_seen_at=now,
    )
    db.add(user)
    db.flush()

    return issue_session(
        db,
        user=user,
        auth_type="guest",
        capabilities=["chat:send"],
        persistent=False,
        created_ip=created_ip,
        user_agent=user_agent,
    )


def issue_session(
    db: Session,
    *,
    user: User,
    auth_type: AuthType,
    capabilities: list[str],
    persistent: bool,
    created_ip: str | None,
    user_agent: str | None,
    provider_artifacts: ProviderSessionArtifacts | None = None,
) -> CreatedSession:
    now = utc_now()
    raw_session_key = generate_session_key()
    absolute_expires_at = now + _get_absolute_duration(auth_type)
    auth_session = AuthSession(
        id=str(uuid4()),
        session_key_hash=hash_session_key(raw_session_key),
        user=user,
        auth_type=auth_type,
        state="active",
        persistent=persistent,
        capabilities=list(capabilities),
        created_at=now,
        last_seen_at=now,
        idle_expires_at=min(now + _get_idle_duration(auth_type), absolute_expires_at),
        absolute_expires_at=absolute_expires_at,
        created_ip=created_ip,
        created_user_agent=user_agent,
        last_ip=created_ip,
        last_user_agent=user_agent,
    )
    db.add(auth_session)

    if provider_artifacts is not None:
        auth_session.provider_session = AuthProviderSession(
            session=auth_session,
            provider=provider_artifacts.provider,
            token_cache_encrypted=provider_artifacts.token_cache_encrypted,
            access_token_expires_at=provider_artifacts.access_token_expires_at,
            refresh_token_expires_at=provider_artifacts.refresh_token_expires_at,
            tenant_id=provider_artifacts.tenant_id,
            home_account_id=provider_artifacts.home_account_id,
            scope=list(provider_artifacts.scopes or []),
        )

    user.last_seen_at = now
    db.commit()

    return CreatedSession(
        context=_build_session_context(auth_session, user),
        raw_session_key=raw_session_key,
    )


def resolve_session(
    db: Session,
    *,
    raw_session_key: str | None,
    client_ip: str | None,
    user_agent: str | None,
    touch: bool = True,
) -> SessionLookupResult:
    if not raw_session_key:
        return SessionLookupResult(context=None, reason="missing_session", should_clear_cookie=False)

    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.session_key_hash == hash_session_key(raw_session_key))
    ).first()

    if row is None:
        return SessionLookupResult(context=None, reason="invalid_session", should_clear_cookie=True)

    auth_session, user = row
    now = utc_now()

    if auth_session.state != "active":
        _delete_session_row(db, auth_session)
        db.commit()
        return SessionLookupResult(
            context=None,
            reason=f"{auth_session.state}_session",
            should_clear_cookie=True,
        )

    if user.status != "active":
        _delete_session_row(db, auth_session)
        db.commit()
        return SessionLookupResult(context=None, reason="user_disabled", should_clear_cookie=True)

    if auth_session.absolute_expires_at <= now:
        _delete_session_row(db, auth_session)
        db.commit()
        return SessionLookupResult(context=None, reason="expired_session", should_clear_cookie=True)

    if auth_session.idle_expires_at <= now:
        _delete_session_row(db, auth_session)
        db.commit()
        return SessionLookupResult(context=None, reason="expired_session", should_clear_cookie=True)

    if touch:
        auth_session.last_seen_at = now
        auth_session.last_ip = client_ip
        auth_session.last_user_agent = user_agent
        auth_session.idle_expires_at = min(
            auth_session.absolute_expires_at,
            now + _get_idle_duration(auth_session.auth_type),
        )
        user.last_seen_at = now
        db.commit()

    return SessionLookupResult(
        context=_build_session_context(auth_session, user),
        reason="authenticated",
        should_clear_cookie=False,
    )


def delete_session(
    db: Session,
    *,
    raw_session_key: str | None,
) -> bool:
    if not raw_session_key:
        return False

    auth_session = db.execute(
        select(AuthSession).where(AuthSession.session_key_hash == hash_session_key(raw_session_key))
    ).scalar_one_or_none()

    if auth_session is None:
        return False

    _delete_session_row(db, auth_session)
    db.commit()
    return True


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
        _delete_session_row(db, auth_session)
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

    db.commit()
    return deleted_count


def _build_session_context(auth_session: AuthSession, user: User) -> SessionContext:
    return SessionContext(
        session_id=auth_session.id,
        user_id=user.id,
        auth_type=auth_session.auth_type,
        display_name=user.display_name,
        email=user.email,
        capabilities=list(auth_session.capabilities or []),
        persistent=auth_session.persistent,
        idle_expires_at=auth_session.idle_expires_at,
        absolute_expires_at=auth_session.absolute_expires_at,
    )


def _delete_session_row(
    db: Session,
    auth_session: AuthSession,
) -> None:
    user_id = auth_session.user_id
    db.delete(auth_session)
    db.flush()
    _delete_orphan_guest_user(db, user_id=user_id)


def _delete_orphan_guest_user(
    db: Session,
    *,
    user_id: str,
) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or user.account_type != "guest":
        return

    has_sessions = db.execute(
        select(AuthSession.id).where(AuthSession.user_id == user_id).limit(1)
    ).first()
    has_identities = db.execute(
        select(AuthIdentity.id).where(AuthIdentity.user_id == user_id).limit(1)
    ).first()

    if has_sessions is None and has_identities is None:
        db.delete(user)


def _get_idle_duration(auth_type: AuthType | str) -> timedelta:
    if auth_type == "microsoft":
        return timedelta(minutes=settings.auth_microsoft_idle_minutes)
    return timedelta(minutes=settings.auth_guest_idle_minutes)


def _get_absolute_duration(auth_type: AuthType | str) -> timedelta:
    if auth_type == "microsoft":
        return timedelta(days=settings.auth_microsoft_absolute_days)
    return timedelta(hours=settings.auth_guest_absolute_hours)
