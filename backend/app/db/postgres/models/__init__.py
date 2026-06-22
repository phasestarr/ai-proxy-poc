"""
ORM model package for PostgreSQL tables.

Purpose:
- Group SQLAlchemy model definitions for persistent application data.
"""

from app.db.postgres.models.auth_conflicts import AuthConflictTicket
from app.db.postgres.models.auth_sessions import AuthProviderSession, AuthSession
from app.db.postgres.models.chat_attachment import (
    ChatHistoryFile,
    ChatMessageAttachment,
    StoredFile,
    StoredFileProviderState,
)
from app.db.postgres.models.chat_history import (
    ChatContextCheckpoint,
    ChatHistory,
    ChatHistoryMemory,
    ChatMessage,
)
from app.db.postgres.models.identities import GuestIdentity, MicrosoftIdentity
from app.db.postgres.models.operator_event import OperatorEvent
from app.db.postgres.models.oauth_transactions import OAuthTransaction
from app.db.postgres.models.usage_ledger import UsageLedgerEvent
from app.db.postgres.models.user import User
from app.db.postgres.models.user_usage_cap import UserUsageCap

__all__ = [
    "AuthConflictTicket",
    "AuthProviderSession",
    "AuthSession",
    "GuestIdentity",
    "ChatHistoryFile",
    "ChatContextCheckpoint",
    "ChatHistory",
    "ChatHistoryMemory",
    "ChatMessage",
    "ChatMessageAttachment",
    "MicrosoftIdentity",
    "OperatorEvent",
    "OAuthTransaction",
    "StoredFile",
    "StoredFileProviderState",
    "UsageLedgerEvent",
    "User",
    "UserUsageCap",
]
