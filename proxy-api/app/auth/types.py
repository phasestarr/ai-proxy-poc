from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AuthType = Literal["guest", "microsoft"]
SessionLimitStrategy = Literal["reject", "evict_oldest"]


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
class CreatedSessionConflictTicket:
    raw_ticket: str
    expires_at: datetime
    return_to: str
    auth_type: AuthType
    session_limit: int


@dataclass(slots=True)
class SessionLookupResult:
    context: SessionContext | None
    reason: str
    should_clear_cookie: bool
    auth_type: AuthType | None = None
    session_limit: int | None = None
    can_evict_oldest: bool = False


@dataclass(slots=True)
class SessionLimitExceededError(RuntimeError):
    auth_type: AuthType
    session_limit: int
    strategy: SessionLimitStrategy

    def __str__(self) -> str:
        return f"{self.auth_type} session limit reached"


@dataclass(slots=True)
class SessionConflictResolutionError(RuntimeError):
    reason: str
    detail: str
    auth_type: AuthType | None = None

    def __str__(self) -> str:
        return self.detail


@dataclass(slots=True)
class SessionConflictTicketLookupResult:
    has_conflict: bool
    should_clear_cookie: bool
    reason: str
    detail: str = ""
    auth_type: AuthType | None = None
    session_limit: int | None = None

