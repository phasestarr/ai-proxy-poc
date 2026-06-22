from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.config.time import utc_now
from app.db.postgres.base import Base


class UsageLedgerEvent(Base):
    __tablename__ = "usage_ledger_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('billable', 'adjustment')",
            name="ck_usage_ledger_events_status",
        ),
        CheckConstraint(
            "source IN ('chat_completion', 'backfill', 'operator_adjustment')",
            name="ck_usage_ledger_events_source",
        ),
        Index("ix_usage_ledger_events_user_created", "user_id", "created_at"),
        Index("ix_usage_ledger_events_provider_created", "provider", "created_at"),
        Index("ix_usage_ledger_events_message", "chat_message_id_snapshot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    auth_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    chat_history_id_snapshot: Mapped[str | None] = mapped_column(String(36), nullable=True)
    chat_message_id_snapshot: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tool_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    operation: Mapped[str] = mapped_column(String(64), nullable=False, default="chat_completion")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="billable")
    result_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens_reported: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens_reported: Mapped[int | None] = mapped_column(nullable=True)
    total_tokens_reported: Mapped[int | None] = mapped_column(nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    cache_write_input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(nullable=True)
    tool_result_input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    web_search_requests: Mapped[int | None] = mapped_column(nullable=True)
    file_search_requests: Mapped[int | None] = mapped_column(nullable=True)
    code_execution_requests: Mapped[int | None] = mapped_column(nullable=True)
    price_estimate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider_raw_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="USD")
    pricing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_completeness: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
