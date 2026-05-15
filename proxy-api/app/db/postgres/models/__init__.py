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
from app.db.postgres.models.chat_request_rejection import ChatRequestRejection
from app.db.postgres.models.identities import GuestIdentity, MicrosoftIdentity
from app.db.postgres.models.oauth_transactions import OAuthTransaction
from app.db.postgres.models.user import User

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
    "ChatRequestRejection",
    "MicrosoftIdentity",
    "OAuthTransaction",
    "StoredFile",
    "StoredFileProviderState",
    "User",
]
