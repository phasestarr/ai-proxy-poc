"""
ORM model package for PostgreSQL tables.

Purpose:
- Group SQLAlchemy model definitions for persistent application data.
"""

from app.db.postgres.models.auth_conflicts import AuthConflictTicket
from app.db.postgres.models.auth_sessions import AuthProviderSession, AuthSession
from app.db.postgres.models.chat_attachment import (
    ChatDraftFile,
    ChatHistoryFile,
    ChatMessageAttachment,
    StoredFile,
    StoredFileProviderState,
)
from app.db.postgres.models.chat_history import (
    ChatContextCheckpoint,
    ChatDraft,
    ChatHistory,
    ChatHistoryMemory,
    ChatMessage,
    ChatMessageBlock,
    ChatOperation,
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
    "ChatDraft",
    "ChatDraftFile",
    "ChatHistoryFile",
    "ChatContextCheckpoint",
    "ChatHistory",
    "ChatHistoryMemory",
    "ChatMessage",
    "ChatMessageAttachment",
    "ChatMessageBlock",
    "ChatOperation",
    "MicrosoftIdentity",
    "OperatorEvent",
    "OAuthTransaction",
    "StoredFile",
    "StoredFileProviderState",
    "UsageLedgerEvent",
    "User",
    "UserUsageCap",
]
