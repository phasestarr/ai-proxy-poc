from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.keys import generate_session_key, hash_session_key
from app.auth.session_policy import get_absolute_duration, get_idle_duration, get_session_limit
from app.auth.types import (
    AuthType,
    CreatedSession,
    ProviderSessionArtifacts,
    SessionContext,
    SessionLimitExceededError,
    SessionLimitStrategy,
    SessionLookupResult,
)
from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.auth_sessions import AuthProviderSession, AuthSession
from app.db.postgres.models.identities import GuestIdentity, MicrosoftIdentity
from app.db.postgres.models.user import User


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
    session_limit_strategy: SessionLimitStrategy | None = None,
) -> CreatedSession:
    now = utc_now()
    raw_session_key = generate_session_key()
    absolute_expires_at = now + get_absolute_duration(auth_type)
    auth_session_id = str(uuid4())
    revoked_sessions = _enforce_session_limit(
        db,
        user=user,
        auth_type=auth_type,
        replacement_session_id=auth_session_id,
        now=now,
        strategy=session_limit_strategy,
    )
    auth_session = AuthSession(
        id=auth_session_id,
        session_key_hash=hash_session_key(raw_session_key),
        user=user,
        auth_type=auth_type,
        state="active",
        persistent=persistent,
        capabilities=list(capabilities),
        created_at=now,
        last_seen_at=now,
        idle_expires_at=min(now + get_idle_duration(auth_type), absolute_expires_at),
        absolute_expires_at=absolute_expires_at,
        created_ip=created_ip,
        created_user_agent=user_agent,
        last_ip=created_ip,
        last_user_agent=user_agent,
    )
    db.add(auth_session)
    db.flush()

    for revoked_session in revoked_sessions:
        revoked_session.superseded_by_session_id = auth_session.id

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
        context=build_session_context(auth_session, user),
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
        return SessionLookupResult(
            context=None,
            reason=f"{auth_session.state}_session",
            should_clear_cookie=auth_session.revoked_reason_code != "evicted_by_session_limit",
            auth_type=auth_session.auth_type,
            session_limit=get_session_limit(auth_session.auth_type),
            can_evict_oldest=auth_session.revoked_reason_code == "evicted_by_session_limit",
        )

    if user.status != "active":
        delete_session_row(db, auth_session)
        db.commit()
        return SessionLookupResult(context=None, reason="user_disabled", should_clear_cookie=True)

    if is_session_expired(auth_session, now=now):
        delete_session_row(db, auth_session)
        db.commit()
        return SessionLookupResult(context=None, reason="expired_session", should_clear_cookie=True)

    if touch:
        auth_session.last_seen_at = now
        auth_session.last_ip = client_ip
        auth_session.last_user_agent = user_agent
        auth_session.idle_expires_at = min(
            auth_session.absolute_expires_at,
            now + get_idle_duration(auth_session.auth_type),
        )
        user.last_seen_at = now
        db.commit()

    return SessionLookupResult(
        context=build_session_context(auth_session, user),
        reason="authenticated",
        should_clear_cookie=False,
    )


def delete_session(
    db: Session,
    *,
    raw_session_key: str | None,
) -> bool:
    auth_session = load_session_by_raw_key(db, raw_session_key)
    if auth_session is None:
        return False

    delete_session_row(db, auth_session)
    db.commit()
    return True


def load_session_by_raw_key(
    db: Session,
    raw_session_key: str | None,
) -> AuthSession | None:
    if not raw_session_key:
        return None

    return db.execute(
        select(AuthSession).where(AuthSession.session_key_hash == hash_session_key(raw_session_key))
    ).scalar_one_or_none()


def build_session_context(auth_session: AuthSession, user: User) -> SessionContext:
    display_name = user.display_name
    if auth_session.auth_type == "guest" and user.guest_identity is not None:
        display_name = user.guest_identity.ip_address

    return SessionContext(
        session_id=auth_session.id,
        user_id=user.id,
        auth_type=auth_session.auth_type,
        display_name=display_name,
        email=user.email,
        capabilities=list(auth_session.capabilities or []),
        persistent=auth_session.persistent,
        idle_expires_at=auth_session.idle_expires_at,
        absolute_expires_at=auth_session.absolute_expires_at,
    )


def delete_session_row(
    db: Session,
    auth_session: AuthSession,
) -> None:
    user_id = auth_session.user_id
    db.delete(auth_session)
    db.flush()
    delete_orphan_guest_user(db, user_id=user_id)


def delete_orphan_guest_user(
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
    has_microsoft_identity = db.execute(
        select(MicrosoftIdentity.id).where(MicrosoftIdentity.user_id == user_id).limit(1)
    ).first()
    has_guest_identity = db.execute(
        select(GuestIdentity.id).where(GuestIdentity.user_id == user_id).limit(1)
    ).first()

    if has_sessions is None and has_microsoft_identity is None and has_guest_identity is None:
        db.delete(user)


def _enforce_session_limit(
    db: Session,
    *,
    user: User,
    auth_type: AuthType,
    replacement_session_id: str,
    now: datetime,
    strategy: SessionLimitStrategy | None = None,
) -> list[AuthSession]:
    max_sessions = get_session_limit(auth_type)
    active_sessions = _load_active_sessions_for_user(db, user_id=user.id, auth_type=auth_type, now=now)
    overflow = (len(active_sessions) + 1) - max_sessions
    if overflow <= 0:
        return []

    applied_strategy = strategy or settings.auth_session_limit_strategy
    if applied_strategy == "reject":
        raise SessionLimitExceededError(
            auth_type=auth_type,
            session_limit=max_sessions,
            strategy=applied_strategy,
        )

    sessions_to_revoke = active_sessions[:overflow]
    for auth_session in sessions_to_revoke:
        _revoke_session(
            auth_session,
            now=now,
            reason_code="evicted_by_session_limit",
            reason=(
                f"Revoked to make room for a newer {auth_type} session "
                f"(replacement session {replacement_session_id})."
            ),
        )

    return sessions_to_revoke


def _load_active_sessions_for_user(
    db: Session,
    *,
    user_id: str,
    auth_type: AuthType,
    now: datetime,
) -> list[AuthSession]:
    sessions = db.execute(
        select(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.auth_type == auth_type,
            AuthSession.state == "active",
        )
        .order_by(
            AuthSession.last_seen_at.asc().nullsfirst(),
            AuthSession.created_at.asc(),
        )
    ).scalars().all()

    active_sessions: list[AuthSession] = []
    for auth_session in sessions:
        if is_session_expired(auth_session, now=now):
            delete_session_row(db, auth_session)
            continue
        active_sessions.append(auth_session)

    return active_sessions


def _revoke_session(
    auth_session: AuthSession,
    *,
    now: datetime,
    reason_code: str,
    reason: str,
) -> None:
    auth_session.state = "revoked"
    auth_session.revoked_at = now
    auth_session.revoked_reason_code = reason_code
    auth_session.revoke_reason = reason


def is_session_expired(
    auth_session: AuthSession,
    *,
    now: datetime,
) -> bool:
    return auth_session.absolute_expires_at <= now or auth_session.idle_expires_at <= now

