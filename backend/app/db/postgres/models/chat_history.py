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
            "lifecycle_state IN ('active', 'deleting')",
            name="ck_chat_histories_lifecycle_state",
        ),
        Index("ix_chat_histories_user_updated", "user_id", "updated_at"),
        Index("ix_chat_histories_user_pin_order", "user_id", "pin_order"),
        Index("ix_chat_histories_active_operation", "active_operation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_order: Mapped[int | None] = mapped_column(nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    active_operation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_operation_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
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
    operations: Mapped[list["ChatOperation"]] = relationship(
        back_populates="history",
        cascade="all, delete-orphan",
        foreign_keys="ChatOperation.chat_history_id",
    )


class ChatDraft(Base):
    __tablename__ = "chat_drafts"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN ('active', 'expired')",
            name="ck_chat_drafts_lifecycle_state",
        ),
        Index("ix_chat_drafts_user_created", "user_id", "created_at"),
        Index("ix_chat_drafts_expires", "lifecycle_state", "expires_at"),
        Index("ix_chat_drafts_active_operation", "active_operation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    lifecycle_state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    active_operation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_operation_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="chat_drafts")
    files: Mapped[list["ChatDraftFile"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="ChatDraftFile.created_at",
    )
    operations: Mapped[list["ChatOperation"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        foreign_keys="ChatOperation.draft_id",
    )


class ChatOperation(Base):
    __tablename__ = "chat_operations"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('history', 'draft')",
            name="ck_chat_operations_scope_type",
        ),
        CheckConstraint(
            "operation_type IN ('send', 'attach_file', 'delete_file', 'toggle_file', 'delete_history')",
            name="ck_chat_operations_operation_type",
        ),
        CheckConstraint(
            "state IN ('validating', 'provider_streaming', 'finalizing', 'succeeded', 'failed', 'timed_out', 'cancelled')",
            name="ck_chat_operations_state",
        ),
        Index("ix_chat_operations_scope_state", "scope_type", "scope_id", "state"),
        Index("ix_chat_operations_deadline", "state", "deadline_at"),
        Index("ix_chat_operations_history_created", "chat_history_id", "created_at"),
        Index("ix_chat_operations_draft_created", "draft_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    auth_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(36), nullable=False)
    chat_history_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_histories.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_drafts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_token: Mapped[str] = mapped_column(String(64), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    provider_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_provider_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_provider_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_max_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="chat_operations")
    history: Mapped["ChatHistory | None"] = relationship(
        back_populates="operations",
        foreign_keys=[chat_history_id],
    )
    draft: Mapped["ChatDraft | None"] = relationship(
        back_populates="operations",
        foreign_keys=[draft_id],
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
