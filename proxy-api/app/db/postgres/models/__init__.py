"""
ORM model package for PostgreSQL tables.

Purpose:
- Group SQLAlchemy model definitions for persistent application data.
"""

from app.db.postgres.models.auth_conflicts import AuthConflictTicket
from app.db.postgres.models.auth_sessions import AuthProviderSession, AuthSession
from app.db.postgres.models.chat_history import ChatHistory, ChatHistoryMemory, ChatMessage
from app.db.postgres.models.identities import GuestIdentity, MicrosoftIdentity
from app.db.postgres.models.oauth_transactions import OAuthTransaction
from app.db.postgres.models.user import User

__all__ = [
    "AuthConflictTicket",
    "AuthProviderSession",
    "AuthSession",
    "GuestIdentity",
    "ChatHistory",
    "ChatHistoryMemory",
    "ChatMessage",
    "MicrosoftIdentity",
    "OAuthTransaction",
    "User",
]
