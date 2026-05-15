from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.config.time import utc_now
from app.db.postgres.base import Base


class OAuthTransaction(Base):
    __tablename__ = "oauth_transactions"
    __table_args__ = (
        CheckConstraint("provider IN ('microsoft')", name="ck_oauth_transactions_provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    pkce_verifier_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    return_to: Mapped[str] = mapped_column(String(2048), nullable=False, default="/")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requester_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requester_user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

