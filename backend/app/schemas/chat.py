"""
Purpose:
- Define chat request and streaming event schemas for the API layer.

Responsibilities:
- Validate incoming chat payloads
- Keep the public contract explicit and versionable
- Separate request validation from provider-specific payloads

Notes:
- Public API schemas should remain stable even if provider details change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config.chat import CHAT_HISTORY_TITLE_MAX_CHARS, MAX_SELECTED_TOOL_IDS


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("message content must not be blank")
        return trimmed


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_history_id: str | None = Field(default=None, min_length=1, max_length=36)
    model_id: str | None = Field(default=None, min_length=1)
    tool_ids: list[str] = Field(default_factory=list, max_length=MAX_SELECTED_TOOL_IDS)
    prompt: str = Field(..., min_length=1)

    @field_validator("tool_ids")
    @classmethod
    def validate_tool_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            trimmed = item.strip()
            if not trimmed:
                raise ValueError("tool ids must not be blank")
            normalized.append(trimmed)
        return normalized

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("prompt must not be blank")
        return trimmed

    @property
    def conversation_id(self) -> str:
        return self.chat_history_id or ""


class ChatUsageSummary(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ChatStreamStartEvent(BaseModel):
    model: str | None = None
    provider: str | None = None
    chat_history_id: str
    user_message_id: str
    assistant_message_id: str


class ChatStreamDeltaEvent(BaseModel):
    delta_text: str


class ChatStreamStatusEvent(BaseModel):
    provider: str | None = None
    status_code: str
    status_message: str


class ChatStreamThinkingBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    operation: Literal["start", "delta", "end"]
    block_id: str
    text_delta: str = ""
    metadata: dict[str, object]


class ChatStreamToolUsageBlock(BaseModel):
    type: Literal["tool"] = "tool"
    operation: Literal["start", "delta", "end"]
    block_id: str
    metadata: dict[str, object]
    raw: object


class ChatHistoryMessageBlockView(BaseModel):
    id: str
    type: Literal["thinking", "tool"]
    sequence: int
    block_id: str
    text: str
    metadata: dict[str, object]
    raw_events: list[object]
    started_at: datetime
    completed_at: datetime
    created_at: datetime
    updated_at: datetime


class ChatStreamDoneEvent(BaseModel):
    model: str | None = None
    provider: str | None = None
    result_code: str
    result_message: str
    finish_reason: str | None = None
    usage: ChatUsageSummary | None = None


class ChatStreamErrorEvent(BaseModel):
    result_code: str
    result_message: str
    retry_after_seconds: int | None = None
    detail: str


class ChatHistoryTitleUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=CHAT_HISTORY_TITLE_MAX_CHARS)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("title must not be blank")
        return trimmed


class ChatHistorySummary(BaseModel):
    id: str
    title: str
    pin_order: int | None = None
    lifecycle_state: Literal["active", "deleting"] = "active"
    operation_state: Literal["ready", "running", "provider_streaming"] = "ready"
    operation_type: str | None = None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None
    message_count: int
    attachment_count: int


class ChatAttachmentLimitsView(BaseModel):
    max_files_per_history: int
    max_files_per_user: int


class ChatHistoryListEnvelope(BaseModel):
    histories: list[ChatHistorySummary]
    attachment_limits: ChatAttachmentLimitsView


class ChatHistoryFileTokenSummary(BaseModel):
    openai: int | None = None
    anthropic: int | None = None
    vertex_ai: int | None = None


class ChatHistoryFileView(BaseModel):
    id: str
    display_name: str
    mime_type: str
    byte_size: int
    is_active: bool
    token_counts: ChatHistoryFileTokenSummary
    created_at: datetime
    updated_at: datetime


class ChatHistoryFileUpdateRequest(BaseModel):
    is_active: bool


class ChatHistoryMessageView(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    status: Literal["done", "streaming", "error"]
    sequence: int
    excluded_from_context: bool
    model_id: str | None = None
    provider: str | None = None
    tool_ids: list[str]
    finish_reason: str | None = None
    result_code: str | None = None
    result_message: str | None = None
    error_detail: str | None = None
    blocks: list[ChatHistoryMessageBlockView]
    block_activity_started_at: datetime | None = None
    block_activity_completed_at: datetime | None = None
    block_activity_duration_ms: int | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChatHistoryEnvelope(BaseModel):
    history: ChatHistorySummary
    files: list[ChatHistoryFileView]
    messages: list[ChatHistoryMessageView]
    attachment_limits: ChatAttachmentLimitsView


class ChatHistoryFilesEnvelope(BaseModel):
    history: ChatHistorySummary | None = None
    files: list[ChatHistoryFileView]
    deleted_history_id: str | None = None
    attachment_limits: ChatAttachmentLimitsView
