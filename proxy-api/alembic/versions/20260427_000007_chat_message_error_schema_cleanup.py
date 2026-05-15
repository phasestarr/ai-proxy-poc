"""Drop obsolete persisted chat error columns.

Revision ID: 20260427_000007
Revises: 20260423_000006
Create Date: 2026-04-27 00:00:07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260427_000007"
down_revision = "20260423_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("chat_messages", "retry_after_seconds")
    op.drop_column("chat_messages", "provider_error_code")
    op.drop_column("chat_messages", "error_http_status")
    op.drop_column("chat_messages", "error_origin")


def downgrade() -> None:
    op.add_column("chat_messages", sa.Column("error_origin", sa.String(length=32), nullable=True))
    op.add_column("chat_messages", sa.Column("error_http_status", sa.Integer(), nullable=True))
    op.add_column("chat_messages", sa.Column("provider_error_code", sa.String(length=128), nullable=True))
    op.add_column("chat_messages", sa.Column("retry_after_seconds", sa.Integer(), nullable=True))
