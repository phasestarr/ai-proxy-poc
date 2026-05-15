"""Add persisted chat outcome fields.

Revision ID: 20260423_000006
Revises: 20260420_000005
Create Date: 2026-04-23 00:00:06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260423_000006"
down_revision = "20260420_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("result_code", sa.String(length=64), nullable=True))
    op.add_column("chat_messages", sa.Column("result_message", sa.Text(), nullable=True))
    op.add_column("chat_messages", sa.Column("error_origin", sa.String(length=32), nullable=True))
    op.add_column("chat_messages", sa.Column("error_http_status", sa.Integer(), nullable=True))
    op.add_column("chat_messages", sa.Column("provider_error_code", sa.String(length=128), nullable=True))
    op.add_column("chat_messages", sa.Column("retry_after_seconds", sa.Integer(), nullable=True))
    op.add_column("chat_messages", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "completed_at")
    op.drop_column("chat_messages", "retry_after_seconds")
    op.drop_column("chat_messages", "provider_error_code")
    op.drop_column("chat_messages", "error_http_status")
    op.drop_column("chat_messages", "error_origin")
    op.drop_column("chat_messages", "result_message")
    op.drop_column("chat_messages", "result_code")
