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

from pydantic import BaseModel, Field, field_validator, model_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1, max_length=65535)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("message content must not be blank")
        return trimmed


class ChatCompletionRequest(BaseModel):
    chat_history_id: str | None = Field(default=None, min_length=1, max_length=36)
    model_id: str | None = Field(default=None, min_length=1)
    tool_ids: list[str] = Field(default_factory=list, max_length=16)
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=100)

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

    @model_validator(mode="after")
    def validate_messages(self) -> "ChatCompletionRequest":
        if not any(message.role == "user" for message in self.messages):
            raise ValueError("at least one user message is required")
        if self.messages[-1].role != "user":
            raise ValueError("last message must have role 'user'")
        return self


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
    error_origin: str
    error_http_status: int | None = None
    provider: str | None = None
    provider_error_code: str | None = None
    retry_after_seconds: int | None = None
    detail: str


class ChatHistoryCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("title must not be blank")
        return trimmed


class ChatHistorySummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None
    message_count: int


class ChatHistoryListEnvelope(BaseModel):
    histories: list[ChatHistorySummary]


class ChatHistoryUsageSummary(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


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
    error_origin: str | None = None
    error_http_status: int | None = None
    provider_error_code: str | None = None
    retry_after_seconds: int | None = None
    error_detail: str | None = None
    usage: ChatHistoryUsageSummary | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChatHistoryEnvelope(BaseModel):
    history: ChatHistorySummary
    messages: list[ChatHistoryMessageView]
