"""
Chat service package.

Purpose:
- Group chat request preparation and streaming orchestration.
"""

from app.services.chat.completions.route_selection import (
    PreparedChatCompletionRequest,
    prepare_chat_completion_request,
)
from app.services.chat.completions.orchestrator import (
    create_chat_completion_stream,
)

__all__ = [
    "PreparedChatCompletionRequest",
    "create_chat_completion_stream",
    "prepare_chat_completion_request",
]
