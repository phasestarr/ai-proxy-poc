from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import secrets
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.conflict_tickets import create_session_conflict_ticket
from app.auth.encryption import decrypt_auth_payload, encrypt_auth_payload
from app.auth.session_lifecycle import issue_session
from app.auth.types import CreatedSession, CreatedSessionConflictTicket, SessionLimitExceededError
from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.identities import MicrosoftIdentity
from app.db.postgres.models.oauth_transactions import OAuthTransaction
from app.db.postgres.models.user import User

MICROSOFT_PROVIDER = "microsoft"
DEFAULT_CHAT_CAPABILITIES = ["chat:send"]
MSAL_RESERVED_SCOPES = {"openid", "profile", "offline_access"}


class MicrosoftOAuthConfigurationError(RuntimeError):
    """Raised when Microsoft OAuth is not configured for this deployment."""


@dataclass(slots=True)
class MicrosoftOAuthRedirectError(RuntimeError):
    error_code: str
    return_to: str | None = None

    def __str__(self) -> str:
        return self.error_code


@dataclass(slots=True)
class MicrosoftAuthorizationCompletion:
    return_to: str
    created_session: CreatedSession | None = None
    conflict_ticket: CreatedSessionConflictTicket | None = None


def build_microsoft_authorization_url(
    db: Session,
    *,
    redirect_uri: str,
    return_to: str | None,
    requester_ip: str | None,
    requester_user_agent: str | None,
) -> str:
    _ensure_microsoft_auth_is_configured()

    app = _build_msal_application()
    now = utc_now()
    state = secrets.token_urlsafe(32)
    flow = app.initiate_auth_code_flow(
        scopes=_get_microsoft_login_scopes(),
        redirect_uri=redirect_uri,
        state=state,
        response_mode="query",
    )

    if "error" in flow:
        raise MicrosoftOAuthRedirectError("microsoft_login_failed")

    authorization_url = flow.get("auth_uri")
    if not isinstance(authorization_url, str) or not authorization_url:
        raise MicrosoftOAuthRedirectError("microsoft_login_failed")

    transaction = OAuthTransaction(
        id=str(uuid4()),
        provider=MICROSOFT_PROVIDER,
        state=str(flow.get("state") or state),
        nonce=str(flow.get("nonce") or secrets.token_urlsafe(24)),
        pkce_verifier_encrypted=encrypt_auth_payload(_serialize_auth_code_flow(flow)),
        return_to=_normalize_return_to(return_to),
        created_at=now,
        expires_at=now + timedelta(minutes=settings.microsoft_oauth_transaction_minutes),
        requester_ip=requester_ip,
        requester_user_agent=requester_user_agent,
    )
    db.add(transaction)
    db.commit()
    return authorization_url


def complete_microsoft_authorization(
    db: Session,
    *,
    auth_response: dict[str, str],
    redirect_uri: str,
    requester_ip: str | None,
    requester_user_agent: str | None,
) -> MicrosoftAuthorizationCompletion:
    _ensure_microsoft_auth_is_configured()

    transaction = _load_active_transaction(db, auth_response.get("state"))
    return_to = transaction.return_to

    if auth_response.get("error"):
        _delete_transaction(db, transaction)
        error_code = "microsoft_login_cancelled" if auth_response["error"] == "access_denied" else "microsoft_login_failed"
        raise MicrosoftOAuthRedirectError(error_code, return_to=return_to)

    auth_code_flow = _deserialize_auth_code_flow(transaction.pkce_verifier_encrypted)
    app = _build_msal_application()

    try:
        result = app.acquire_token_by_auth_code_flow(auth_code_flow, auth_response)
    except ValueError as exc:
        _delete_transaction(db, transaction)
        raise MicrosoftOAuthRedirectError("microsoft_login_invalid_state", return_to=return_to) from exc

    if "error" in result:
        _delete_transaction(db, transaction)
        raise MicrosoftOAuthRedirectError("microsoft_login_failed", return_to=return_to)

    user = _resolve_microsoft_user(db, result=result)
    db.delete(transaction)

    try:
        created_session = issue_session(
            db,
            user=user,
            auth_type=MICROSOFT_PROVIDER,
            capabilities=DEFAULT_CHAT_CAPABILITIES,
            persistent=False,
            created_ip=requester_ip,
            user_agent=requester_user_agent,
        )
    except SessionLimitExceededError:
        conflict_ticket = create_session_conflict_ticket(
            db,
            user=user,
            auth_type=MICROSOFT_PROVIDER,
            capabilities=DEFAULT_CHAT_CAPABILITIES,
            persistent=False,
            return_to=return_to,
            requester_ip=requester_ip,
            requester_user_agent=requester_user_agent,
        )
        return MicrosoftAuthorizationCompletion(
            return_to=return_to,
            conflict_ticket=conflict_ticket,
        )
    return MicrosoftAuthorizationCompletion(return_to=return_to, created_session=created_session)


def get_microsoft_return_to(
    db: Session,
    *,
    state: str | None,
) -> str:
    transaction = _load_transaction(db, state)
    if transaction is None:
        return "/"
    return transaction.return_to


def _resolve_microsoft_user(
    db: Session,
    *,
    result: dict[str, Any],
) -> User:
    claims = result.get("id_token_claims")
    if not isinstance(claims, dict):
        raise MicrosoftOAuthRedirectError("microsoft_login_failed")

    tenant_id = _coerce_claim(claims.get("tid"))
    subject = _coerce_claim(claims.get("sub")) or _coerce_claim(claims.get("oid"))
    if not tenant_id or not subject:
        raise MicrosoftOAuthRedirectError("microsoft_login_failed")

    preferred_username = _coerce_claim(claims.get("preferred_username"))
    email = _coerce_claim(claims.get("email")) or preferred_username
    display_name = (
        _coerce_claim(claims.get("name"))
        or preferred_username
        or email
        or f"Microsoft-{subject[-6:]}"
    )
    account = result.get("account")
    account_home_id = _coerce_claim(account.get("home_account_id")) if isinstance(account, dict) else None
    home_account_id = _coerce_claim(claims.get("oid")) or account_home_id

    identity = db.execute(
        select(MicrosoftIdentity).where(
            MicrosoftIdentity.provider == MICROSOFT_PROVIDER,
            MicrosoftIdentity.tenant_id == tenant_id,
            MicrosoftIdentity.subject == subject,
        )
    ).scalar_one_or_none()

    now = utc_now()
    if identity is None:
        user = User(
            id=str(uuid4()),
            account_type="human",
            status="active",
            display_name=display_name,
            email=email,
            last_seen_at=now,
        )
        db.add(user)
        db.flush()

        identity = MicrosoftIdentity(
            id=str(uuid4()),
            user_id=user.id,
            provider=MICROSOFT_PROVIDER,
            tenant_id=tenant_id,
            subject=subject,
            home_account_id=home_account_id,
            preferred_username=preferred_username,
        )
        db.add(identity)
        return user

    user = identity.user
    if user.status != "active":
        raise MicrosoftOAuthRedirectError("microsoft_login_failed")

    user.display_name = display_name
    user.email = email
    user.last_seen_at = now
    identity.home_account_id = home_account_id
    identity.preferred_username = preferred_username
    return user


def _load_active_transaction(db: Session, state: str | None) -> OAuthTransaction:
    transaction = _load_transaction(db, state)
    if transaction is None:
        raise MicrosoftOAuthRedirectError("microsoft_login_invalid_state")

    if transaction.consumed_at is not None:
        _delete_transaction(db, transaction)
        raise MicrosoftOAuthRedirectError("microsoft_login_invalid_state", return_to=transaction.return_to)

    if transaction.expires_at <= utc_now():
        _delete_transaction(db, transaction)
        raise MicrosoftOAuthRedirectError("microsoft_login_expired", return_to=transaction.return_to)

    transaction.consumed_at = utc_now()
    db.flush()
    return transaction


def _load_transaction(db: Session, state: str | None) -> OAuthTransaction | None:
    if not state:
        return None

    return db.execute(
        select(OAuthTransaction).where(
            OAuthTransaction.provider == MICROSOFT_PROVIDER,
            OAuthTransaction.state == state,
        )
    ).scalar_one_or_none()


def _delete_transaction(db: Session, transaction: OAuthTransaction) -> None:
    db.delete(transaction)
    db.commit()


def _serialize_auth_code_flow(flow: dict[str, Any]) -> bytes:
    return json.dumps(flow, default=str).encode("utf-8")


def _deserialize_auth_code_flow(payload: bytes) -> dict[str, Any]:
    decoded = decrypt_auth_payload(payload).decode("utf-8")
    flow = json.loads(decoded)
    if not isinstance(flow, dict):
        raise MicrosoftOAuthRedirectError("microsoft_login_failed")
    return flow


def _normalize_return_to(return_to: str | None) -> str:
    candidate = (return_to or "/").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    return candidate


def _coerce_claim(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return None


def _ensure_microsoft_auth_is_configured() -> None:
    if not settings.microsoft_client_id or not settings.microsoft_client_secret:
        raise MicrosoftOAuthConfigurationError("Microsoft OAuth is not configured")

    if not settings.auth_data_encryption_key:
        raise MicrosoftOAuthConfigurationError("AUTH_DATA_ENCRYPTION_KEY is not configured")


def _get_microsoft_login_scopes() -> list[str]:
    return [
        scope
        for scope in settings.microsoft_scopes
        if scope.strip() and scope.strip().lower() not in MSAL_RESERVED_SCOPES
    ]


def _build_msal_application():
    try:
        import msal
    except ImportError as exc:
        raise MicrosoftOAuthConfigurationError("msal is required for Microsoft OAuth") from exc

    return msal.ConfidentialClientApplication(
        client_id=settings.microsoft_client_id,
        client_credential=settings.microsoft_client_secret,
        authority=settings.microsoft_authority,
    )

