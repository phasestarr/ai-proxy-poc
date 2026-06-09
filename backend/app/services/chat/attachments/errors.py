from __future__ import annotations


class ChatHistoryFileNotFoundError(RuntimeError):
    """Raised when a chat attachment does not belong to the current user/history."""


class ChatHistoryDuplicateFileError(RuntimeError):
    """Raised when the same stored file is already attached to a chat history."""
