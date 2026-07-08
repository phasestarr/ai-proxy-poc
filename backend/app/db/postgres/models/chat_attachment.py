"""
Purpose:
- Define persisted chat attachment models.

Responsibilities:
- Store backend-owned uploaded file bytes in PostgreSQL
- Deduplicate identical files per user while preserving logical history attachments
- Track provider-specific token counts and provider file references
- Snapshot which attachments were used for each persisted user turn
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.time import utc_now
from app.db.postgres.base import Base


class StoredFile(Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN ('active', 'pending_delete', 'delete_failed')",
            name="ck_stored_files_lifecycle_state",
        ),
        UniqueConstraint("user_id", "sha256", name="uq_stored_files_user_sha256"),
        Index("ix_stored_files_user_created", "user_id", "created_at"),
        Index("ix_stored_files_lifecycle_retry", "lifecycle_state", "delete_next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    delete_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delete_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delete_last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delete_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="stored_files")
    provider_states: Mapped[list["StoredFileProviderState"]] = relationship(
        back_populates="stored_file",
        cascade="all, delete-orphan",
    )
    history_files: Mapped[list["ChatHistoryFile"]] = relationship(
        back_populates="stored_file",
        cascade="all, delete-orphan",
    )
    draft_files: Mapped[list["ChatDraftFile"]] = relationship(
        back_populates="stored_file",
        cascade="all, delete-orphan",
    )


class StoredFileProviderState(Base):
    __tablename__ = "stored_file_provider_states"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('openai', 'anthropic', 'vertex_ai')",
            name="ck_stored_file_provider_states_provider",
        ),
        CheckConstraint(
            "token_count_status IN ('ready', 'failed', 'unsupported')",
            name="ck_stored_file_provider_states_token_count_status",
        ),
        CheckConstraint(
            "remote_file_status IN ('not_uploaded', 'ready', 'failed', 'unsupported')",
            name="ck_stored_file_provider_states_remote_file_status",
        ),
        UniqueConstraint("stored_file_id", "provider", name="uq_stored_file_provider_states_file_provider"),
        Index("ix_stored_file_provider_states_provider_status", "provider", "remote_file_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    stored_file_id: Mapped[str] = mapped_column(
        ForeignKey("stored_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int | None] = mapped_column(nullable=True)
    token_count_status: Mapped[str] = mapped_column(String(16), nullable=False)
    token_count_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_file_status: Mapped[str] = mapped_column(String(16), nullable=False, default="not_uploaded")
    remote_file_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    count_model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    stored_file: Mapped["StoredFile"] = relationship(back_populates="provider_states")


class ChatHistoryFile(Base):
    __tablename__ = "chat_history_files"
    __table_args__ = (
        UniqueConstraint("chat_history_id", "stored_file_id", name="uq_chat_history_files_history_stored_file"),
        Index("ix_chat_history_files_history_created", "chat_history_id", "created_at"),
        Index("ix_chat_history_files_user_history", "user_id", "chat_history_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_history_id: Mapped[str] = mapped_column(
        ForeignKey("chat_histories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stored_file_id: Mapped[str] = mapped_column(
        ForeignKey("stored_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="chat_history_files")
    history: Mapped["ChatHistory"] = relationship(back_populates="files")
    stored_file: Mapped["StoredFile"] = relationship(back_populates="history_files")


class ChatDraftFile(Base):
    __tablename__ = "chat_draft_files"
    __table_args__ = (
        UniqueConstraint("draft_id", "stored_file_id", name="uq_chat_draft_files_draft_stored_file"),
        Index("ix_chat_draft_files_draft_created", "draft_id", "created_at"),
        Index("ix_chat_draft_files_user_draft", "user_id", "draft_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("chat_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stored_file_id: Mapped[str] = mapped_column(
        ForeignKey("stored_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="chat_draft_files")
    draft: Mapped["ChatDraft"] = relationship(back_populates="files")
    stored_file: Mapped["StoredFile"] = relationship(back_populates="draft_files")


class ChatMessageAttachment(Base):
    __tablename__ = "chat_message_attachments"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('openai', 'anthropic', 'vertex_ai')",
            name="ck_chat_message_attachments_provider",
        ),
        UniqueConstraint("chat_message_id", "attachment_index", name="uq_chat_message_attachments_message_index"),
        Index("ix_chat_message_attachments_message_index", "chat_message_id", "attachment_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chat_message_id: Mapped[str] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attachment_index: Mapped[int] = mapped_column(nullable=False)
    chat_history_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    stored_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    message: Mapped["ChatMessage"] = relationship(back_populates="attachments")
