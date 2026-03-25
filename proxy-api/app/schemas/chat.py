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

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("message content must not be blank")
        return trimmed


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="vertex-default", min_length=1)
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=100)

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
    model: str
    provider: str


class ChatStreamDeltaEvent(BaseModel):
    delta_text: str


class ChatStreamDoneEvent(BaseModel):
    model: str
    provider: str
    finish_reason: str | None = None
    usage: ChatUsageSummary | None = None


class ChatStreamErrorEvent(BaseModel):
    detail: str
