from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config.time import utc_now
from app.db.postgres.base import Base


class AuthConflictTicket(Base):
    __tablename__ = "auth_conflict_tickets"
    __table_args__ = (
        CheckConstraint("auth_type IN ('guest', 'microsoft')", name="ck_auth_conflict_tickets_auth_type"),
        CheckConstraint("reason IN ('session_limit_reached')", name="ck_auth_conflict_tickets_reason"),
        Index("ix_auth_conflict_tickets_user_auth_type", "user_id", "auth_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ticket_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    return_to: Mapped[str] = mapped_column(String(2048), nullable=False, default="/")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requester_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requester_user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship()

