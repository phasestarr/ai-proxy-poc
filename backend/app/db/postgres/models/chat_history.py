"""
Purpose:
- Define persisted chat history and message models.

Responsibilities:
- Own user chat transcripts in PostgreSQL
- Cascade messages when a chat history is deleted
- Keep failed turns renderable while excluding them from future provider context
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.time import utc_now
from app.db.postgres.base import Base


class ChatHistory(Base):
    __tablename__ = "chat_histories"
    __table_args__ = (
        CheckConstraint(
            "interaction_state IN ('ready', 'validating', 'waiting')",
            name="ck_chat_histories_interaction_state",
        ),
        CheckConstraint(
            "busy_reason IS NULL OR busy_reason IN ('send', 'attach_file', 'delete_file', 'delete_history')",
            name="ck_chat_histories_busy_reason",
        ),
        Index("ix_chat_histories_user_updated", "user_id", "updated_at"),
        Index("ix_chat_histories_user_pin_order", "user_id", "pin_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_order: Mapped[int | None] = mapped_column(nullable=True)
    interaction_state: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    busy_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    state_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="chat_histories")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="history",
        cascade="all, delete-orphan",
        order_by="ChatMessage.sequence",
    )
    memory_record: Mapped["ChatHistoryMemory | None"] = relationship(
        back_populates="history",
        cascade="all, delete-orphan",
        uselist=False,
    )
    context_checkpoint: Mapped["ChatContextCheckpoint | None"] = relationship(
        back_populates="history",
        cascade="all, delete-orphan",
        uselist=False,
    )
    files: Mapped[list["ChatHistoryFile"]] = relationship(
        back_populates="history",
        cascade="all, delete-orphan",
        order_by="ChatHistoryFile.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),
        CheckConstraint("status IN ('done', 'streaming', 'error')", name="ck_chat_messages_status"),
        UniqueConstraint("chat_history_id", "sequence", name="uq_chat_messages_history_sequence"),
        Index("ix_chat_messages_history_sequence", "chat_history_id", "sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chat_history_id: Mapped[str] = mapped_column(
        ForeignKey("chat_histories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="done")
    excluded_from_context: Mapped[bool] = mapped_column(nullable=False, default=False)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    finish_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    history: Mapped["ChatHistory"] = relationship(back_populates="messages")
    attachments: Mapped[list["ChatMessageAttachment"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ChatMessageAttachment.attachment_index",
    )


class ChatHistoryMemory(Base):
    __tablename__ = "chat_history_memories"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name="ck_chat_history_memories_status",
        ),
        UniqueConstraint("chat_history_id", name="uq_chat_history_memories_chat_history_id"),
        Index("ix_chat_history_memories_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_history_id: Mapped[str] = mapped_column(
        ForeignKey("chat_histories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_last_message_sequence: Mapped[int | None] = mapped_column(nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="chat_history_memories")
    history: Mapped["ChatHistory"] = relationship(back_populates="memory_record")


class ChatContextCheckpoint(Base):
    __tablename__ = "chat_context_checkpoints"
    __table_args__ = (
        CheckConstraint(
            "status IN ('building', 'ready', 'failed')",
            name="ck_chat_context_checkpoints_status",
        ),
        UniqueConstraint("chat_history_id", name="uq_chat_context_checkpoints_chat_history_id"),
        Index("ix_chat_context_checkpoints_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_history_id: Mapped[str] = mapped_column(
        ForeignKey("chat_histories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="building")
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    covered_through_sequence: Mapped[int | None] = mapped_column(nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="chat_context_checkpoints")
    history: Mapped["ChatHistory"] = relationship(back_populates="context_checkpoint")
